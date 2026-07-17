"""纯 Python Okapi BM25（字 unigram+bigram 倒排索引），零依赖。"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import List, Tuple

from ..textutil import tokenize


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
