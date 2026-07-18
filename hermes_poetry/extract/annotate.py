"""意象/情感/题材标注器。

承袭伤寒-赫尔墨斯实体抽取的两条铁律：
  1. 先做保长度归一（t2s 折叠），使匹配偏移在原文上依然有效；
  2. 最长优先 + 共享占位掩码，杜绝「明月」再被「月」重复计数；
     情感标记若被否定前缀（不/无/未/莫/非/休/勿）修饰，一律不作正向证据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..lexicon import EMOTION_SURFACE, IMAGERY_SURFACE, NEGATION_PREFIX, THEME_SURFACE
from ..schemas import Poem
from ..textutil import t2s

# 否定词与标记之间可被跨越的中性字（「不是愁」「不见愁」「未必愁」）
_NEG_BRIDGE = set("是见得必成为曾复即在有")


def negation_scope(folded: str, idx: int, window: int = 3) -> bool:
    """标记位 idx 之前 window 字内是否存在管辖它的否定词。

    仅跨越中性桥接字；遇实义字即停（「离愁」的「离」不是桥，
    不会让更前面的否定词越界管辖）。
    """
    steps = 0
    j = idx - 1
    while j >= 0 and steps < window:
        ch = folded[j]
        if ch in NEGATION_PREFIX:
            return True
        if ch not in _NEG_BRIDGE:
            return False
        j -= 1
        steps += 1
    return False


@dataclass
class LineHits:
    line_idx: int = 0
    line: str = ""                      # 原文句
    imagery: List[Tuple[str, str]] = field(default_factory=list)   # (规范名, 表面形式)
    emotions: List[Tuple[str, str]] = field(default_factory=list)  # (类别, 标记词)
    negated_emotions: List[Tuple[str, str]] = field(default_factory=list)
    themes: List[Tuple[str, str]] = field(default_factory=list)    # (题材, 标记词)


def _match_terms(folded: str, surface_table, taken: List[bool]):
    """最长优先非重叠匹配；surface_table 已按表面形式长度降序。"""
    hits = []
    for surface, canon in surface_table:
        start = 0
        while True:
            idx = folded.find(surface, start)
            if idx < 0:
                break
            end = idx + len(surface)
            if not any(taken[idx:end]):
                for i in range(idx, end):
                    taken[i] = True
                hits.append((canon, surface, idx))
            start = idx + 1
    hits.sort(key=lambda h: h[2])
    return hits


# 词义消歧（首批：「月」）：单字「月」前接数字/历法/时段词时为月份义，
# 不作月亮意象（实测语料月份误标约 11.6%，复审 P0 项）。
# 「日月」保留为天体并举意象；机制可按意象扩展（柳=地名、山=山东等）。
_MONTH_PRE = set("一二两三四五六七八九十正腊闰几数岁年经累")


def _is_month_sense(folded: str, idx: int, surface: str) -> bool:
    return surface == "月" and idx > 0 and folded[idx - 1] in _MONTH_PRE


def annotate_line(line: str, line_idx: int) -> LineHits:
    folded = t2s(line)
    out = LineHits(line_idx=line_idx, line=line)
    taken = [False] * len(folded)
    # 意象先占位（多为名词性，优先级高）；词义排除语境不计
    for canon, surface, idx in _match_terms(folded, IMAGERY_SURFACE, taken):
        if canon == "月" and _is_month_sense(folded, idx, surface):
            continue
        out.imagery.append((canon, surface))
    # 情感标记：独立掩码——意象与情感是两个正交维度，共享掩码会让
    # 单字意象「云」吃掉更长的情感标记「凌云」（违背最长优先）
    taken_e = [False] * len(folded)
    for cat, marker, idx in _match_terms(folded, EMOTION_SURFACE, taken_e):
        if negation_scope(folded, idx):
            out.negated_emotions.append((cat, marker))
        else:
            out.emotions.append((cat, marker))
    taken_t = [False] * len(folded)
    for theme, marker, idx in _match_terms(folded, THEME_SURFACE, taken_t):
        out.themes.append((theme, marker))
    return out


def annotate_poem(poem: Poem) -> List[LineHits]:
    """逐句标注并把汇总写回 poem.imagery/emotions/themes。"""
    hits = [annotate_line(ln, i) for i, ln in enumerate(poem.lines)]
    imagery, emotions, theme_score = [], [], {}
    for h in hits:
        for canon, _ in h.imagery:
            if canon not in imagery:
                imagery.append(canon)
        for cat, _ in h.emotions:
            if cat not in emotions:
                emotions.append(cat)
        for theme, marker in h.themes:
            theme_score.setdefault(theme, set()).add(marker)
    poem.imagery = imagery
    poem.emotions = emotions
    # 题材判定（保精度）：≥2 个不同标记词；或单一标记词（长度≥2）在全篇
    # 出现≥2 次。单次弱命中不定题材，留给检索层做软信号。
    folded_text = t2s(poem.text)
    themes = []
    for theme, markers in theme_score.items():
        if len(markers) >= 2:
            themes.append(theme)
        else:
            m = next(iter(markers))
            if len(m) >= 2 and folded_text.count(m) >= 2:
                themes.append(theme)
    poem.themes = themes
    return hits
