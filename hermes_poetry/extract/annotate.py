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


def annotate_line(line: str, line_idx: int) -> LineHits:
    folded = t2s(line)
    out = LineHits(line_idx=line_idx, line=line)
    taken = [False] * len(folded)
    # 意象先占位（多为名词性，优先级高）
    for canon, surface, idx in _match_terms(folded, IMAGERY_SURFACE, taken):
        out.imagery.append((canon, surface))
    # 情感标记：单独掩码（同一字可同时是意象与情感语境的一部分时，意象优先）
    taken_e = list(taken)
    for cat, marker, idx in _match_terms(folded, EMOTION_SURFACE, taken_e):
        if idx > 0 and folded[idx - 1] in NEGATION_PREFIX:
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
