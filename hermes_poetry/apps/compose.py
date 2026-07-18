"""创作实验室（第三阶段 MVP）：格律辅助，永远标注「今人拟作」。

能力：平仄模板（近体标准谱）、韵部候选字（平水韵/词林正韵，来源分层）、
意象建议（语料档案，可排除）、陈词提醒（语料高频五言句头）、逐句检查。
守卫：不代拟古人署名；输出显式创作声明。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..textutil import cjk_chars, t2s

# 近体标准谱四起式（王力《诗词格律》通行口径；○平 ●仄 ◎常规可宽）。
# ◎位并非无限自由：仍受孤平、三平尾与拗救约束（见 template_note）。
def _templates_for(genre: str) -> Dict[str, List[str]]:
    from ..extract.phonology import Phonology
    char_n = 7 if genre.startswith("七") else 5
    n_lines = 8 if genre.endswith("律") else 4
    out = {}
    for qishi in Phonology._QISHI:
        lines = Phonology._template_lines(qishi, char_n, n_lines)
        marked = []
        for ln in lines:
            chars = []
            for j, tone in enumerate(ln):
                lenient = j not in ([1, 3] + ([5] if char_n == 7 else []) + [char_n - 1])
                chars.append("◎" if lenient else ("○" if tone == "平" else "●"))
            marked.append("".join(chars))
        out[qishi] = marked
    return out


def compose_helper(genre: str = "七绝", rhyme_char: str = "", mood: str = "",
                   avoid_imagery: Optional[List[str]] = None,
                   imagery: Optional[List[str]] = None, engine=None) -> Dict:
    from .engine import get_engine
    from ..extract.phonology import get_phonology, pingshui_of, cilin_of
    engine = engine or get_engine()
    ph = get_phonology()
    genre = t2s(genre.strip()) or "七绝"
    if genre not in ("五绝", "七绝", "五律", "七律"):
        genre = "七绝"
    out: Dict = {
        "declaration": "【创作声明】本工具输出为今人拟作辅助，不得伪托古人作品；"
                       "引用的古典例句均逐字回源。",
        "genre": genre,
        "templates": _templates_for(genre),
        "template_note": "四起式标准谱（平起/仄起 × 首句入韵/不入韵，王力口径）；"
                         "○平 ●仄；◎常规可宽但非无限自由——仍受孤平、三平尾、"
                         "句末与拗救规则约束，草稿请用 check_draft 复核。",
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
    # 用户选定意象：逐一给出情感关联与例证（供立意布局参考）
    if imagery:
        from ..lexicon import IMAGERY_SURFACE
        s2c = {t2s(s): c for s, c in IMAGERY_SURFACE}
        chosen = []
        for x in imagery:
            canon = s2c.get(t2s(x.strip()), t2s(x.strip()))
            prof = engine.imagery_profiles.get(canon)
            if prof:
                chosen.append({
                    "imagery": canon,
                    "associations": [a["emotion"] for a in prof.get("emotion_associations", [])[:3]],
                    "co_imagery": [c["imagery"] for c in prof.get("co_imagery", [])[:5]],
                    "example": (prof.get("evidence_chain") or [{}])[0]})
            else:
                chosen.append({"imagery": canon, "note": "无该意象档案（词库外，自由使用）"})
        out["chosen_imagery"] = chosen
    return out


def compose_cipai(cipai: str, engine=None) -> Dict:
    """词创作辅助：龙榆生词谱权威层 + 语料例词 + 韵位说明。"""
    from .engine import get_engine
    engine = engine or get_engine()
    r = engine.cipai_query(cipai)
    if r.get("error"):
        return r
    out = {
        "declaration": "【创作声明】本工具输出为今人拟作辅助，不得伪托古人作品。",
        "query": r["query"], "resolved_via": r["resolved_via"],
        "cipu": r["cipu"], "cipai_profile": r["cipai_profile"],
        "example_poems": r["all_poems"][:12], "n_examples_total": len(r["all_poems"]),
        "note": r["note"],
    }
    return out


def compose_gufeng(theme: str = "", rhyme_char: str = "", n_lines: int = 16,
                   requirements: str = "", engine=None, client=None) -> Dict:
    """古体（歌行）创作智能体：检索规则组合成方案 → 真实大模型代拟 → 形式核验。

    确定性方案层（离线可用）：体式（七言歌行）、分段与换韵计划（语料韵组）、
    意象建议（题材档案）、语料范例（长恨歌等歌行原文节选，逐字回源）。
    生成层：接入真实大模型时按方案代拟并过撞句/换韵一致性核验；
    local 后端不代笔，如实返回方案与范例。
    """
    from .engine import get_engine
    from ..llm import get_client
    from ..extract.phonology import get_phonology, pingshui_of
    engine = engine or get_engine()
    client = client or get_client()
    ph = get_phonology()
    n_lines = max(8, min(int(n_lines or 16), 60))
    n_lines -= n_lines % 4
    n_seg = n_lines // 4

    # ── 换韵计划：韵脚字所在韵组起手，其余从大韵组轮换（歌行四句一转常式）──
    plan_groups: List[Dict] = []
    used = set()
    ch = t2s((rhyme_char or "").strip())[:1]
    if ch:
        for g in engine.rhyme_rules:
            if ch in g["members"]:
                plan_groups.append(g)
                used.add(g["label"])
                break
    for g in sorted(engine.rhyme_rules, key=lambda x: -len(x["members"])):
        if len(plan_groups) >= n_seg:
            break
        if g["label"] not in used and "异常" not in g["note"]:
            plan_groups.append(g)
            used.add(g["label"])
    rhyme_plan = [{"segment": i + 1, "lines": f"{i*4+1}–{i*4+4}",
                   "group": g["label"], "candidates": g["members"][:12]}
                  for i, g in enumerate(plan_groups[:n_seg])]

    # ── 意象建议（题材/心境档案）──
    imagery_sugg = []
    if theme:
        m = engine.match(theme, top_k=1)
        for canon in m["query"]["imagery"] + [
                x["imagery"] for prof in engine.theme_profiles.values()
                if prof["theme"] in m["query"]["themes"]
                for x in prof.get("top_imagery", [])[:5]]:
            if canon not in imagery_sugg:
                imagery_sugg.append(canon)
    imagery_sugg = imagery_sugg[:8]

    # ── 语料范例：七言歌行（长恨歌等）节选，逐字回源 ──
    gexing = sorted((p for p in engine.poems if p.genre == "七古" and len(p.lines) >= 24),
                    key=lambda p: -len(p.lines))
    refs = [{"poem_id": p.poem_id, "title": p.title, "author": p.author,
             "n_lines": len(p.lines), "excerpt": p.lines[:4]} for p in gexing[:3]]

    plan = {
        "genre": "七言歌行（古体，不拘平仄粘对，四句一解、可转韵）",
        "n_lines": n_lines, "segments": n_seg, "rhyme_plan": rhyme_plan,
        "imagery_suggestions": imagery_sugg, "references": refs,
        "conventions": [
            "歌行以四句（一解）为常见换韵单位，平仄韵可交替以变声情",
            "首解立题，中段铺叙转折，末解收束咏叹（参考范例结构）",
            "古体不拘近体粘对，但句内仍避生硬拗口；叙事宜时序清晰",
        ],
    }
    out: Dict = {
        "declaration": "【创作声明】本工具产出为今人拟作（AI 代拟），绝不伪托古人；"
                       "范例引文均逐字回源语料。",
        "theme": theme, "rhyme_char": ch, "requirements": requirements,
        "plan": plan, "backend": client.backend,
    }
    if not client.available:
        out["poem"] = None
        out["note"] = ("当前为离线确定性后端：不代笔生成，仅给出检索组合的创作方案与"
                       "语料范例；接入真实大模型（litellm/azure/poe/minimax）后自动代拟并核验。")
        return out

    # ── 真实大模型代拟 + 形式核验（换韵一致性/撞句），一次修复机会 ──
    seg_desc = "；".join(f"第{r['segment']}解（{r['lines']}句）押【{r['group']}】组，"
                         f"候选韵脚：{'、'.join(r['candidates'][:8])}" for r in rhyme_plan)
    prompt = (f"请以七言歌行体创作一首 {n_lines} 句的古风长诗。主题：{theme or '不限'}。"
              f"{('用户要求：' + requirements + '。') if requirements else ''}"
              f"换韵计划：{seg_desc}。四句一解，偶数句入韵，解内一韵到底。"
              f"建议意象：{'、'.join(imagery_sugg) or '不限'}。"
              "只输出诗行，每句一行，不加标题与解说。")
    issues: List[str] = []
    poem_lines: List[str] = []
    for attempt in range(2):
        res = client.chat([{"role": "user", "content": prompt if not issues else
                            prompt + "\n上稿问题：" + "；".join(issues) + "。请修正重写。"}],
                          task="compose_gufeng")
        poem_lines = [ln.strip() for ln in (res.content or "").splitlines()
                      if ln.strip() and len(cjk_chars(ln)) >= 5][:n_lines]
        issues = _verify_gufeng(poem_lines, rhyme_plan, engine, ph)
        if not issues:
            break
    out["poem"] = poem_lines
    out["verification"] = {"passed": not issues, "issues": issues,
                           "note": "核验项：句数/换韵计划一致性（平水韵近似）/与语料撞句；"
                                   "古体不判近体律则"}
    return out


def _verify_gufeng(lines: List[str], rhyme_plan: List[Dict], engine, ph) -> List[str]:
    from ..extract.phonology import pingshui_of
    issues: List[str] = []
    if not lines:
        return ["未产出诗行"]
    want = sum(1 for _ in rhyme_plan) * 4
    if len(lines) < want:
        issues.append(f"句数不足：{len(lines)}/{want}")
    def _bu(chars):
        return {pingshui_of(y) for m in chars
                for rd in ph.char_readings(m) for y in [rd["yun"]] if pingshui_of(y)}
    first_bu = _bu(rhyme_plan[0]["candidates"]) if rhyme_plan else set()
    for r in rhyme_plan:
        i0 = (r["segment"] - 1) * 4
        feet = [cjk_chars(t2s(ln))[-1] for ln in lines[i0 + 1:i0 + 4:2]
                if cjk_chars(ln)]
        member_bu = _bu(r["candidates"])
        for f in feet:
            f_bu = _bu([f])
            # 解内押计划组，或全篇沿用首解组（歌行一韵到底亦常见）均可
            if f_bu and member_bu and not (f_bu & member_bu) and not (f_bu & first_bu):
                issues.append(f"第{r['segment']}解韵脚「{f}」不在计划韵组【{r['group']}】"
                              "亦不在首解韵组近似韵部内")
    for ln in lines[:8]:
        folded = "".join(cjk_chars(t2s(ln)))
        if len(folded) >= 5:
            rr = engine.intertext_query(text=folded)
            if rr.get("pairs"):
                issues.append(f"「{ln}」与语料原句逐字重合（涉嫌抄袭而非化用）")
    return issues[:6]


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
