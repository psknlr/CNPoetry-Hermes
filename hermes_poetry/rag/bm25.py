"""纯 Python Okapi BM25（字 unigram+bigram 倒排索引），零依赖。

磁盘缓存采用扁平数组编码（CACHE_FORMAT=2）：postings 展平为
array('I') 三元组（offsets/docs/tfs），载入免去数百万小对象反序列化，
实测比 list-of-tuples pickle 快一个数量级。search 对两种存储形态
（内存 dict / 扁平数组切片）同构工作。
"""
from __future__ import annotations

import math
import pickle
from array import array
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..textutil import tokenize

CACHE_FORMAT = 2


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_ids: List[str] = []
        self.doc_len: List[int] = []
        self.tf: List[Counter] = []
        self.df: Counter = Counter()
        self.avgdl = 0.0
        self._postings: Optional[Dict[str, List[Tuple[int, int]]]] = None
        # 扁平存储（缓存载入形态）
        self._flat_ranges: Optional[Dict[str, Tuple[int, int]]] = None
        self._flat_docs: Optional[array] = None
        self._flat_tfs: Optional[array] = None

    def add(self, doc_id: str, text: str) -> None:
        toks = tokenize(text)
        self.doc_ids.append(doc_id)
        self.doc_len.append(len(toks))
        counts = Counter(toks)
        self.tf.append(counts)
        for t in counts:
            self.df[t] += 1

    def finalize(self) -> None:
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        self._postings = defaultdict(list)
        for i, counts in enumerate(self.tf):
            for t, c in counts.items():
                self._postings[t].append((i, c))
        self.tf = []  # 词频表只在建索引期需要，及时释放

    # ── 磁盘缓存（扁平数组编码）─────────────────────────────────
    def dump(self, path: Path, fingerprint: str = "") -> None:
        if self._postings is None and self._flat_ranges is None:
            self.finalize()
        terms: List[str] = []
        offsets = array("I", [0])
        docs = array("I")
        tfs = array("I")
        if self._postings is not None:
            for t in sorted(self._postings):
                terms.append(t)
                for i, c in self._postings[t]:
                    docs.append(i)
                    tfs.append(c)
                offsets.append(len(docs))
        payload = {
            "format": CACHE_FORMAT, "fingerprint": fingerprint,
            "doc_ids": self.doc_ids, "doc_len": array("I", self.doc_len).tobytes(),
            "avgdl": self.avgdl, "terms": terms,
            "offsets": offsets.tobytes(), "docs": docs.tobytes(), "tfs": tfs.tobytes(),
        }
        tmp = path.with_suffix(".tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path, fingerprint: str = "") -> Optional["BM25Index"]:
        try:
            with path.open("rb") as fh:
                payload = pickle.load(fh)
        except (OSError, pickle.UnpicklingError, EOFError):
            return None
        if payload.get("format") != CACHE_FORMAT or payload.get("fingerprint") != fingerprint:
            return None
        idx = cls()
        idx.doc_ids = payload["doc_ids"]
        doc_len = array("I")
        doc_len.frombytes(payload["doc_len"])
        idx.doc_len = list(doc_len)
        idx.avgdl = payload["avgdl"]
        offsets = array("I")
        offsets.frombytes(payload["offsets"])
        docs = array("I")
        docs.frombytes(payload["docs"])
        tfs = array("I")
        tfs.frombytes(payload["tfs"])
        idx._flat_docs, idx._flat_tfs = docs, tfs
        idx._flat_ranges = {t: (offsets[i], offsets[i + 1])
                            for i, t in enumerate(payload["terms"])}
        return idx

    # ── 检索 ─────────────────────────────────────────────────────
    def _term_postings(self, t: str):
        if self._flat_ranges is not None:
            rng = self._flat_ranges.get(t)
            if rng is None:
                return None
            s, e = rng
            return zip(self._flat_docs[s:e], self._flat_tfs[s:e])
        if self._postings is None:
            self.finalize()
        return self._postings.get(t)

    def _term_df(self, t: str) -> int:
        if self._flat_ranges is not None:
            rng = self._flat_ranges.get(t)
            return (rng[1] - rng[0]) if rng else 0
        return self.df.get(t, 0)

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        q_toks = set(tokenize(query))
        n_docs = len(self.doc_ids)
        scores = defaultdict(float)
        for t in q_toks:
            postings = self._term_postings(t)
            if not postings:
                continue
            df = self._term_df(t)
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            for i, tf in postings:
                dl = self.doc_len[i] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * tf * (self.k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        return [(self.doc_ids[i], round(s, 4)) for i, s in ranked]
