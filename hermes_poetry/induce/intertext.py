"""互文检测：跨诗逐字复用（重出互见/袭用/化用）。

移植伤寒-赫尔墨斯 quotation 层的 n-gram 倒排 + 对角线合并算法：
  * 5-gram 倒排索引（简体折叠、仅 CJK）；出现于 >0.5% 诗篇的
    高频 gram 视为套语剪除（如「万里」「不知」类）；
  * 命中点按对角线 (p - c) 合并成连续 run；
  * 分级：run≥10 且几乎全篇 → 重出互见；run≥7 → 袭用（逐字）；
    run 5–6 → 化用（部分逐字）。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from .. import config
from ..schemas import IntertextRule, Poem, write_jsonl
from ..textutil import content_only, t2s

SHINGLE = 5


class IntertextMiner:
    def __init__(self, poems: List[Poem]):
        self.poems = poems
        self.folded: Dict[str, str] = {p.poem_id: content_only(t2s(p.text)) for p in poems}
        self.index: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        cap = max(20, int(0.005 * len(poems)))
        counts: Dict[str, int] = defaultdict(int)
        for pid, text in self.folded.items():
            seen = set()
            for i in range(len(text) - SHINGLE + 1):
                g = text[i:i + SHINGLE]
                if g not in seen:
                    counts[g] += 1
                    seen.add(g)
        self._generic = {g for g, c in counts.items() if c > cap}
        for pid, text in self.folded.items():
            for i in range(len(text) - SHINGLE + 1):
                g = text[i:i + SHINGLE]
                if g not in self._generic:
                    self.index[g].append((pid, i))

    def _runs_between(self, a_text: str, b_hits: Dict[str, List[Tuple[int, int]]]):
        """b_poem_id → [(a_start, b_start, len)]（对角线合并）。"""
        merged: Dict[str, List[Tuple[int, int, int]]] = {}
        for pid, points in b_hits.items():
            by_diag: Dict[int, List[int]] = defaultdict(list)
            for pa, pb in points:
                by_diag[pa - pb].append(pa)
            runs = []
            for diag, starts in by_diag.items():
                starts.sort()
                run_start, prev = starts[0], starts[0]
                for s in starts[1:]:
                    if s <= prev + SHINGLE:
                        prev = s
                    else:
                        runs.append((run_start, run_start - diag, prev - run_start + SHINGLE))
                        run_start, prev = s, s
                runs.append((run_start, run_start - diag, prev - run_start + SHINGLE))
            merged[pid] = runs
        return merged

    def run(self, max_rules: int = 4000) -> List[IntertextRule]:
        rules: List[IntertextRule] = []
        seen_pairs = set()
        seq = 0
        for poem in self.poems:
            a_id = poem.poem_id
            a_text = self.folded[a_id]
            if len(a_text) < SHINGLE:
                continue
            hits: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
            for i in range(len(a_text) - SHINGLE + 1):
                g = a_text[i:i + SHINGLE]
                for pid, off in self.index.get(g, ()):  # 已剪除高频 gram
                    if pid != a_id:
                        hits[pid].append((i, off))
            for b_id, runs in self._runs_between(a_text, hits).items():
                pair = tuple(sorted((a_id, b_id)))
                if pair in seen_pairs:
                    continue
                best = max(runs, key=lambda r: r[2])
                span_len = best[2]
                if span_len < SHINGLE:
                    continue
                seen_pairs.add(pair)
                span = a_text[best[0]:best[0] + span_len]
                b_len = len(self.folded[b_id])
                coverage = span_len / max(1, min(len(a_text), b_len))
                if span_len >= 10 and coverage >= 0.8:
                    mode = "重出互见"
                elif span_len >= 7:
                    mode = "袭用"
                else:
                    mode = "化用"
                seq += 1
                rules.append(IntertextRule(
                    intertext_rule_id=f"ITR_{seq:05d}",
                    source_poem_id=pair[0],
                    target_poem_id=pair[1],
                    shared_span=span,
                    span_len=span_len,
                    similarity=round(coverage, 3),
                    mode=mode,
                ))
                if len(rules) >= max_rules:
                    return rules
        return rules

def persist_intertext(rules: List[IntertextRule]) -> None:
    write_jsonl(config.RULES_INTERTEXT_DIR / "intertext_rules.jsonl", rules)
