"""创作实验室（第三阶段 MVP）：格律辅助，永远标注「今人拟作」。

能力：平仄模板（近体标准谱）、韵部候选字（平水韵/词林正韵，来源分层）、
意象建议（语料档案，可排除）、陈词提醒（语料高频五言句头）、逐句检查。
守卫：不代拟古人署名；输出显式创作声明。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..textutil import cjk_chars, t2s

# 近体标准谱（首句不入韵式；○平 ●仄 ◎可平可仄）
TEMPLATES = {
    "五绝": ["◎●○○●", "○○◎●○", "◎○○●●", "◎●●○○"],
    "七绝": ["◎●◎○○●●", "◎○◎●●○○", "◎○◎●○○●", "◎●○○◎●○"],
    "五律": ["◎●○○●", "○○◎●○", "◎○○●●", "◎●●○○"] * 2,
    "七律": ["◎●◎○○●●", "◎○◎●●○○", "◎○◎●○○●", "◎●○○◎●○"] * 2,
}


def compose_helper(genre: str = "七绝", rhyme_char: str = "", mood: str = "",
                   avoid_imagery: Optional[List[str]] = None, engine=None) -> Dict:
    from .engine import get_engine
    from ..extract.phonology import get_phonology, pingshui_of, cilin_of
    engine = engine or get_engine()
    ph = get_phonology()
    genre = t2s(genre.strip()) or "七绝"
    out: Dict = {
        "declaration": "【创作声明】本工具输出为今人拟作辅助，不得伪托古人作品；"
                       "引用的古典例句均逐字回源。",
        "genre": genre,
        "template": TEMPLATES.get(genre, TEMPLATES["七绝"]),
        "template_note": "标准谱（首句不入韵式）；○平●仄◎可平可仄，依《广韵》口径",
    }
    # 韵部候选：给定韵脚字 → 平水韵部 + 同部常用字（取语料韵伴组交集保常用度）
    if rhyme_char:
        ch = t2s(rhyme_char.strip())[:1]
        gys = sorted({r["yun"] for r in ph.char_readings(ch)})
        pss = sorted({pingshui_of(y) for y in gys if pingshui_of(y)})
        same_bu: List[str] = []
        groups = [g for g in engine.rhyme_rules if ch in g["members"]]
        for g in groups:
            for m in g["members"]:
                m_ps = {pingshui_of(y) for r in ph.char_readings(m) for y in [r["yun"]]}
                if m != ch and (set(pss) & m_ps) and m not in same_bu:
                    same_bu.append(m)
        out["rhyme"] = {"char": ch, "pingshui": pss,
                        "cilin": sorted({b for p in pss for b in cilin_of(p)}),
                        "candidates": same_bu[:30],
                        "note": "候选=语料韵伴组∩平水同部（常用且归部可靠）；平水韵由广韵合并推导"}
    # 意象建议：按心境匹配档案，支持排除（如「不要月」）
    if mood:
        avoid = {t2s(x) for x in (avoid_imagery or [])}
        m = engine.match(mood, top_k=1)
        sugg = []
        for canon in m["query"]["imagery"] + [
                i for prof in engine.theme_profiles.values()
                if prof["theme"] in m["query"]["themes"]
                for x in prof.get("top_imagery", [])[:6] for i in [x["imagery"]]]:
            if canon not in avoid and canon not in sugg:
                prof = engine.imagery_profiles.get(canon)
                if prof:
                    top = prof["emotion_associations"][:1]
                    sugg.append(canon)
        out["imagery_suggestions"] = [
            {"imagery": c,
             "association": (engine.imagery_profiles[c]["emotion_associations"][0]["emotion"]
                             if engine.imagery_profiles.get(c, {}).get("emotion_associations") else ""),
             "example": (engine.imagery_profiles[c]["evidence_chain"][0]
                         if engine.imagery_profiles.get(c, {}).get("evidence_chain") else {})}
            for c in sugg[:8]]
        out["avoided"] = sorted(avoid)
    return out


def check_draft(lines: List[str], genre: str = "") -> Dict:
    """逐句检查草稿：平仄/律则/撞句（与语料逐字重合提醒）。"""
    from .engine import get_engine
    from ..extract.phonology import get_phonology
    engine = get_engine()
    ph = get_phonology()
    feet = [cjk_chars(ln)[-1] for ln in lines[1::2] if cjk_chars(ln)]
    tonal = ph.analyze_poem(lines, feet)
    collisions = []
    for ln in lines:
        folded = "".join(cjk_chars(t2s(ln)))
        if len(folded) >= 5:
            r = engine.intertext_query(text=folded)
            for p in (r.get("pairs") or [])[:1]:
                collisions.append({"line": ln, "overlaps": p["shared_span"],
                                   "with": [p["source_poem_id"], p["target_poem_id"]]})
    return {"declaration": "【创作声明】草稿为今人拟作；检查仅涉形式层。",
            "tonal": tonal, "collisions": collisions,
            "note": "撞句=与语料 5 字以上逐字重合（提醒非禁止；化用请自觉注明）"}
