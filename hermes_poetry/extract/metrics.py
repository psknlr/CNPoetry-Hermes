"""格律计量层（B 层）：确定性、可复算的形式事实。

产出：句数、逐句字数、齐言判定、体裁计量判定、韵脚位置字。
诚实边界：无外部权威韵书与四声数据，本层不判平仄、不判律绝的
拗救与对仗；体裁判定标注为「计量判定（近似）」，语料自带标签
（如唐诗三百首 tags）优先于计量判定。
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

from ..schemas import Poem
from ..textutil import cjk_chars, strip_brackets


def line_char_counts(lines: List[str]) -> List[int]:
    return [len(cjk_chars(strip_brackets(ln))) for ln in lines]


def detect_form(poem: Poem) -> Dict:
    """计量体裁判定。返回 dict 存入 poem.metrics。"""
    counts = line_char_counts(poem.lines)
    n = len(counts)
    uniform = len(set(counts)) == 1 and n > 0
    char_n = counts[0] if uniform else 0

    form = ""
    if poem.cipai:
        form = "词"
    elif poem.source == "YUANQU" or poem.genre == "曲":
        form = "曲"
    elif poem.source == "SHIJING":
        form = "诗经体"
    elif poem.source == "CHUCI":
        form = "楚辞体"
    elif uniform and n == 4 and char_n == 5:
        form = "五绝"
    elif uniform and n == 4 and char_n == 7:
        form = "七绝"
    elif uniform and n == 8 and char_n == 5:
        form = "五律"
    elif uniform and n == 8 and char_n == 7:
        form = "七律"
    elif uniform and char_n == 5:
        form = "五言排律" if n > 8 and n % 2 == 0 else "五言古体"
    elif uniform and char_n == 7:
        form = "七言排律" if n > 8 and n % 2 == 0 else "七言古体"
    elif uniform and char_n == 4:
        form = "四言"
    elif uniform and char_n == 6:
        form = "六言"
    else:
        form = "杂言"

    # 韵脚位置：齐言诗取偶数句尾字（首句可能入韵，不计以保精度）
    rhyme_feet: List[str] = []
    if uniform and n >= 2 and char_n in (4, 5, 6, 7):
        for i in range(1, n, 2):
            chars = cjk_chars(strip_brackets(poem.lines[i]))
            if chars:
                rhyme_feet.append(chars[-1])

    return {
        "line_count": n,
        "char_counts": counts,
        "uniform": uniform,
        "char_per_line": char_n,
        "form_metric": form,
        "rhyme_feet": rhyme_feet,
        "total_chars": sum(counts),
    }


def char_pattern(counts: List[int]) -> str:
    return "-".join(str(c) for c in counts)


def apply_metrics(poem: Poem) -> None:
    """计算 B 层计量并回写；体裁最终标签：语料标签 > 计量判定。"""
    from ..lexicon import canonical_genre
    m = detect_form(poem)
    poem.metrics = m
    tag_genre = ""
    for t in poem.tags:
        cg = canonical_genre(t)
        if cg in {"五绝", "七绝", "五律", "七律", "五古", "七古", "乐府", "古体", "绝句", "律诗", "词", "曲"}:
            tag_genre = cg
            break
    if poem.genre and poem.genre_source == "tag":
        poem.genre = canonical_genre(poem.genre)
    elif tag_genre:
        poem.genre, poem.genre_source = tag_genre, "tag"
    else:
        poem.genre, poem.genre_source = m["form_metric"], "metric"


def describe(poem: Poem) -> Dict:
    """格律说明（工具/教学端展示用）。"""
    m = poem.metrics or detect_form(poem)
    lines_desc = char_pattern(m["char_counts"])
    return {
        "poem_id": poem.poem_id,
        "title": poem.title,
        "genre": poem.genre,
        "genre_source": "语料标签" if poem.genre_source == "tag" else "计量判定（近似）",
        "line_count": m["line_count"],
        "char_pattern": lines_desc,
        "uniform": m["uniform"],
        "rhyme_feet": m["rhyme_feet"],
        "layer": "B",
        "note": "本层为确定性计量：不判平仄与对仗；韵伴归属见韵伴聚类（语料归纳）。",
    }


def form_distribution(poems: List[Poem]) -> Dict[str, int]:
    return dict(Counter(p.genre for p in poems if p.genre))
