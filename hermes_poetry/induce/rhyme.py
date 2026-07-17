"""韵伴聚类：从近体诗偶数句尾字共现归纳韵组（B层计量的归纳延伸）。

诚实边界：这不是平水韵权威表——古体通押、邻韵通用与语料噪声都会
进入图中。做法与口径：
  * 只取齐言且句数为偶的诗（近体近似），减少换韵干扰；
  * 边权 = 两字在同一首诗韵脚位置共现的诗数，弱边（<2）剪除；
  * 连通分量即韵组；巨型分量（>全部韵脚字 40%）说明通押打通全图，
    此时提高剪枝阈值重聚一次；仍巨型则如实标注 low_purity。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Dict, List, Set

from .. import config
from ..schemas import Poem, RhymePartnerRule, write_jsonl
from ..textutil import t2s


def _rhyme_sets(poems: List[Poem]) -> List[tuple]:
    out = []
    for p in poems:
        m = p.metrics or {}
        feet = m.get("rhyme_feet") or []
        if len(feet) >= 2 and m.get("uniform") and m.get("line_count", 0) % 2 == 0:
            folded = [t2s(c) for c in feet]
            if len(set(folded)) >= 2:
                out.append((p.poem_id, sorted(set(folded))))
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
        poems_of: Dict[tuple, List[str]] = defaultdict(list)
        for pid, feet in self.samples:
            char_freq.update(feet)
            for a, b in combinations(feet, 2):
                key = (a, b) if a < b else (b, a)
                edges[key] += 1
                if len(poems_of[key]) < 3:
                    poems_of[key].append(pid)

        n_chars = len(char_freq)
        min_w, low_purity = 2, False
        comps = _components(edges, min_w)
        while comps and max(len(c) for c in comps) > 0.4 * n_chars and min_w < 6:
            min_w += 1
            comps = _components(edges, min_w)
        if comps and max(len(c) for c in comps) > 0.4 * n_chars:
            low_purity = True

        rules = []
        for i, comp in enumerate(sorted(comps, key=lambda c: -len(c)), 1):
            members = sorted(comp, key=lambda c: -char_freq[c])
            label = "·".join(members[:3])
            comp_edges = [(k, w) for k, w in edges.items() if k[0] in comp and k[1] in comp and w >= min_w]
            comp_edges.sort(key=lambda kw: -kw[1])
            support_pids = sorted({pid for k, _ in comp_edges[:20] for pid in poems_of[k]})
            note = "韵伴聚类由近体诗偶数句尾字共现归纳，非平水韵权威表。"
            if low_purity:
                note += "（本轮聚类纯度低：通押/邻韵打通图连通性，仅供研究参考。）"
            rules.append(RhymePartnerRule(
                rhyme_rule_id=f"RPR_{i:03d}",
                label=label,
                members=members[:120],
                n_poems=len({pid for k, _ in comp_edges for pid in poems_of[k]}),
                edge_examples=[{"pair": list(k), "co_occurrence": w} for k, w in comp_edges[:10]],
                supporting_poems=support_pids[:60],
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
