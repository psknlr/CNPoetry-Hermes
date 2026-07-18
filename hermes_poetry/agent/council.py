"""多智能体合议：规划 → 取证 → 专家 → 批评 → 共识评分 → 综合。

每步产出 CouncilMessage（时间线可视化）；专家各自用自己的工具取证并给出
结构化 judgment；接入真实模型时每位专家附一句合议评述（只许引用自己
证据内的 poem_id，逐句过 CitationGuard）；共识按固定量表打分——把
「过程表演」变成可审计的裁决记录。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..llm import get_client
from ..llm.prompts import specialist_comment_user, synth_system
from ..safety import governed, infer_role, intent_guard
from .citation import CitationGuard, RE_POEM_ID
from .tools import ToolRegistry


@dataclass
class CouncilMessage:
    agent: str = ""
    role_cn: str = ""
    action: str = ""
    content: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    data: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"agent": self.agent, "role_cn": self.role_cn, "action": self.action,
                "content": self.content, "evidence_ids": self.evidence_ids, "data": self.data}


_SPECIALISTS = {
    "ImageryAnalyst": {"cn": "意象专家", "tool": "poetry_imagery"},
    "MetricsAnalyst": {"cn": "格律专家", "tool": "poetry_metrics"},
    "ThemeAnalyst": {"cn": "题材专家", "tool": "poetry_theme"},
    "ComparisonAnalyst": {"cn": "比较专家", "tool": "poetry_differential"},
    "GlossAnalyst": {"cn": "训诂专家", "tool": "poetry_gloss"},
    "IntertextAnalyst": {"cn": "互文专家", "tool": "poetry_intertext"},
}


class Council:
    def __init__(self, registry: Optional[ToolRegistry] = None, client=None):
        self.registry = registry or ToolRegistry()
        self.client = client or get_client()
        self.guard = CitationGuard(self.registry.engine.poems)

    # ── 规划：结构化 QueryPlan ────────────────────────────────────
    def _plan(self, question: str) -> Dict:
        from ..lexicon import IMAGERY_SURFACE, THEMES
        from ..textutil import t2s
        q = t2s(question)
        plan = {"specialists": [], "entities": {}, "facets": [],
                "intent": "interpret", "ambiguities": []}
        titles = re.findall(r"[《〈]([^》〉]{1,20})[》〉]", question)
        if titles:
            plan["entities"]["titles"] = titles
            plan["specialists"].append("MetricsAnalyst")
            plan["facets"].append("structure")
            # 同题多作歧义前置识别
            for t in titles:
                cands = self.registry.engine.resolve_candidates(t)
                if len({c.author for c in cands}) > 1:
                    plan["ambiguities"].append(
                        {"title": t, "type": "POEM_AMBIGUOUS",
                         "candidates": [f"《{t}》@{c.author}" for c in cands[:4]]})
        for surface, canon in IMAGERY_SURFACE:
            if surface in q:
                plan["entities"]["imagery"] = canon
                plan["specialists"].append("ImageryAnalyst")
                plan["facets"].append("imagery")
                break
        for theme in THEMES:
            markers = [m for m in THEMES[theme]["markers"] if len(m) >= 2]  # type: ignore[index]
            if theme in q or any(m in q for m in markers):
                plan["entities"]["theme"] = theme
                plan["specialists"].append("ThemeAnalyst")
                plan["facets"].append("theme")
                break
        if len(titles) >= 2 or re.search(r"对比|比较|异同|区别", q):
            plan["specialists"].append("ComparisonAnalyst")
            plan["intent"] = "compare"
        if re.search(r"训诂|本义|字义|说文", q):
            qm = re.findall(r"[「『\"‘]([㐀-鿿]{1,4})[」』\"’]", q)
            plan["entities"]["gloss_chars"] = "".join(qm)[:8] or q[:4]
            plan["specialists"].append("GlossAnalyst")
            plan["intent"] = "gloss"
        if re.search(r"化用|袭用|互文|用典|出处相近|相似", q) and titles:
            plan["specialists"].append("IntertextAnalyst")
            plan["facets"].append("intertext")
        if re.search(r"是谁|哪个朝代|作者是|几句|什么体裁", q):
            plan["intent"] = "fact"
        # 无实体命中时不注入默认专家：宁可只靠取证员检索，
        # 也不用无关题材档案推高置信度
        plan["specialists"] = list(dict.fromkeys(plan["specialists"]))
        return plan

    def _specialist_args(self, name: str, plan: Dict, question: str) -> Dict:
        ent = plan["entities"]
        if name == "ImageryAnalyst":
            return {"imagery": ent.get("imagery", "月")}
        if name == "MetricsAnalyst":
            return {"poem_ref": f"《{ent['titles'][0]}》"} if ent.get("titles") else {"poem_ref": question}
        if name == "ThemeAnalyst":
            return {"theme": ent.get("theme", "思乡羁旅")}
        if name == "ComparisonAnalyst":
            if ent.get("titles"):
                return {"poem_refs": [f"《{t}》" for t in ent["titles"][:3]]}
            return {"query": question}
        if name == "GlossAnalyst":
            return {"chars": ent.get("gloss_chars", "")}
        if name == "IntertextAnalyst":
            return {"poem_ref": f"《{ent['titles'][0]}》"} if ent.get("titles") else {"text": question}
        return {}

    @staticmethod
    def _argument(name: str, result: Dict, ids: List[str]) -> Dict:
        """论证图节点：claim + 推理桥梁 + 证伪条件（确定性模板，绑定工具数据）。"""
        claim, warrants, falsifiers = "", [], []
        if name == "ImageryAnalyst" and result.get("imagery_profile"):
            r = result["imagery_profile"]
            top = r.get("emotion_associations", [])[:2]
            claim = (f"意象「{r.get('imagery')}」在语料中主要关联 "
                     + "、".join(f"{a['emotion']}（{a['support']}例）" for a in top))
            warrants = [f"跨 {r.get('n_poems')} 首诗的共现归纳，证据链逐条可回源"]
            if r.get("conflicts"):
                warrants.append("相反情感并存已如实呈现（不裁决）")
            falsifiers = ["若支撑例集中于单一朝代或单一诗人，该关联的普适性减弱"]
        elif name == "MetricsAnalyst" and result.get("metrics"):
            m = result["metrics"]
            tonal = m.get("tonal") or {}
            iss = tonal.get("issues") or []
            claim = f"《{m.get('title')}》体裁 {m.get('genre')}，" + \
                    ("近体律则未检出违例" if not iss else
                     "检出 " + "、".join(sorted({x['rule'] for x in iss})))
            warrants = [f"句式 {m.get('char_pattern')} 确定性复算",
                        "平仄依《广韵》韵目定调，多音字标两读不参与违例判定"]
            falsifiers = ["若语料文本为异文/节选，格律判定随文本而变"]
        elif name == "ThemeAnalyst" and result.get("theme_profile"):
            r = result["theme_profile"]
            claim = f"题材「{r.get('theme')}」在语料中有 {r.get('n_poems')} 首支撑"
            warrants = ["题材由 ≥2 个标记词或重复强标记判定（保精度口径）"]
            falsifiers = ["单标记弱命中的诗不入此档案，覆盖为下界"]
        elif name == "GlossAnalyst" and result.get("glosses"):
            gs = [g for g in result["glosses"] if g.get("shuowen")]
            claim = "、".join(f"「{g['char']}」本义：{g['shuowen']['gloss'][:12]}" for g in gs[:2])
            warrants = ["《说文解字》逐字条目（C层旁证）"]
            falsifiers = ["诗中用义可能为引申/假借，字书本义不等于诗义"]
        elif name == "IntertextAnalyst" and result.get("pairs"):
            n = len(result["pairs"])
            claim = f"检出 {n} 组逐字互文（重出/袭用/化用）"
            warrants = ["5-gram 逐字对齐，方向按朝代先后判定"]
            falsifiers = ["同源套语（疑共源标记）不构成直接承继证据"]
        elif name == "ComparisonAnalyst" and result.get("contrast"):
            claim = "逐轴对比完成（体裁/意象/题材/情感/互文）"
            warrants = ["各轴均由确定性计量或已审核规则支撑"]
        return {"claim": claim, "reasoning_warrants": warrants, "falsifiers": falsifiers}

    # ── 主流程 ───────────────────────────────────────────────────
    def deliberate(self, question: str, role: str = "") -> Dict:
        role = role or infer_role(question)
        timeline: List[CouncilMessage] = []
        ig = intent_guard(question)
        if not ig["allowed"]:
            return governed({"question": question, "answer": ig["notice"], "blocked": True,
                             "timeline": []}, role)
        registry = self.registry.for_role(role)

        plan = self._plan(question)
        plan_desc = f"意图 {plan['intent']}；派遣：" + \
                    ("、".join(_SPECIALISTS[s]["cn"] for s in plan["specialists"]) or "仅取证员")
        if plan["ambiguities"]:
            amb = plan["ambiguities"][0]
            plan_desc += f"；⚠ 同题多作《{amb['title']}》：{'、'.join(amb['candidates'][:3])}"
        timeline.append(CouncilMessage("Planner", "规划者", "plan", plan_desc, data=plan))
        # 取证员
        search = registry.call("poetry_search", {"query": question, "top_k": 6})
        search_ids = _ids_of(search)
        timeline.append(CouncilMessage("Retriever", "取证员", "retrieve",
                                       f"检索命中 {len(search.get('hits', []))} 首",
                                       evidence_ids=search_ids, data=search))
        evidence_ids = list(search_ids)
        judgments: List[Dict] = []
        for name in plan["specialists"]:
            spec = _SPECIALISTS[name]
            args = self._specialist_args(name, plan, question)
            result = registry.call(spec["tool"], args)
            ids = _ids_of(result)
            evidence_ids += [i for i in ids if i not in evidence_ids]
            judgment = {
                "specialist": name, "specialist_cn": spec["cn"], "tool": spec["tool"],
                "args": args, "evidence": ids,
                "has_error": bool(result.get("error")),
                "confidence": 0.2 if result.get("error") else (0.85 if ids else 0.5),
                **self._argument(name, result, ids),
            }
            comment = ""
            if self.client.available and not result.get("error"):
                res = self.client.chat(
                    [{"role": "system", "content": synth_system(role)},
                     {"role": "user", "content": specialist_comment_user(spec["cn"], result)}],
                    task="synthesize", context={"evidence": [], "question": question})
                crep = self.guard.check(res.content, allowed_ids=ids)
                comment = res.content if crep.ok else "（评述未过引用核验，已弃用）"
            judgment["comment"] = comment
            judgments.append(judgment)
            timeline.append(CouncilMessage(
                name, spec["cn"], "analyze",
                comment or judgment.get("claim") or f"以 {spec['tool']} 取证 {len(ids)} 处",
                evidence_ids=ids,
                data={**result, "_argument": {k: judgment[k] for k in
                                              ("claim", "reasoning_warrants", "falsifiers")}}))
        # 批评者
        critic_flags = []
        for j in judgments:
            if j["has_error"]:
                critic_flags.append(f"{j['specialist_cn']}工具报错，其结论不可采信")
            elif not j["evidence"]:
                critic_flags.append(f"{j['specialist_cn']}无 poem_id 证据，仅作参考")
        timeline.append(CouncilMessage("Critic", "批评者", "critique",
                                       "；".join(critic_flags) or "各专家证据链完整",
                                       data={"flags": critic_flags}))
        # 共识（固定量表）
        ev_n = len(evidence_ids)
        directness = 3.0 if any(j["evidence"] for j in judgments) else 0.0
        coverage = min(3.0, 0.75 * len([j for j in judgments if j["evidence"]]))
        breadth = min(2.0, ev_n / 4.0)
        penalty = min(3.0, 1.0 * len(critic_flags))
        completeness = min(2.0, 0.5 * len(judgments))
        raw = directness + coverage + breadth + completeness - penalty
        confidence = round(max(0.0, min(1.0, raw / 10.0)), 2)
        decision = ("probable" if confidence >= 0.6 else
                    "probable_but_needs_more_information" if confidence >= 0.35 else
                    "insufficient_evidence")
        timeline.append(CouncilMessage("ConsensusJudge", "共识裁决", "adjudicate",
                                       f"裁决 {decision}（置信 {confidence}）",
                                       data={"decision": decision, "confidence": confidence,
                                             "rubric": {"directness": directness, "coverage": coverage,
                                                        "breadth": breadth, "penalty": penalty,
                                                        "completeness": completeness}}))
        # 综合
        answer = self._synthesize(question, role, timeline, evidence_ids)
        report = self.guard.check(answer, allowed_ids=evidence_ids)
        final = self.guard.annotate(answer, report)
        from .claims import ClaimGuard, annotate_claims
        claim_report = ClaimGuard(self.registry.engine).check(final)
        final = annotate_claims(final, claim_report)
        timeline.append(CouncilMessage("Synthesizer", "综合者", "synthesize", final,
                                       evidence_ids=report.verified_ids,
                                       data={"citation_report": report.to_dict()}))
        return governed({
            "question": question,
            "answer": final,
            "decision": decision,
            "confidence": confidence,
            "citation_report": report.to_dict(),
            "claim_report": claim_report.to_dict(),
            "timeline": [m.to_dict() for m in timeline],
            "evidence_ids": evidence_ids,
            "backend": self.client.backend,
        }, role)

    def _synthesize(self, question: str, role: str, timeline: List[CouncilMessage],
                    evidence_ids: List[str]) -> str:
        engine = self.registry.engine
        evidence = []
        for pid in evidence_ids[:10]:
            p = engine.by_id.get(pid)
            if p:
                evidence.append({"poem_id": pid, "title": p.title, "author": p.author,
                                 "quote": p.lines[0] if p.lines else ""})
        if self.client.available:
            parts = [m.content for m in timeline if m.action in ("analyze",) and m.content]
            q = question + ("\n\n专家评述：\n" + "\n".join(parts) if parts else "")
            return self.client.synthesize(q, evidence, role)
        # 本地确定性综合
        lines = [f"合议结论（{len(evidence_ids)} 处证据）："]
        for m in timeline:
            if m.action == "analyze" and m.data:
                from ..llm.providers import LocalProvider
                text = LocalProvider()._compose_answer(m.data)
                if text:
                    lines.append(text)
        if len(lines) == 1 and evidence:
            lines += [f"- 《{e['title']}》「{e['quote']}」［{e['poem_id']}］" for e in evidence[:5]]
        return "\n\n".join(lines)


def _ids_of(payload: Dict) -> List[str]:
    ids = []
    for m in RE_POEM_ID.findall(json.dumps(payload, ensure_ascii=False)):
        if m not in ids:
            ids.append(m)
    return ids
