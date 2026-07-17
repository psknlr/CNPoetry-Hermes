"""领域引擎：规则库装载 + 荐诗/对比/教学/全息/研究。

Engine 是所有工具与服务端的共享只读核心：一次装载 poems 与全部规则
资产，提供带证据的领域操作。所有返回值都是可 JSON 化的 dict，
且凡涉及论断处均携带 poem_id 与 quote。
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Dict, List, Optional

from .. import config
from ..corpus import normalize, sources
from ..extract import metrics as metrics_mod
from ..lexicon import IMAGERY, MOOD_HINTS, THEMES, IMAGERY_SURFACE, EMOTION_SURFACE
from ..rag.poem_rag import PoemRAG
from ..schemas import Poem, read_jsonl
from ..textutil import t2s


class Engine:
    """只读领域核心（懒加载单例见 get_engine）。"""

    def __init__(self):
        self.poems: List[Poem] = normalize.load_poems()
        if not self.poems:
            from ..health import MissingAssetsError
            raise MissingAssetsError(
                "规则库未生成：请先运行 `python3 -m hermes_poetry pipeline`，"
                f"或设 HERMES_POETRY_DATA 指向数据目录（当前 {config.DATA_DIR}）。")
        self.by_id: Dict[str, Poem] = {p.poem_id: p for p in self.poems}
        self.rag = PoemRAG(self.poems, cache_fingerprint=self._corpus_fingerprint())
        self.imagery_profiles = {r["imagery"]: r for r in read_jsonl(config.RULES_IMAGERY_DIR / "imagery_profiles.jsonl")}
        self.theme_profiles = {r["theme"]: r for r in read_jsonl(config.RULES_THEME_DIR / "theme_profiles.jsonl")}
        self.cipai_profiles = {t2s(r["cipai"]): r for r in read_jsonl(config.RULES_CIPAI_DIR / "cipai_profiles.jsonl")}
        self.author_profiles = {t2s(r["author"]): r for r in read_jsonl(config.RULES_AUTHOR_DIR / "author_profiles.jsonl")}
        self.rhyme_rules = read_jsonl(config.RULES_RHYME_DIR / "rhyme_partners.jsonl")
        self.intertext_rules = read_jsonl(config.RULES_INTERTEXT_DIR / "intertext_rules.jsonl")
        self.external = {str(e.get("id")): e for e in sources.load_external_analysis()}
        self.shuowen = sources.load_shuowen()
        self.erya = sources.load_erya_glosses()
        self._erya_index: Dict[str, List[int]] = {}
        for i, g in enumerate(self.erya):
            for m in g["members"]:
                if len(m) == 1:
                    self._erya_index.setdefault(t2s(m), []).append(i)
        self._ext_by_poem: Dict[str, Dict] = {}
        for r in read_jsonl(config.RULES_INITIAL_DIR / "initial_rules.jsonl"):
            if r.get("rule_type") == "external_analysis_rule":
                ext = self.external.get(str(r["if_conditions"].get("external_id", "")))
                if ext:
                    self._ext_by_poem[r["poem_id"]] = ext
        try:
            self.manifest = json.loads((config.MANIFEST_DIR / "corpus_manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.manifest = {}

    @staticmethod
    def _corpus_fingerprint() -> str:
        """poems.jsonl 的轻量指纹（大小+mtime），语料变更即缓存失效。"""
        try:
            st = (config.POEM_DIR / "poems.jsonl").stat()
            return f"{st.st_size}:{int(st.st_mtime)}"
        except OSError:
            return ""

    # ── 基础 ────────────────────────────────────────────────────
    def resolve_poem(self, ref: str) -> Optional[Poem]:
        ref = (ref or "").strip()
        if ref in self.by_id:
            return self.by_id[ref]
        import re
        m = re.search(r"CNP_[A-Z0-9]+_\d{5}", ref)
        if m and m.group(0) in self.by_id:
            return self.by_id[m.group(0)]
        title = ref.strip("《》〈〉")
        hits = self.rag.search(f"《{title}》", top_k=1)
        if hits and hits[0]["match_source"] == "direct_title":
            return self.by_id[hits[0]["poem_id"]]
        # 模糊题名回退：语料题名常带组诗编号（如「月下獨酌四首 一」）
        title_s = t2s(title)
        if len(title_s) >= 2:
            prefix_matches = [ps[0] for ts, ps in self.rag._title_index.items()
                              if ts.startswith(title_s) or title_s in ts]
            if prefix_matches:
                curated = [p for p in prefix_matches
                           if p.source in ("TANG300", "SONGCI300", "QIANJIA") or p.also_in]
                return (curated or prefix_matches)[0]
        return None

    def stats(self) -> Dict:
        return {
            "poems": len(self.poems),
            "sources": {k: v for k, v in (self.manifest.get("per_source") or {}).items()},
            "form_distribution": self.manifest.get("form_distribution", {}),
            "rules": self.manifest.get("rules", {}),
            "imagery_profiles": len(self.imagery_profiles),
            "theme_profiles": len(self.theme_profiles),
            "cipai_profiles": len(self.cipai_profiles),
            "author_profiles": len(self.author_profiles),
            "rhyme_groups": len(self.rhyme_rules),
            "intertext_rules": len(self.intertext_rules),
            "external_analysis_linked": len(self._ext_by_poem),
        }

    # ── 情境荐诗 ─────────────────────────────────────────────────
    def match(self, mood: str = "", imagery: Optional[List[str]] = None,
              themes: Optional[List[str]] = None, top_k: int = 6) -> Dict:
        want_imagery = list(imagery or [])
        want_themes = list(themes or [])
        want_emotions: List[str] = []
        folded = t2s(mood or "")
        for key, hint in MOOD_HINTS.items():
            if key in folded:
                want_imagery += [x for x in hint["imagery"] if x not in want_imagery]
                want_themes += [x for x in hint["themes"] if x not in want_themes]
                want_emotions += [x for x in hint["emotions"] if x not in want_emotions]
        # 直接意象/情感词命中
        for surface, canon in IMAGERY_SURFACE:
            if surface in folded and canon not in want_imagery:
                want_imagery.append(canon)
        for marker, cat in EMOTION_SURFACE:
            if marker in folded and cat not in want_emotions:
                want_emotions.append(cat)
        for theme, spec in THEMES.items():
            if any(m in folded for m in spec["markers"]) and theme not in want_themes:  # type: ignore[index]
                want_themes.append(theme)

        scored = []
        for p in self.poems:
            s = 0.0
            img_hit = [c for c in want_imagery if c in p.imagery]
            s += 2.0 * len(img_hit)
            th_hit = [t for t in want_themes if t in p.themes]
            s += 3.0 * len(th_hit)
            emo_hit = [e for e in want_emotions if e in p.emotions]
            s += 1.5 * len(emo_hit)
            if s <= 0:
                continue
            if p.source in ("TANG300", "SONGCI300", "QIANJIA") or p.also_in:
                s += 1.0
            scored.append((s, p, img_hit, th_hit, emo_hit))
        scored.sort(key=lambda x: (-x[0], x[1].poem_id))
        recs = []
        for s, p, img_hit, th_hit, emo_hit in scored[:top_k]:
            quote = ""
            surfaces = [sf for c in img_hit for sf in IMAGERY.get(c, [])]
            for ln in p.lines:
                if any(sf in t2s(ln) for sf in surfaces):
                    quote = ln
                    break
            recs.append({
                "poem_id": p.poem_id, "title": p.title, "author": p.author,
                "dynasty": p.dynasty, "genre": p.genre,
                "quote": quote or (p.lines[0] if p.lines else ""),
                "matched_imagery": img_hit, "matched_themes": th_hit,
                "matched_emotions": emo_hit, "score": round(s, 2), "layer": "A",
            })
        return {
            "query": {"mood": mood, "imagery": want_imagery, "themes": want_themes,
                      "emotions": want_emotions},
            "recommendations": recs,
        }

    # ── 对比鉴赏 ─────────────────────────────────────────────────
    def differential(self, refs: List[str]) -> Dict:
        poems = [p for p in (self.resolve_poem(r) for r in refs) if p]
        if len(poems) < 2:
            return {"error": "需要至少两首可解析的作品（poem_id 或《题名》）。"}
        rows = []
        rows.append({"axis": "体裁（B层）", "detail": "；".join(
            f"《{p.title}》{p.genre}（{p.metrics.get('line_count')}句，"
            f"{metrics_mod.char_pattern(p.metrics.get('char_counts', []))}）" for p in poems)})
        img_sets = [set(p.imagery) for p in poems]
        shared = sorted(set.intersection(*img_sets)) if img_sets else []
        rows.append({"axis": "共有意象", "detail": "、".join(shared) or "无"})
        for p, imgs in zip(poems, img_sets):
            uniq = sorted(imgs - set.union(*(s for s in img_sets if s is not imgs))) if len(img_sets) > 1 else sorted(imgs)
            rows.append({"axis": f"《{p.title}》独有意象", "detail": "、".join(uniq) or "无"})
        rows.append({"axis": "题材", "detail": "；".join(
            f"《{p.title}》：{'、'.join(p.themes) or '未判定'}" for p in poems)})
        rows.append({"axis": "情感标记", "detail": "；".join(
            f"《{p.title}》：{'、'.join(p.emotions) or '未检出'}" for p in poems)})
        # 互文
        ids = {p.poem_id for p in poems}
        inter = [r for r in self.intertext_rules
                 if r["source_poem_id"] in ids and r["target_poem_id"] in ids]
        if inter:
            rows.append({"axis": "互文（逐字复用）", "detail": "；".join(
                f"{r['mode']}「{r['shared_span']}」" for r in inter[:3])})
        return {
            "poems": [{"poem_id": p.poem_id, "title": p.title, "author": p.author,
                       "dynasty": p.dynasty, "lines": p.lines} for p in poems],
            "contrast": rows,
        }

    # ── 教学 ─────────────────────────────────────────────────────
    def teach(self, topic: str) -> Dict:
        topic_s = t2s((topic or "").strip())
        # 题材教学
        for theme, prof in self.theme_profiles.items():
            if theme in topic_s or topic_s == theme:
                reps = [{**e, "author": self.by_id[e["poem_id"]].author if e["poem_id"] in self.by_id else ""}
                        for e in prof.get("example_evidence", [])[:6]]
                return {"lesson": {
                    "type": "theme", "topic": theme,
                    "outline": f"题材「{theme}」：{prof.get('definition','')}（语料 {prof.get('n_poems')} 首）",
                    "markers": prof.get("marker_terms", [])[:12],
                    "top_imagery": prof.get("top_imagery", [])[:8],
                    "dynasty_distribution": prof.get("dynasty_distribution", {}),
                    "representative": reps,
                    "exercise": f"练习：从代表作中任选一首，找出指向「{theme}」的标记词并核对原文。",
                }}
        # 体裁教学
        genre_pool = [p for p in self.poems if p.genre == topic_s]
        if genre_pool:
            curated = [p for p in genre_pool if p.source in ("TANG300", "SONGCI300", "QIANJIA") or p.also_in]
            reps = (curated or genre_pool)[:6]
            n = len(genre_pool)
            sample = reps[0]
            pattern = metrics_mod.char_pattern(sample.metrics.get("char_counts", []))
            return {"lesson": {
                "type": "genre", "topic": topic_s,
                "outline": f"体裁「{topic_s}」：语料 {n} 首；典型句式如《{sample.title}》为 {pattern}。"
                           "（体裁判定为 B 层计量近似，语料标签优先。）",
                "representative": [{"poem_id": p.poem_id, "title": p.title, "author": p.author,
                                   "quote": p.lines[0] if p.lines else ""} for p in reps],
                "exercise": "练习：数一数代表作的句数与每句字数，验证体裁判定。",
            }}
        # 意象教学
        for canon in IMAGERY:
            if canon in topic_s:
                prof = self.imagery_profiles.get(canon)
                if prof:
                    return {"lesson": {
                        "type": "imagery", "topic": canon,
                        "outline": f"意象「{canon}」：{prof['n_poems']} 首支撑；"
                                   "情感关联为语料归纳，同一意象可承载相反情感。",
                        "associations": prof.get("emotion_associations", [])[:5],
                        "representative": [
                            {"poem_id": a["example"]["poem_id"], "title": a["example"].get("title", ""),
                             "quote": a["example"]["quote"], "author": ""}
                            for a in prof.get("emotion_associations", [])[:5]],
                        "exercise": f"练习：在代表句中指出「{canon}」的表面形式与同现情感标记。",
                    }}
        # 作者教学
        prof = self.author_profiles.get(topic_s)
        if prof:
            reps = [{**r, "quote": (self.by_id[r["poem_id"]].lines[0] if r["poem_id"] in self.by_id and self.by_id[r["poem_id"]].lines else ""), "author": prof["author"]}
                    for r in prof.get("representative_poems", [])[:6]]
            return {"lesson": {
                "type": "author", "topic": prof["author"],
                "outline": f"诗人「{prof['author']}」（{prof['dynasty']}）：语料 {prof['n_poems']} 首；"
                           f"高频意象 {'、'.join(x['imagery'] for x in prof.get('top_imagery', [])[:5])}。",
                "bio": prof.get("bio", "")[:300],
                "representative": reps,
                "exercise": "练习：任选两首代表作，比较其意象与题材。",
            }}
        return {"error": f"未找到可教学的主题「{topic}」。可选：题材（{'、'.join(list(self.theme_profiles)[:5])}…）、"
                         f"体裁（五绝/七律/词…）、意象（月/柳/雁…）或诗人名。"}

    # ── 作品全息 ─────────────────────────────────────────────────
    def explain_poem(self, ref: str) -> Dict:
        p = self.resolve_poem(ref)
        if p is None:
            return {"error": f"无法解析作品「{ref}」（可用 poem_id 或《题名》）。"}
        related_intertext = [r for r in self.intertext_rules
                             if p.poem_id in (r["source_poem_id"], r["target_poem_id"])][:6]
        ext = self._ext_by_poem.get(p.poem_id)
        author_prof = self.author_profiles.get(t2s(p.author))
        return {
            "poem": {
                "poem_id": p.poem_id, "title": p.title, "author": p.author,
                "dynasty": p.dynasty, "book": p.book, "cipai": p.cipai,
                "section": p.section, "genre": p.genre, "lines": p.lines,
                "tags": p.tags, "also_in": p.also_in, "layer": "A",
            },
            "metrics": {**metrics_mod.describe(p), "layer": "B"},
            "imagery": p.imagery,
            "emotions": p.emotions,
            "themes": p.themes,
            "notes": [{"text": n, "layer": "C"} for n in p.notes[:20]],
            "appreciation": ({"text": p.appreciation, "layer": "C", "source": "水墨唐诗白话导读"}
                             if p.appreciation else None),
            "author_bio": ({"text": author_prof.get("bio", "")[:400], "layer": "C"}
                           if author_prof and author_prof.get("bio") else None),
            "external_analysis": ({"layer": "D", "dataset": "PoetryMTEB(DeepSeek-V3.1)",
                                   "subject": ext.get("subject"), "theme": ext.get("theme"),
                                   "emotion": ext.get("emotion"),
                                   "note": "外部LLM生成，非本系统结论"} if ext else None),
            "intertext": [{"mode": r["mode"], "shared_span": r["shared_span"],
                           "other": (r["target_poem_id"] if r["source_poem_id"] == p.poem_id
                                     else r["source_poem_id"])} for r in related_intertext],
        }

    # ── 韵伴与互文查询 ────────────────────────────────────────────
    def rhyme_query(self, char: str = "", poem_ref: str = "") -> Dict:
        if poem_ref:
            p = self.resolve_poem(poem_ref)
            if p is None:
                return {"error": f"无法解析作品「{poem_ref}」。"}
            feet = (p.metrics or {}).get("rhyme_feet", [])
            groups = [r for r in self.rhyme_rules if any(t2s(f) in r["members"] for f in feet)]
            return {"poem_id": p.poem_id, "rhyme_feet": feet,
                    "groups": groups[:3], "layer": "B",
                    "note": "韵伴聚类为语料归纳，非平水韵权威表。"}
        ch = t2s((char or "").strip())[:1]
        groups = [r for r in self.rhyme_rules if ch in r["members"]]
        return {"char": ch, "groups": groups[:3],
                "note": "韵伴聚类为语料归纳，非平水韵权威表。"}

    def intertext_query(self, poem_ref: str = "", text: str = "") -> Dict:
        if poem_ref:
            p = self.resolve_poem(poem_ref)
            if p is None:
                return {"error": f"无法解析作品「{poem_ref}」。"}
            pairs = [r for r in self.intertext_rules
                     if p.poem_id in (r["source_poem_id"], r["target_poem_id"])]
            return {"poem_id": p.poem_id, "pairs": pairs[:10]}
        if text:
            from ..textutil import content_only
            folded = content_only(t2s(text))
            pairs = [r for r in self.intertext_rules if folded and folded in r["shared_span"]]
            if not pairs:
                hits = self.rag.search(text, top_k=5)
                return {"text": text, "pairs": [], "nearest_poems": hits,
                        "note": "无逐字互文命中，给出最近似检索结果。"}
            return {"text": text, "pairs": pairs[:10]}
        return {"error": "需提供 poem_ref 或 text。"}

    # ── 字义训诂（C层：说文解字 + 尔雅，gujilab CC0）──────────────
    def gloss_query(self, chars: str = "", poem_ref: str = "") -> Dict:
        targets: List[str] = []
        context = ""
        if poem_ref:
            p = self.resolve_poem(poem_ref)
            if p is None:
                return {"error": f"无法解析作品「{poem_ref}」。"}
            context = p.poem_id
            from collections import Counter as _C
            from ..textutil import cjk_chars
            freq = _C(cjk_chars(p.text))
            targets = [c for c, _ in freq.most_common(8)]
        else:
            from ..textutil import cjk_chars
            targets = cjk_chars(chars)[:8]
        if not targets:
            return {"error": "需提供 chars（1-8 个汉字）或 poem_ref。"}
        entries = []
        for ch in targets:
            key = t2s(ch)
            sw = self.shuowen.get(key) or self.shuowen.get(ch)
            erya_hits = [self.erya[i] for i in self._erya_index.get(key, [])[:3]]
            entries.append({
                "char": ch,
                "shuowen": ({"headword": sw["char"], "radical": sw.get("radical", ""),
                             "fanqie": sw.get("fanqie", ""), "gloss": sw.get("gloss", "")}
                            if sw else None),
                "erya": [{"chapter": g["chapter"], "members": g["members"][:12],
                          "gloss": g["gloss"]} for g in erya_hits],
            })
        return {"glosses": entries, "poem_id": context, "layer": "C",
                "source": "说文解字/尔雅（gujilab/chinese-classical-corpus，CC0）",
                "note": "训诂为字书本义，诗中用义可能引申；本层为 C 层旁证。"}

    # ── 研究端 ───────────────────────────────────────────────────
    def research(self, topic: str = "") -> Dict:
        try:
            net = json.loads((config.NETWORK_DIR / "imagery_network.json").read_text(encoding="utf-8"))
            dyn = json.loads((config.NETWORK_DIR / "dynasty_tables.json").read_text(encoding="utf-8"))
            mat = json.loads((config.NETWORK_DIR / "emotion_imagery_matrix.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"error": "研究资产未生成，请先运行 pipeline。"}
        out = {"imagery_network_top": {"nodes": net["nodes"][:20], "edges": net["edges"][:20]},
               "dynasty_poem_counts": dyn["poem_counts"],
               "emotion_imagery_matrix": {k: v for k, v in list(mat.items())[:6]}}
        topic_s = t2s(topic or "")
        for canon in IMAGERY:
            if canon in topic_s and canon in self.imagery_profiles:
                out["focus_imagery"] = self.imagery_profiles[canon]
                break
        return out


_engine: Optional[Engine] = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


def set_engine(engine: Optional[Engine]) -> None:
    global _engine
    _engine = engine
