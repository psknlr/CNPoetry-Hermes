"""作品检索：直接引用捷径 + 结构化过滤 + BM25 候选池 + 覆盖度重排 + 意象扩展。

设计（承袭伤寒-赫尔墨斯 ClauseRAG）：
  * 《题名》/ poem_id / 「作者 题名」直接命中，score=99；
  * 结构化过滤：朝代/作者/体裁/词牌/集子；
  * BM25 先取 5× 候选池并归一到 0–10 分带，再按查询意象与题材
    覆盖度重排——命中全部查询意象的诗胜过只命中一半的诗；
  * --expand：查询中的意象规范名展开其全部表面形式增强召回。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..lexicon import IMAGERY, IMAGERY_SURFACE, THEME_SURFACE
from ..schemas import Poem
from ..textutil import normalize_query, t2s
from .bm25 import BM25Index

RE_TITLE_REF = re.compile(r"[《〈]([^》〉]{1,20})[》〉]")
RE_POEM_ID_Q = re.compile(r"CNP_[A-Z0-9]+_\d{5}")


class PoemRAG:
    def __init__(self, poems: List[Poem], cache_fingerprint: str = ""):
        self.poems = poems
        self.by_id: Dict[str, Poem] = {p.poem_id: p for p in poems}
        self._title_index: Dict[str, List[Poem]] = {}
        self._author_index: Dict[str, List[Poem]] = {}
        self._cipai_names: List[str] = []
        cipai_seen = set()
        for p in poems:
            self._title_index.setdefault(t2s(p.title), []).append(p)
            self._author_index.setdefault(t2s(p.author), []).append(p)
            if p.cipai:
                cs = t2s(p.cipai)
                if len(cs) >= 2 and cs not in cipai_seen:
                    cipai_seen.add(cs)
                    self._cipai_names.append(cs)
        self._cipai_names.sort(key=len, reverse=True)
        self.index = self._build_index(cache_fingerprint)

    def _build_index(self, fingerprint: str) -> BM25Index:
        from .. import config
        cache_path = config.INDEX_DIR / "bm25_poems.pkl"
        if fingerprint:
            cached = BM25Index.load(cache_path, fingerprint)
            if cached is not None and len(cached.doc_ids) == len(self.poems):
                return cached
        index = BM25Index()
        for p in self.poems:
            index.add(p.poem_id, f"{p.title} {p.author} {p.cipai} {t2s(p.text)}")
        index.finalize()
        if fingerprint:
            try:
                index.dump(cache_path, fingerprint)
            except OSError:
                pass
        return index

    # ── 公共查询接口（外部模块勿触私有索引，便于后续更换存储后端）──
    def find_by_title(self, title: str) -> List[Poem]:
        return list(self._title_index.get(t2s((title or "").strip("《》〈〉")), []))

    def find_by_author(self, author: str) -> List[Poem]:
        return list(self._author_index.get(t2s((author or "").strip()), []))

    def has_author(self, author: str) -> bool:
        return bool(self._author_index.get(t2s((author or "").strip())))

    def titles_containing(self, title_s: str, prefix_only: bool = False) -> List[Poem]:
        out = []
        for ts, ps in self._title_index.items():
            if ts.startswith(title_s) or (not prefix_only and title_s in ts):
                out.append(ps[0])
        return out

    # ── 查询解析 ────────────────────────────────────────────────
    def _query_imagery(self, q: str) -> List[str]:
        found, taken = [], [False] * len(q)
        for surface, canon in IMAGERY_SURFACE:
            idx = q.find(surface)
            if idx >= 0 and not any(taken[idx:idx + len(surface)]):
                for i in range(idx, idx + len(surface)):
                    taken[i] = True
                if canon not in found:
                    found.append(canon)
        return found

    def _expand_query(self, q: str, imagery: List[str]) -> str:
        extra = []
        for canon in imagery:
            extra.extend(IMAGERY.get(canon, [])[:6])
        return q + " " + " ".join(extra)

    # ── 主检索 ──────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 8, dynasty: str = "", author: str = "",
               genre: str = "", cipai: str = "", source: str = "",
               expand: bool = False) -> List[Dict]:
        q = normalize_query(query)

        # 捷径一：poem_id
        m = RE_POEM_ID_Q.search(query)
        if m and m.group(0) in self.by_id:
            return [self._hit(self.by_id[m.group(0)], 99.0, "direct_id")]
        # 捷径二：《题名》（多个书名号全部解析——对比类查询不丢作品）
        titles = RE_TITLE_REF.findall(query)
        if titles:
            all_hits = []
            rest = normalize_query(RE_TITLE_REF.sub("", query))
            for ttl in titles:
                cands = self._title_index.get(t2s(ttl), [])
                if len(cands) > 1 and rest:
                    cands = [p for p in cands if t2s(p.author) in rest] or cands
                all_hits.extend(self._hit(p, 99.0, "direct_title") for p in cands[:3])
            if all_hits:
                return all_hits[:max(top_k, len(titles))]

        # 结构化过滤
        def passes(p: Poem) -> bool:
            if dynasty and p.dynasty != dynasty:
                return False
            if author and t2s(author) != t2s(p.author):
                return False
            if genre and p.genre != genre:
                return False
            if cipai and t2s(cipai) != t2s(p.cipai):
                return False
            if source and source not in (p.source, p.book):
                return False
            return True

        # 词牌名先从查询中剥离，避免「浣溪沙」被当作意象/内容词解析
        q_for_parse = q
        for cn in self._cipai_names:
            if cn in q_for_parse:
                q_for_parse = q_for_parse.replace(cn, " ")
                if not cipai:
                    cipai = cn
        q_imagery = self._query_imagery(q_for_parse)
        # 题材标记：单字标记（溪/禅类）误命中率高，只认 ≥2 字标记
        q_themes = [theme for m2, theme in THEME_SURFACE if len(m2) >= 2 and m2 in q_for_parse]
        bm_query = self._expand_query(q, q_imagery) if expand else q
        # 过滤器激活时扩大候选池，防止过滤后召回崩塌
        filters_active = bool(dynasty or author or genre or cipai or source)
        pool_size = 600 if filters_active else max(top_k * 5, 40)
        pool = self.index.search(bm_query, top_k=pool_size)
        bm_max = pool[0][1] if pool else 1.0
        hits = []
        for pid, bm in pool:
            p = self.by_id[pid]
            if not passes(p):
                continue
            score = 10.0 * bm / (bm_max or 1.0)
            # 意象覆盖度（组合信号主导重排）
            if q_imagery:
                matched = sum(1 for c in q_imagery if c in p.imagery)
                cov = matched / len(q_imagery)
                score += 4.0 if cov == 1.0 else (2.0 if cov >= 0.5 else (0.5 if cov > 0 else 0.0))
            if q_themes:
                tm_n = sum(1 for t in set(q_themes) if t in p.themes)
                score += 1.0 * tm_n
            if t2s(p.author) and t2s(p.author) in q:
                score += 3.0
            if p.title and t2s(p.title) in q:
                score += 3.0
            if p.source in ("TANG300", "SONGCI300", "QIANJIA") or p.also_in:
                score += 0.5  # 精选集微幅加权（经典度先验）
            hits.append(self._hit(p, round(score, 3), "bm25+rerank", q_imagery=q_imagery))
        # 作者名单独查询（BM25 池可能不含其全部作品）
        if not hits and t2s(query.strip()) in self._author_index:
            for p in self._author_index[t2s(query.strip())][:top_k]:
                hits.append(self._hit(p, 50.0, "author_index"))
        hits.sort(key=lambda h: -h["score"])
        # 结果去重：同一作品的重出互见/异文变体只占一个名额
        deduped, seen_keys = [], set()
        for h in hits:
            p = self.by_id[h["poem_id"]]
            key = f"{t2s(p.author)}|{t2s(p.title)[:8]}|{t2s(p.text)[:10]}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(h)
        return deduped[:top_k]

    def _best_quote(self, p: Poem, q_imagery: List[str]) -> str:
        if q_imagery:
            surfaces = [s for c in q_imagery for s in IMAGERY.get(c, [])]
            for ln in p.lines:
                folded = t2s(ln)
                if any(s in folded for s in surfaces):
                    return ln
        return p.lines[0] if p.lines else ""

    def _hit(self, p: Poem, score: float, match_source: str, q_imagery: Optional[List[str]] = None) -> Dict:
        return {
            "poem_id": p.poem_id,
            "title": p.title,
            "author": p.author,
            "dynasty": p.dynasty,
            "book": p.book,
            "genre": p.genre,
            "cipai": p.cipai,
            "quote": self._best_quote(p, q_imagery or []),
            "imagery": p.imagery[:8],
            "themes": p.themes,
            "score": score,
            "match_source": match_source,
            "layer": "A",
        }
