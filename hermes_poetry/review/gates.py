"""自主审核闸门：schema → 证据回源 → 语义 → 对抗批评 → 修复 → 共识 → 发布。

硬性规则（与伤寒-赫尔墨斯完全同构）：
  * 证据回源失败或批评硬失败 → 一律 rejected，分数再高也不放行；
  * 修复只做「删除与降级」，绝不发明证据；修复后重新核验；
  * 每条规则每个阶段都有 AuditRecord，三个落盘口：
    rules_initial/（通过）、rejected/（拒绝）、audit/（全量审计）。
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from .. import config
from ..lexicon import EMOTIONS, IMAGERY, POSTHOC_TERMS, THEMES, NEGATION_PREFIX
from ..schemas import (
    AuditRecord, EVIDENCE_TYPES, InitialRule, INTERPRETATION_LEVELS, Poem,
    RE_INITIAL_RULE_ID, RE_POEM_ID, RULE_TYPES, write_jsonl,
)
from ..textutil import contains_verbatim, t2s


class PoemStore:
    """证据存储：poem_id → Poem；外部分析 external_id → 记录。"""

    def __init__(self, poems: List[Poem], external: Optional[List[Dict]] = None):
        self.by_id: Dict[str, Poem] = {p.poem_id: p for p in poems}
        self.external: Dict[str, Dict] = {str(e.get("id", "")): e for e in (external or [])}

    def get(self, poem_id: str) -> Optional[Poem]:
        return self.by_id.get(poem_id)

    def evidence_haystacks(self, rule: InitialRule) -> List[str]:
        """规则证据可回源的文本层（按 evidence_type 决定）。"""
        poem = self.get(rule.poem_id)
        if poem is None:
            return []
        if rule.evidence_type == "original_text":
            return [poem.text]
        if rule.evidence_type == "annotation_text":
            return poem.notes
        if rule.evidence_type == "appreciation_text":
            return [poem.appreciation]
        if rule.evidence_type == "external_analysis":
            ext = self.external.get(str(rule.if_conditions.get("external_id", "")))
            # D层双向回源：跨度须同时在诗文本与外部分析文本中
            return [poem.text] if ext and contains_verbatim(ext.get("text", ""), rule.evidence_span) else []
        return []

    def external_record(self, rule: InitialRule) -> Optional[Dict]:
        return self.external.get(str(rule.if_conditions.get("external_id", "")))


# ── 阶段一：schema ────────────────────────────────────────────────────

def validate_schema(rule: InitialRule) -> Tuple[bool, List[str]]:
    from ..textutil import content_only
    flags = []
    if not RE_INITIAL_RULE_ID.match(rule.initial_rule_id or ""):
        flags.append("schema:bad_rule_id")
    if not RE_POEM_ID.match(rule.poem_id or ""):
        flags.append("schema:bad_poem_id")
    # 规则 ID 必须锚定其声称的 poem_id（防止移花接木）
    if rule.poem_id and rule.initial_rule_id:
        stem = rule.poem_id.replace("CNP_", "", 1)
        if not rule.initial_rule_id.startswith(f"IR_CNP_{stem}_"):
            flags.append("schema:rule_id_poem_id_mismatch")
    if rule.rule_type not in RULE_TYPES:
        flags.append(f"schema:bad_rule_type:{rule.rule_type}")
    if rule.evidence_type not in EVIDENCE_TYPES:
        flags.append(f"schema:bad_evidence_type:{rule.evidence_type}")
    if rule.interpretation_level not in INTERPRETATION_LEVELS:
        flags.append("schema:bad_interpretation_level")
    # 跨度长度按内容字（去标点）计，防单字/标点跨度充数
    if len(content_only(rule.evidence_span or "")) < 3:
        flags.append("schema:evidence_span_too_short")
    if not isinstance(rule.if_conditions, dict) or not rule.if_conditions:
        flags.append("schema:empty_if_conditions")
    if not isinstance(rule.then_conclusions, dict) or not rule.then_conclusions:
        flags.append("schema:empty_then_conclusions")
    try:
        conf = float(rule.model_confidence)
        if not (0.0 <= conf <= 1.0):
            flags.append("schema:bad_confidence")
    except (TypeError, ValueError):
        flags.append("schema:bad_confidence")
    return (not flags, flags)


# ── 阶段二：证据回源（全系统核心）─────────────────────────────────────

def verify_evidence(rule: InitialRule, store: PoemStore) -> Tuple[bool, List[str]]:
    flags: List[str] = []
    poem = store.get(rule.poem_id)
    if poem is None:
        return False, [f"evidence:poem_id_not_found:{rule.poem_id}"]
    haystacks = store.evidence_haystacks(rule)
    if not any(contains_verbatim(h, rule.evidence_span) for h in haystacks if h):
        flags.append("evidence:span_not_in_source")
    # IF 侧逐项回源
    for surface in rule.if_conditions.get("imagery_surface", []) or []:
        if not contains_verbatim(rule.evidence_span, surface):
            flags.append(f"evidence:imagery_not_in_span:{surface}")
    for marker in rule.if_conditions.get("theme_markers", []) or []:
        if not contains_verbatim(poem.text, marker):
            flags.append(f"evidence:theme_marker_not_in_text:{marker}")
    marker = rule.then_conclusions.get("emotion_marker")
    if marker and not contains_verbatim(rule.evidence_span, marker):
        flags.append(f"evidence:emotion_marker_not_in_span:{marker}")
    # 意象-情感规则的 IF/THEN 内部一致性（伪造词库映射防线）
    if rule.rule_type == "imagery_emotion_rule":
        from ..lexicon import EMOTIONS, IMAGERY
        surfaces = rule.if_conditions.get("imagery_surface") or []
        canons = rule.if_conditions.get("imagery") or []
        if not surfaces or not canons:
            flags.append("evidence:imagery_rule_missing_surface_or_canon")
        else:
            canon = canons[0]
            reg = {t2s(s) for s in IMAGERY.get(canon, [])}
            for s in surfaces:
                if t2s(s) not in reg:
                    flags.append(f"evidence:surface_not_registered_for_imagery:{s}->{canon}")
        emo = rule.then_conclusions.get("emotion", "")
        if marker and emo in EMOTIONS:
            reg_markers = {t2s(m) for m in EMOTIONS[emo]}
            if t2s(marker) not in reg_markers:
                flags.append(f"evidence:marker_not_registered_for_emotion:{marker}->{emo}")
    # D层规则：结论必须逐字来自外部记录对应字段（防移花接木改写）
    if rule.evidence_type == "external_analysis":
        ext = store.external_record(rule)
        if ext is None:
            flags.append("evidence:external_record_not_found")
        else:
            for key in ("subject", "theme", "emotion"):
                val = rule.then_conclusions.get(key)
                if val and not contains_verbatim(ext.get(key, ""), val):
                    flags.append(f"evidence:external_conclusion_not_in_record:{key}")
    # 注释规则：结论文本必须逐字来自被绑定的注释本身
    if rule.rule_type == "annotation_rule":
        note = rule.then_conclusions.get("annotation", "")
        if not note or not any(contains_verbatim(n, note) for n in poem.notes):
            flags.append("evidence:annotation_not_in_notes")
    return (not flags, flags)


# ── 阶段三：语义 ─────────────────────────────────────────────────────

def review_semantics(rule: InitialRule, store: PoemStore) -> Tuple[str, List[str]]:
    flags: List[str] = []
    poem = store.get(rule.poem_id)
    if poem is None:
        return "fail", ["semantic:poem_missing"]
    if rule.rule_type == "imagery_emotion_rule":
        if not rule.if_conditions.get("imagery"):
            return "fail", ["semantic:imagery_rule_without_imagery"]
        canon = rule.if_conditions["imagery"][0]
        if canon not in IMAGERY:
            return "fail", [f"semantic:unknown_imagery:{canon}"]
        if rule.then_conclusions.get("emotion") not in EMOTIONS:
            return "fail", [f"semantic:unknown_emotion:{rule.then_conclusions.get('emotion')}"]
    if rule.rule_type == "theme_rule":
        if rule.then_conclusions.get("theme") not in THEMES:
            return "fail", [f"semantic:unknown_theme:{rule.then_conclusions.get('theme')}"]
        if not (rule.if_conditions.get("theme_markers") or []):
            # 标记词被修复删空 → 零证据题材规则不得发布
            return "fail", ["semantic:theme_rule_without_markers"]
    if rule.rule_type == "form_metric_rule":
        from ..extract.metrics import detect_form, char_pattern
        m = detect_form(poem)
        if rule.if_conditions.get("char_pattern") != char_pattern(m["char_counts"]):
            return "fail", ["semantic:metric_not_reproducible"]
    if rule.rule_type == "rhyme_rule":
        from ..extract.metrics import detect_form
        m = detect_form(poem)
        if rule.then_conclusions.get("rhyme_feet") != m["rhyme_feet"]:
            return "fail", ["semantic:rhyme_feet_not_reproducible"]
    # 证据跨度覆盖过宽：长诗整篇作跨度证明力不足
    if rule.evidence_type == "original_text" and len(poem.text) > 120:
        if len(rule.evidence_span) > 0.9 * len(poem.text):
            flags.append("semantic:span_overbroad")
    return ("warn" if flags else "pass"), flags


# ── 阶段四：对抗批评 ─────────────────────────────────────────────────

def criticize(rule: InitialRule, store: PoemStore) -> Tuple[str, List[str]]:
    flags: List[str] = []
    hard_fail = False
    # 1) 后世鉴赏套语混入 if/then（硬失败）
    body = " ".join(
        str(v) for v in list(rule.if_conditions.values()) + list(rule.then_conclusions.values())
    )
    for term in POSTHOC_TERMS:
        if term in body:
            flags.append(f"critic:posthoc_term_in_body:{term}")
            hard_fail = True
    # 2) 情感标记处于否定语境却计为正向（硬失败）。
    #    统一在去标点/空白的内容层扫描，防止带杂质的 marker 绕过检查。
    if rule.rule_type == "imagery_emotion_rule":
        from ..textutil import content_only
        marker = rule.then_conclusions.get("emotion_marker", "")
        span = content_only(t2s(rule.evidence_span))
        if marker:
            m_folded = content_only(t2s(marker))
            idx = span.find(m_folded) if m_folded else -1
            while idx >= 0:
                if idx > 0 and span[idx - 1] in NEGATION_PREFIX:
                    flags.append(f"critic:negated_emotion_as_positive:{marker}")
                    hard_fail = True
                    break
                idx = span.find(m_folded, idx + 1)
    # 3) 强度虚标：邻证/弱证冒称显证（降级修复）
    if rule.rule_type == "imagery_emotion_rule" and rule.strength == "显证":
        surfaces = rule.if_conditions.get("imagery_surface", [])
        marker = rule.then_conclusions.get("emotion_marker", "")
        poem = store.get(rule.poem_id)
        if poem and surfaces and marker:
            same_line = any(
                contains_verbatim(ln, surfaces[0]) and contains_verbatim(ln, marker)
                for ln in poem.lines
            )
            if not same_line:
                flags.append("critic:strength_overclaimed")
    # 4) D层证据冒称本系统结论（硬失败）。按 evidence_type 判定而非
    #    rule_type——改个类型名绕不过去。
    if rule.evidence_type == "external_analysis" and rule.interpretation_level != "external_llm":
        flags.append("critic:external_analysis_mislabelled")
        hard_fail = True
    result = "fail" if hard_fail else ("warn" if flags else "pass")
    return result, flags


# ── 阶段五：自动修复（只删不增）───────────────────────────────────────

def repair(rule: InitialRule, flags: List[str], store: PoemStore) -> List[str]:
    repairs: List[str] = []
    for flag in flags:
        if flag.startswith("evidence:theme_marker_not_in_text:"):
            bad = flag.rsplit(":", 1)[1]
            markers = rule.if_conditions.get("theme_markers", [])
            if bad in markers:
                markers.remove(bad)
                repairs.append(f"dropped_unattested_marker:{bad}")
        if flag == "critic:strength_overclaimed":
            rule.strength = "邻证"
            rule.model_confidence = min(rule.model_confidence, 0.8)
            repairs.append("strength_downgraded")
        if flag.startswith("critic:posthoc_term_in_body:"):
            term = flag.rsplit(":", 1)[1]
            for cond in (rule.if_conditions, rule.then_conclusions):
                for k, v in list(cond.items()):
                    if isinstance(v, str) and term in v:
                        cond[k] = v.replace(term, "")
                    elif isinstance(v, list):
                        cond[k] = [x for x in v if term not in str(x)]
            rule.interpretation = (rule.interpretation + f"（后世术语「{term}」移出规则主体）").strip()
            rule.interpretation_level = "model_inference"
            repairs.append(f"posthoc_term_moved:{term}")
    return repairs


# ── 共识评分与发布闸门 ────────────────────────────────────────────────

_LITERAL_TYPES = {"form_metric_rule", "rhyme_rule", "annotation_rule"}


def consensus_score(rule: InitialRule, evidence_ok: bool, sem: str, crit: str, repaired: bool) -> float:
    score = 0.0
    if evidence_ok:
        score += 0.50
    score += {"pass": 0.12, "warn": 0.06}.get(sem, 0.0)
    score += {"pass": 0.16, "warn": 0.08}.get(crit, 0.0)
    if rule.strength == "显证" or rule.rule_type in _LITERAL_TYPES:
        score += 0.08
    elif rule.strength == "邻证":
        score += 0.05
    elif rule.strength == "弱证":
        score += 0.02
    cond_n = sum(len(v) if isinstance(v, list) else 1 for v in rule.if_conditions.values())
    score += min(0.06, 0.02 * cond_n)
    score += 0.04 * min(1.0, float(rule.model_confidence))
    if rule.evidence_type == "external_analysis":
        score -= 0.06
    if repaired:
        score = min(score, 0.92)
    return max(0.0, min(score, 0.98))


def release_gate(score: float, evidence_ok: bool, crit: str, sem: str = "pass") -> str:
    if not evidence_ok or crit == "fail" or sem == "fail":
        return "rejected"
    if score >= config.RELEASE_GOLD:
        return "gold"
    if score >= config.RELEASE_SILVER:
        return "silver"
    if score >= config.RELEASE_BRONZE:
        return "bronze"
    return "rejected"


# ── 审核流水线 ────────────────────────────────────────────────────────


class ReviewPipeline:
    def __init__(self, store: PoemStore):
        self.store = store
        self.audits: List[AuditRecord] = []
        self.critic_counter: Counter = Counter()
        self._audit_seq = 0

    def _audit(self, rule: InitialRule, stage: str, result: str, flags: List[str], **details):
        self._audit_seq += 1
        self.audits.append(AuditRecord(
            audit_id=f"AUD_{self._audit_seq:06d}",
            target_id=rule.initial_rule_id,
            stage=stage,
            result=result,
            flags=flags,
            details=details,
        ))

    def review_rule(self, rule: InitialRule) -> InitialRule:
        rv = rule.autonomous_review
        # 1 schema
        ok, flags = validate_schema(rule)
        rv.schema_valid = ok
        self._audit(rule, "schema", "pass" if ok else "fail", flags)
        if not ok:
            rv.release_level = "rejected"
            self._audit(rule, "release", "rejected", flags)
            return rule
        # 2 evidence
        ev_ok, ev_flags = verify_evidence(rule, self.store)
        rv.evidence_verified = ev_ok
        self._audit(rule, "evidence", "pass" if ev_ok else "fail", ev_flags)
        # 3 semantic
        sem, sem_flags = review_semantics(rule, self.store)
        rv.semantic_result = sem
        self._audit(rule, "semantic", sem, sem_flags)
        # 4 critic
        crit, crit_flags = criticize(rule, self.store)
        rv.critic_result = crit
        rv.critic_flags = crit_flags
        self.critic_counter.update(f.split(":")[1] if ":" in f else f for f in crit_flags)
        self._audit(rule, "critic", crit, crit_flags)
        # 5 repair（一轮）+ 重核
        all_flags = ev_flags + sem_flags + crit_flags
        repairs = repair(rule, all_flags, self.store) if all_flags else []
        rv.repairs = repairs
        if repairs:
            self._audit(rule, "repair", "repaired", repairs)
            ev_ok, ev_flags = verify_evidence(rule, self.store)
            rv.evidence_verified = ev_ok
            sem, _ = review_semantics(rule, self.store)
            rv.semantic_result = sem
            crit, crit_flags = criticize(rule, self.store)
            rv.critic_result = crit
            rv.critic_flags = crit_flags
            self._audit(rule, "evidence", "pass" if ev_ok else "fail", ev_flags, reverify=True)
        # 6 consensus + release（修复后重跑 schema，修空的规则不得发布）
        if repairs:
            schema_ok, schema_flags = validate_schema(rule)
            rv.schema_valid = schema_ok
            if not schema_ok:
                self._audit(rule, "schema", "fail", schema_flags, reverify=True)
                rv.release_level = "rejected"
                self._audit(rule, "release", "rejected", schema_flags)
                return rule
        score = consensus_score(rule, ev_ok, sem, crit, bool(repairs))
        rv.consensus_score = round(score, 3)
        level = release_gate(score, ev_ok, crit, sem)
        rv.release_level = level
        self._audit(rule, "consensus", "pass", [], score=rv.consensus_score)
        self._audit(rule, "release", level, [])
        return rule

    def run(self, rules: List[InitialRule]) -> Tuple[List[InitialRule], List[InitialRule]]:
        accepted, rejected = [], []
        for rule in rules:
            self.review_rule(rule)
            (accepted if rule.autonomous_review.release_level != "rejected" else rejected).append(rule)
        return accepted, rejected

    def persist(self, accepted: List[InitialRule], rejected: List[InitialRule]) -> None:
        write_jsonl(config.RULES_INITIAL_DIR / "initial_rules.jsonl", accepted)
        write_jsonl(config.REJECTED_DIR / "rejected_rules.jsonl", rejected)
        write_jsonl(config.AUDIT_DIR / "audit_log.jsonl", self.audits)
