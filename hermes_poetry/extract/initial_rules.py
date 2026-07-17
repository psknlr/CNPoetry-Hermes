"""初始规则抽取：一首作品只产出关于它自身的规则。

铁律：
  * evidence_span 永远是该作品（或其注释/外部分析）的逐字文本；
  * 意象-情感规则只在同句（显证）或邻句（邻证）成立时产出，
    同篇远距共现不产规则（噪声留给检索层）；
  * 后世鉴赏套语不进入 if/then（审核层有对抗检查）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..schemas import InitialRule, Poem
from ..textutil import contains_verbatim, t2s
from .annotate import LineHits, annotate_poem
from .metrics import char_pattern


class InitialRuleExtractor:
    def __init__(self) -> None:
        self._seq: Dict[str, int] = {}

    def _next_id(self, poem: Poem) -> str:
        n = self._seq.get(poem.poem_id, 0) + 1
        self._seq[poem.poem_id] = n
        stem = poem.poem_id.replace("CNP_", "", 1)
        return f"IR_CNP_{stem}_{n:03d}"

    def extract(self, poem: Poem) -> List[InitialRule]:
        hits = annotate_poem(poem)
        rules: List[InitialRule] = []
        rules.extend(self._imagery_emotion_rules(poem, hits))
        rules.extend(self._theme_rules(poem, hits))
        fm = self._form_rule(poem)
        if fm:
            rules.append(fm)
        rh = self._rhyme_rule(poem)
        if rh:
            rules.append(rh)
        rules.extend(self._annotation_rules(poem))
        return rules

    # ── 意象-情感 ────────────────────────────────────────────────
    def _imagery_emotion_rules(self, poem: Poem, hits: List[LineHits]) -> List[InitialRule]:
        # 先收集全部候选再择优：同句显证永远优先于先出现的邻证
        best: Dict[tuple, tuple] = {}   # (canon, cat) -> (rank, i, surface, marker, span, same_line)
        for i, h in enumerate(hits):
            neighbors = [hits[i]] + ([hits[i + 1]] if i + 1 < len(hits) else [])
            for canon, surface in h.imagery:
                for j, nb in enumerate(neighbors):
                    for cat, marker in nb.emotions:
                        same_line = j == 0
                        rank = 0 if same_line else 1
                        span = h.line if same_line else f"{h.line}，{nb.line}"
                        key = (canon, cat)
                        cand = (rank, i, surface, marker, span, same_line)
                        if key not in best or cand[:2] < best[key][:2]:
                            best[key] = cand
        rules = []
        for (canon, cat), (rank, _i, surface, marker, span, same_line) in sorted(
                best.items(), key=lambda kv: (kv[1][0], kv[1][1])):
            rules.append(InitialRule(
                initial_rule_id=self._next_id(poem),
                poem_id=poem.poem_id,
                rule_type="imagery_emotion_rule",
                if_conditions={"imagery": [canon], "imagery_surface": [surface]},
                then_conclusions={"emotion": cat, "emotion_marker": marker},
                evidence_span=span,
                evidence_type="original_text",
                strength="显证" if same_line else "邻证",
                interpretation=f"「{surface}」与情感标记「{marker}」{'同句' if same_line else '邻句'}共现。",
                interpretation_level="normalized",
                model_confidence=0.9 if same_line else 0.8,
            ))
        return rules

    # ── 题材 ─────────────────────────────────────────────────────
    def _theme_rules(self, poem: Poem, hits: List[LineHits]) -> List[InitialRule]:
        rules = []
        for theme in poem.themes:
            marker_lines = [(m, h.line) for h in hits for t, m in h.themes if t == theme]
            if not marker_lines:
                continue
            markers = []
            for m, _ in marker_lines:
                if m not in markers:
                    markers.append(m)
            span = marker_lines[0][1]
            rules.append(InitialRule(
                initial_rule_id=self._next_id(poem),
                poem_id=poem.poem_id,
                rule_type="theme_rule",
                if_conditions={"theme_markers": markers[:6]},
                then_conclusions={"theme": theme},
                evidence_span=span,
                evidence_type="original_text",
                strength="显证" if len(markers) >= 2 else "弱证",
                interpretation=f"标记词 {'、'.join(markers[:4])} 指向题材「{theme}」。",
                interpretation_level="normalized",
                model_confidence=0.85 if len(markers) >= 2 else 0.7,
            ))
        return rules

    # ── 计量（B层）────────────────────────────────────────────────
    def _form_rule(self, poem: Poem) -> Optional[InitialRule]:
        m = poem.metrics
        if not m or not poem.lines:
            return None
        return InitialRule(
            initial_rule_id=self._next_id(poem),
            poem_id=poem.poem_id,
            rule_type="form_metric_rule",
            if_conditions={"line_count": m["line_count"], "char_pattern": char_pattern(m["char_counts"])},
            then_conclusions={"genre": poem.genre, "genre_source": poem.genre_source},
            evidence_span=poem.lines[0],
            evidence_type="original_text",
            strength="显证",
            interpretation="体裁由句数与逐句字数计量判定（语料标签优先）。",
            interpretation_level="metric",
            model_confidence=0.95,
        )

    def _rhyme_rule(self, poem: Poem) -> Optional[InitialRule]:
        m = poem.metrics
        feet = (m or {}).get("rhyme_feet") or []
        # 长篇齐言古体多换韵，整包韵脚不成一条韵事实，不产规则
        if len(feet) < 2 or (m or {}).get("line_count", 0) > 8:
            return None
        # 证据句取最后一个偶数句
        even_lines = [poem.lines[i] for i in range(1, len(poem.lines), 2)]
        return InitialRule(
            initial_rule_id=self._next_id(poem),
            poem_id=poem.poem_id,
            rule_type="rhyme_rule",
            if_conditions={"even_line_count": len(even_lines)},
            then_conclusions={"rhyme_feet": feet},
            evidence_span=even_lines[-1],
            evidence_type="original_text",
            strength="显证",
            interpretation="韵脚位置字为偶数句尾字（首句入韵不计，保守口径）。",
            interpretation_level="metric",
            model_confidence=0.9,
        )

    # ── 注释（C层）────────────────────────────────────────────────
    def _annotation_rules(self, poem: Poem) -> List[InitialRule]:
        rules = []
        for idx, note in enumerate(poem.notes[:20]):
            note = note.strip()
            if len(note) < 4:
                continue
            rules.append(InitialRule(
                initial_rule_id=self._next_id(poem),
                poem_id=poem.poem_id,
                rule_type="annotation_rule",
                if_conditions={"note_index": idx},
                then_conclusions={"annotation": note},
                evidence_span=note,
                evidence_type="annotation_text",
                strength="显证",
                interpretation="集内注释逐条绑定（C层旁证，非本系统生成）。",
                interpretation_level="literal",
                model_confidence=0.95,
            ))
        return rules


def link_external_analysis(poem: Poem, ext: Dict, seq: int) -> Optional[InitialRule]:
    """D层绑定：外部分析文本须与该诗逐字互证（首句包含判定）。"""
    if not poem.lines:
        return None
    first_line = poem.lines[0]
    ext_text = ext.get("text") or ""
    if not contains_verbatim(ext_text, first_line):
        return None
    if t2s((ext.get("author") or "").strip()) != t2s(poem.author):
        return None
    return InitialRule(
        initial_rule_id=f"IR_CNP_{poem.poem_id.replace('CNP_', '', 1)}_{seq:03d}",
        poem_id=poem.poem_id,
        rule_type="external_analysis_rule",
        if_conditions={"external_id": str(ext.get("id", "")), "external_dataset": "PoetryMTEB/ChineseClassicalPoetryDatabase"},
        then_conclusions={
            "subject": (ext.get("subject") or "")[:40],
            "theme": (ext.get("theme") or "")[:80],
            "emotion": (ext.get("emotion") or "")[:80],
        },
        evidence_span=first_line,
        evidence_type="external_analysis",
        strength="显证",
        interpretation="外部数据集 LLM 分析（DeepSeek-V3.1 生成），仅作 D 层旁证，非本系统结论。",
        interpretation_level="external_llm",
        model_confidence=0.6,
    )
