"""对仗分析（B层启发式）：平仄相对 + 语义范畴对位。

诚实边界：无句法分析器，不判主谓宾结构与虚实词序列；本层检查
（1）平仄相对率（依《广韵》，两读不计）；（2）同位字语义范畴对应
（数字/颜色/方位/天文/地理/时令/动植物/人体/人事），范畴词表为
精选种子非全集。输出 工对倾向/宽对倾向/对仗弱 三级与逐位明细。
"""
from __future__ import annotations

from typing import Dict, List

from ..textutil import cjk_chars, strip_brackets

CATEGORIES: Dict[str, str] = {}
for _cat, _chars in {
    "数字": "一二三四五六七八九十百千万双孤独半几",
    "颜色": "红黄蓝绿紫白黑青碧朱丹素金银翠彩",
    "方位": "东西南北上下前后左右中边内外里",
    "天文": "天日月星风云雨雪霜露雷电虹霞烟雾",
    "地理": "山水江河湖海溪泉石田野岸洲峰谷路桥城郭村",
    "时令": "春夏秋冬晓暮朝夕昼夜岁年晨昏今古",
    "动物": "鸟雁燕莺鹤马牛羊犬鸡鱼龙虎猿蝉蛩鸥鹭鸿",
    "植物": "花草木柳松竹梅兰菊荷叶枝林苔萍桑麻禾",
    "人体": "头目眉眼耳口手足心身发鬓颜面泪",
    "人事": "君臣客主人翁友僧童妾郎将兵农渔樵",
}.items():
    for _c in _chars:
        CATEGORIES[_c] = _cat


def analyze_couplet(line_a: str, line_b: str) -> Dict:
    a = cjk_chars(strip_brackets(line_a))
    b = cjk_chars(strip_brackets(line_b))
    if len(a) != len(b) or not a:
        return {"parallel": False, "reason": "字数不等"}
    from .phonology import get_phonology
    ph = get_phonology()
    pos_detail: List[Dict] = []
    tone_pairs = tone_opposed = cat_pairs = cat_matched = 0
    for i, (ca, cb) in enumerate(zip(a, b)):
        pa, pb = ph.ping_ze(ca), ph.ping_ze(cb)
        if pa in ("平", "仄") and pb in ("平", "仄"):
            tone_pairs += 1
            if pa != pb:
                tone_opposed += 1
        cat_a, cat_b = CATEGORIES.get(ca, ""), CATEGORIES.get(cb, "")
        if cat_a and cat_b:
            cat_pairs += 1
            if cat_a == cat_b and ca != cb:
                cat_matched += 1
        pos_detail.append({"pos": i + 1, "chars": f"{ca}/{cb}", "tones": f"{pa}/{pb}",
                           "category": f"{cat_a or '—'}/{cat_b or '—'}"})
    tone_rate = round(tone_opposed / tone_pairs, 3) if tone_pairs else None
    cat_rate = round(cat_matched / cat_pairs, 3) if cat_pairs else None
    verdict = "对仗弱"
    if tone_rate is not None and tone_rate >= 0.7:
        verdict = "工对倾向" if (cat_rate or 0) >= 0.5 and cat_pairs >= 2 else "宽对倾向"
    return {"parallel": verdict != "对仗弱", "verdict": verdict,
            "tone_opposition_rate": tone_rate, "category_match_rate": cat_rate,
            "positions": pos_detail, "layer": "B",
            "note": "启发式对仗：平仄相对+范畴对位；不判句法结构/借对/流水对（诚实边界）。"}


def analyze_regulated(lines: List[str]) -> List[Dict]:
    """律诗中二联（颔联/颈联）对仗检查。"""
    out = []
    if len(lines) == 8:
        for name, i in (("颔联", 2), ("颈联", 4)):
            r = analyze_couplet(lines[i], lines[i + 1])
            r["couplet"] = name
            out.append(r)
    return out
