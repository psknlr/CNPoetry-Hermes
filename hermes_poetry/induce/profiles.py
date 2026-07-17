"""跨诗归纳：意象档案、题材档案、词牌定格、诗人档案。

归纳层铁律：只消费未被拒绝的初始规则；只引用下层 ID 并附证据链；
相反情感并存时列入 conflicts 呈现而不裁决；绝不改写初始规则。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List

from .. import config
from ..lexicon import IMAGERY, THEMES
from ..schemas import (
    AuthorProfileRule, CipaiProfileRule, ImageryProfileRule, InitialRule,
    Poem, ThemeProfileRule, write_jsonl,
)
from ..textutil import t2s
from ..extract.metrics import char_pattern

# 情感语义上的对立组（用于 conflicts 呈现）
_OPPOSED = [("愁苦哀伤", "喜悦闲适"), ("孤寂冷清", "豪迈壮阔")]


class ImageryInducer:
    def __init__(self, poems: List[Poem], accepted: List[InitialRule]):
        self.by_id = {p.poem_id: p for p in poems}
        self.rules = [r for r in accepted if r.rule_type == "imagery_emotion_rule"]

    def run(self) -> List[ImageryProfileRule]:
        grouped: Dict[str, List[InitialRule]] = defaultdict(list)
        for r in self.rules:
            grouped[r.if_conditions["imagery"][0]].append(r)
        out = []
        for canon, rules in sorted(grouped.items()):
            emo_rules: Dict[str, List[InitialRule]] = defaultdict(list)
            for r in rules:
                emo_rules[r.then_conclusions["emotion"]].append(r)
            associations = []
            for emo, rs in sorted(emo_rules.items(), key=lambda kv: -len(kv[1])):
                strengths = Counter(r.strength for r in rs)
                best = max(rs, key=lambda r: (r.strength == "显证", r.autonomous_review.consensus_score))
                associations.append({
                    "emotion": emo,
                    "support": len(rs),
                    "strength_breakdown": dict(strengths),
                    "example": {"poem_id": best.poem_id, "quote": best.evidence_span,
                                "title": self._title(best.poem_id)},
                })
            conflicts = []
            emos = set(emo_rules)
            for a, b in _OPPOSED:
                if a in emos and b in emos:
                    conflicts.append({
                        "type": "opposed_emotions_coexist",
                        "emotions": [a, b],
                        "note": "同一意象在语料中承载相反情感，属正常文学现象，呈现不裁决。",
                    })
            poem_ids = sorted({r.poem_id for r in rules})
            dyn = Counter(self.by_id[pid].dynasty for pid in poem_ids if pid in self.by_id)
            co = Counter()
            for pid in poem_ids:
                p = self.by_id.get(pid)
                if p:
                    co.update(x for x in p.imagery if x != canon)
            n_support = len(rules)
            out.append(ImageryProfileRule(
                imagery_rule_id=f"IMR_{canon}",
                imagery=canon,
                surface_forms=IMAGERY.get(canon, []),
                emotion_associations=associations,
                co_imagery=[{"imagery": k, "count": v} for k, v in co.most_common(8)],
                n_poems=len(poem_ids),
                dynasty_distribution=dict(dyn),
                supporting_initial_rules=[r.initial_rule_id for r in rules][:200],
                evidence_chain=[{
                    "poem_id": r.poem_id, "title": self._title(r.poem_id),
                    "author": self._author(r.poem_id), "quote": r.evidence_span,
                    "layer": "A",
                } for r in rules[:12]],
                conflicts=conflicts,
                consensus_score=round(min(0.95, 0.6 + 0.02 * n_support), 3),
                release_level="gold" if n_support >= 8 else ("silver" if n_support >= 3 else "bronze"),
            ))
        return out

    def _title(self, pid: str) -> str:
        p = self.by_id.get(pid)
        return p.title if p else ""

    def _author(self, pid: str) -> str:
        p = self.by_id.get(pid)
        return p.author if p else ""


class ThemeInducer:
    def __init__(self, poems: List[Poem], accepted: List[InitialRule]):
        self.by_id = {p.poem_id: p for p in poems}
        self.rules = [r for r in accepted if r.rule_type == "theme_rule"]

    def run(self) -> List[ThemeProfileRule]:
        grouped: Dict[str, List[InitialRule]] = defaultdict(list)
        for r in self.rules:
            grouped[r.then_conclusions["theme"]].append(r)
        out = []
        for theme, rules in sorted(grouped.items()):
            poem_ids = sorted({r.poem_id for r in rules})
            dyn = Counter(self.by_id[pid].dynasty for pid in poem_ids if pid in self.by_id)
            img = Counter()
            for pid in poem_ids:
                p = self.by_id.get(pid)
                if p:
                    img.update(p.imagery)
            strong = [r for r in rules if r.strength == "显证"]
            examples = sorted(strong or rules, key=lambda r: -r.autonomous_review.consensus_score)[:8]
            out.append(ThemeProfileRule(
                theme_rule_id=f"THR_{theme}",
                theme=theme,
                definition=str(THEMES.get(theme, {}).get("definition", "")),
                marker_terms=list(THEMES.get(theme, {}).get("markers", []))[:20],
                n_poems=len(poem_ids),
                dynasty_distribution=dict(dyn),
                top_imagery=[{"imagery": k, "count": v} for k, v in img.most_common(10)],
                example_evidence=[{
                    "poem_id": r.poem_id, "title": self._title(r.poem_id), "quote": r.evidence_span,
                } for r in examples],
                supporting_poems=poem_ids[:500],
                release_level="gold" if len(poem_ids) >= 30 else "silver",
            ))
        return out

    def _title(self, pid: str) -> str:
        p = self.by_id.get(pid)
        return p.title if p else ""


class CipaiInducer:
    def __init__(self, poems: List[Poem]):
        self.ci = [p for p in poems if p.cipai]

    def run(self) -> List[CipaiProfileRule]:
        grouped: Dict[str, List[Poem]] = defaultdict(list)
        for p in self.ci:
            grouped[t2s(p.cipai)].append(p)
        out = []
        for cipai_s, ps in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
            if len(ps) < 2:
                continue
            patterns = Counter(char_pattern(p.metrics.get("char_counts", [])) for p in ps if p.metrics)
            mode_pattern, mode_n = patterns.most_common(1)[0]
            line_counts = Counter(p.metrics.get("line_count", 0) for p in ps if p.metrics)
            examples = ps[:3]
            out.append(CipaiProfileRule(
                cipai_rule_id=f"CPR_{cipai_s}",
                cipai=ps[0].cipai,
                n_poems=len(ps),
                line_count_mode=line_counts.most_common(1)[0][0] if line_counts else 0,
                char_pattern=mode_pattern,
                pattern_consistency=round(mode_n / len(ps), 3),
                example_poems=[{"poem_id": p.poem_id, "title": p.title, "author": p.author} for p in examples],
                supporting_poems=[p.poem_id for p in ps][:300],
                release_level="silver" if len(ps) >= 5 else "bronze",
            ))
        return out


class AuthorInducer:
    def __init__(self, poems: List[Poem], bios: Dict[str, Dict[str, str]], min_poems: int = 5):
        self.poems = poems
        self.bios = bios
        self.min_poems = min_poems

    def run(self) -> List[AuthorProfileRule]:
        grouped: Dict[str, List[Poem]] = defaultdict(list)
        for p in self.poems:
            if p.author and p.author != "佚名":
                grouped[t2s(p.author)].append(p)
        out = []
        for author_s, ps in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
            if len(ps) < self.min_poems:
                continue
            img, themes, forms = Counter(), Counter(), Counter()
            for p in ps:
                img.update(p.imagery)
                themes.update(p.themes)
                forms[p.genre] += 1
            bio = self.bios.get(author_s, {})
            curated = [p for p in ps if p.source in ("TANG300", "SONGCI300", "QIANJIA", "SHUIMO") or p.also_in]
            rep = (curated or ps)[:6]
            dyn = Counter(p.dynasty for p in ps).most_common(1)[0][0]
            out.append(AuthorProfileRule(
                author_rule_id=f"APR_{author_s}",
                author=ps[0].author,
                dynasty=dyn,
                n_poems=len(ps),
                top_imagery=[{"imagery": k, "count": v} for k, v in img.most_common(10)],
                top_themes=[{"theme": k, "count": v} for k, v in themes.most_common(6)],
                form_distribution=dict(forms),
                bio=bio.get("desc", ""),
                bio_source="全唐诗/全宋词作者小传" if bio else "",
                representative_poems=[{"poem_id": p.poem_id, "title": p.title} for p in rep],
                supporting_poems=[p.poem_id for p in ps][:500],
                release_level="silver",
            ))
        return out


def persist_profiles(imagery, themes, cipai, authors) -> None:
    write_jsonl(config.RULES_IMAGERY_DIR / "imagery_profiles.jsonl", imagery)
    write_jsonl(config.RULES_THEME_DIR / "theme_profiles.jsonl", themes)
    write_jsonl(config.RULES_CIPAI_DIR / "cipai_profiles.jsonl", cipai)
    write_jsonl(config.RULES_AUTHOR_DIR / "author_profiles.jsonl", authors)
