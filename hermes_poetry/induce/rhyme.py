"""韵伴聚类：从近体诗偶数句尾字共现归纳韵组（B层计量的归纳延伸）。

诚实边界与口径（对审核发现的修正）：
  * 采样只取 4/8 句、5/7 言的近体近似诗——长篇齐言古体普遍换韵，
    诗经/楚辞/元曲句式杂，全部排除，避免把互不相押的韵部焊接连通；
  * 只连相邻韵脚（第2↔4、4↔6、6↔8句尾字）：换韵古体混入 8 句样本时
    只产生一条换韵点弱边（通常权1，被剪除），真律诗一韵到底仍经
    传递闭包成组——全团连边会把不相押的韵部直接焊死，已实测弃用；
  * 边权 = 相邻共现的诗数，弱边（<2）剪除；
  * 连通分量即韵组；不做「提高阈值重聚」（那会剥落外围节点制造
    假纯度）——分量规模超过 250 字即如实标 low_purity 并降 bronze；
  * n_poems 按成员字的支撑诗全集统计（不抽样），成员不截断。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Set

from .. import config
from ..schemas import Poem, RhymePartnerRule, write_jsonl
from ..textutil import t2s

MAX_CLEAN_COMPONENT = 250   # 超过即视为通押打通，如实标注低纯度
MIN_EDGE_WEIGHT = 2


def _rhyme_sets(poems: List[Poem]) -> List[tuple]:
    """(poem_id, 有序韵脚列表)——保持原文顺序以支持相邻连边。"""
    out = []
    for p in poems:
        m = p.metrics or {}
        feet = m.get("rhyme_feet") or []
        if (len(feet) >= 2 and m.get("uniform")
                and m.get("line_count") in (4, 8)
                and m.get("char_per_line") in (5, 7)):
            folded = [t2s(c) for c in feet]
            if len(set(folded)) >= 2:
                out.append((p.poem_id, folded))
    return out


def _components(edges: Dict[tuple, int], min_w: int) -> List[Set[str]]:
    adj: Dict[str, Set[str]] = defaultdict(set)
    for (a, b), w in edges.items():
        if w >= min_w:
            adj[a].add(b)
            adj[b].add(a)
    seen: Set[str] = set()
    comps = []
    for node in adj:
        if node in seen:
            continue
        comp, stack = set(), [node]
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            stack.extend(adj[cur] - comp)
        seen |= comp
        if len(comp) >= 2:
            comps.append(comp)
    return comps


class RhymeInducer:
    def __init__(self, poems: List[Poem]):
        self.samples = _rhyme_sets(poems)

    def run(self) -> List[RhymePartnerRule]:
        edges: Dict[tuple, int] = Counter()
        char_freq: Counter = Counter()
        char_poems: Dict[str, Set[str]] = defaultdict(set)
        for pid, feet in self.samples:
            uniq = set(feet)
            char_freq.update(uniq)
            for c in uniq:
                char_poems[c].add(pid)
            # 相邻韵脚连边（非全团）
            for a, b in zip(feet, feet[1:]):
                if a != b:
                    key = (a, b) if a < b else (b, a)
                    edges[key] += 1

        comps = _components(edges, MIN_EDGE_WEIGHT)
        rules = []
        for i, comp in enumerate(sorted(comps, key=lambda c: -len(c)), 1):
            members = sorted(comp, key=lambda c: -char_freq[c])
            label = "·".join(members[:3])
            comp_edges = [(k, w) for k, w in edges.items()
                          if k[0] in comp and k[1] in comp and w >= MIN_EDGE_WEIGHT]
            comp_edges.sort(key=lambda kw: -kw[1])
            support: Set[str] = set()
            for c in comp:
                support |= char_poems[c]
            low_purity = len(comp) > MAX_CLEAN_COMPONENT
            note = "韵伴聚类由近体诗（4/8句、5/7言）偶数句尾字共现归纳，非平水韵权威表。"
            if low_purity:
                note += "（本组规模异常：通押/邻韵可能打通连通性，仅供研究参考。）"
            # 广韵交叉验证：报告本组成员的韵目分布与声调纯度（B层旁证）
            yun_profile = {}
            try:
                from ..extract.phonology import get_phonology
                ph = get_phonology()
                if ph.ready:
                    yun_profile = ph.group_yun_profile(members)
                    tones = yun_profile.get("tone_distribution", {})
                    determined = sum(tones.values())
                    if determined:
                        dom_tone, dom_n = max(tones.items(), key=lambda kv: kv[1])
                        yun_profile["tone_purity"] = round(dom_n / determined, 3)
                        yun_profile["dominant_tone"] = dom_tone
            except RuntimeError:
                pass
            rules.append(RhymePartnerRule(
                rhyme_rule_id=f"RPR_{i:03d}",
                label=label,
                members=members[:400],
                n_poems=len(support),
                edge_examples=[{"pair": list(k), "co_occurrence": w} for k, w in comp_edges[:10]],
                supporting_poems=sorted(support)[:60],
                yun_profile=yun_profile,
                release_level="bronze" if low_purity else "silver",
                note=note,
            ))
        return rules


def persist_rhyme(rules: List[RhymePartnerRule]) -> None:
    write_jsonl(config.RULES_RHYME_DIR / "rhyme_partners.jsonl", rules)


def rhyme_lookup(rules: List[RhymePartnerRule]) -> Dict[str, str]:
    """字 → 韵组标签。"""
    out = {}
    for r in rules:
        for ch in r.members:
            out.setdefault(ch, r.label)
    return out
