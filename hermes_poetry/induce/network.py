"""意象共现网络与研究端统计资产（确定性、可复现）。"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Dict, List

from .. import config
from ..schemas import Poem


def build_network(poems: List[Poem]) -> Dict:
    from itertools import combinations
    node_freq: Counter = Counter()
    edges: Counter = Counter()
    for p in poems:
        imgs = sorted(set(p.imagery))
        node_freq.update(imgs)
        for a, b in combinations(imgs, 2):
            edges[(a, b)] += 1
    top_edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in edges.most_common(200) if w >= 3
    ]
    return {
        "nodes": [{"imagery": k, "count": v} for k, v in node_freq.most_common(80)],
        "edges": top_edges,
        "n_poems": len(poems),
    }


def dynasty_tables(poems: List[Poem]) -> Dict:
    by_dyn: Dict[str, Counter] = defaultdict(Counter)
    dyn_count: Counter = Counter()
    for p in poems:
        dyn_count[p.dynasty] += 1
        by_dyn[p.dynasty].update(p.imagery)
    order = [d for d in config.DYNASTY_ORDER if d in dyn_count] + \
            [d for d in dyn_count if d not in config.DYNASTY_ORDER]
    return {
        "poem_counts": {d: dyn_count[d] for d in order},
        "top_imagery_by_dynasty": {d: dict(by_dyn[d].most_common(10)) for d in order},
    }


def emotion_imagery_matrix(poems: List[Poem]) -> Dict:
    matrix: Dict[str, Counter] = defaultdict(Counter)
    for p in poems:
        for e in p.emotions:
            matrix[e].update(p.imagery)
    return {e: dict(c.most_common(10)) for e, c in matrix.items()}


def build_all(poems: List[Poem]) -> Dict:
    config.NETWORK_DIR.mkdir(parents=True, exist_ok=True)
    net = build_network(poems)
    dyn = dynasty_tables(poems)
    mat = emotion_imagery_matrix(poems)
    for name, obj in [("imagery_network.json", net), ("dynasty_tables.json", dyn),
                      ("emotion_imagery_matrix.json", mat)]:
        (config.NETWORK_DIR / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"network_nodes": len(net["nodes"]), "network_edges": len(net["edges"])}
