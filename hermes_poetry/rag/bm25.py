"""纯 Python Okapi BM25（字 unigram+bigram 倒排索引），零依赖。

支持 dump/load 磁盘缓存：finalize 后检索只依赖倒排表与文档长度，
序列化时剔除逐文档词频表（tf）以缩小体积、加快冷启动。
"""
from __future__ import annotations

import math
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional, Tuple

from ..textutil import tokenize

CACHE_FORMAT = 1


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_ids: List[str] = []
        self.doc_len: List[int] = []
        self.tf: List[Counter] = []
        self.df: Counter = Counter()
        self.avgdl = 0.0
        self._postings = None

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

    def dump(self, path: Path, fingerprint: str = "") -> None:
        if self._postings is None:
            self.finalize()
        payload = {"format": CACHE_FORMAT, "fingerprint": fingerprint,
                   "doc_ids": self.doc_ids, "doc_len": self.doc_len,
                   "df": dict(self.df), "avgdl": self.avgdl,
                   "postings": dict(self._postings)}
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
        idx.doc_len = payload["doc_len"]
        idx.df = Counter(payload["df"])
        idx.avgdl = payload["avgdl"]
        idx._postings = payload["postings"]
        return idx

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        if self._postings is None:
            self.finalize()
        q_toks = set(tokenize(query))
        n_docs = len(self.doc_ids)
        scores = defaultdict(float)
        for t in q_toks:
            postings = self._postings.get(t)
            if not postings:
                continue
            idf = math.log(1 + (n_docs - self.df[t] + 0.5) / (self.df[t] + 0.5))
            for i, tf in postings:
                dl = self.doc_len[i] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * tf * (self.k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        return [(self.doc_ids[i], round(s, 4)) for i, s in ranked]
