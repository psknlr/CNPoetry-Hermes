"""典故种子图谱（第二阶段 MVP）：候选发现 → 语境信号 →（人工/模型）确认。

铁律：**表面命中 ≠ 用典确认**。检测输出一律为 status=candidate，附
语境信号（题材相符/伴随动词/歧义提示）供下游裁决；高歧义种子
（青鸟/采薇/王孙等）带 ambiguity_note。种子数据外置于
data/raw/allusions/allusion_seeds.jsonl（版本化、含审核状态与许可，
领域专家可不改代码维护）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, List

from .. import config
from ..textutil import t2s

# 典故功能的语境信号词（出现于同句附近 → 用典概率提升）
_CONTEXT_HINTS = {
    "送别": ["送", "别", "赠", "辞"], "破敌立功": ["破", "斩", "取", "封"],
    "边功未成/建功": ["未", "勒", "归", "计"], "隐逸闲适": ["归", "隐", "菊", "酒"],
    "知己难遇": ["少", "难", "绝", "断"], "盛衰兴亡": ["旧", "空", "斜", "燕"],
}


@lru_cache(maxsize=1)
def load_seeds() -> List[Dict]:
    path = config.RAW_DIR / "allusions" / "allusion_seeds.jsonl"
    seeds: List[Dict] = []
    if not path.exists():
        return seeds
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("name") and r.get("surfaces"):
                seeds.append(r)
    return seeds


@lru_cache(maxsize=1)
def _surface_index():
    return sorted(((t2s(s), seed["name"], i)
                   for i, seed in enumerate(load_seeds()) for s in seed["surfaces"]),
                  key=lambda kv: -len(kv[0]))


def detect_allusions(text: str) -> List[Dict]:
    folded = t2s(text)
    seeds = load_seeds()
    hits, seen = [], set()
    for surface, name, idx in _surface_index():
        pos = folded.find(surface)
        if pos < 0 or name in seen:
            continue
        seen.add(name)
        seed = seeds[idx]
        # 语境信号：典故常用义的提示动词是否出现在附近（±8字）
        window = folded[max(0, pos - 8): pos + len(surface) + 8]
        hint_words = _CONTEXT_HINTS.get(seed.get("implies", ""), [])
        signals = [w for w in hint_words if w in window]
        hits.append({
            "allusion": name, "surface": surface,
            "source": seed.get("source", ""), "implies": seed.get("implies", ""),
            "status": "candidate",
            "context_signals": signals,
            "ambiguity_note": seed.get("ambiguity_note", ""),
            "seed_id": seed.get("id", ""),
            "source_level": "curated_seed",
            "note": "表面命中≠用典确认：本条为候选，须结合语境/注释/年代裁决；"
                    "「典故如何被改造」的功能判断需接入解释层。",
        })
    return hits
