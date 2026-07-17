"""文本工具：CJK 分词、相似度、简繁归一、逐字包含核验。

设计要点（承袭伤寒-赫尔墨斯）：
  * 检索分词 = 字 unigram + 相邻 bigram，无需分词器即可服务未分词的文言语料；
  * similarity = 字 bigram Dice 系数，用于引文模糊匹配与篇章对齐；
  * 简繁折叠使用 OpenCC TSCharacters 单字表构建 str.translate 映射——
    单字映射保持字符串长度不变，折叠后做匹配时所有偏移量仍然有效；
  * contains_verbatim 是全系统证据闸门的核心：两侧去空白/标点、繁→简
    折叠后做子串判定，逐字回源失败的规则一律拒绝。
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from typing import Dict, List, Tuple

from . import config

RE_CJK = re.compile(r"[㐀-鿿]")
RE_SENT_SPLIT = re.compile(r"[，。、；：？！,.;:?!\s「」『』〈〉《》（）()\[\]【】·]+")


def cjk_chars(text: str) -> List[str]:
    return RE_CJK.findall(text or "")


def tokenize(text: str) -> List[str]:
    """字 unigram + bigram（检索用）。"""
    chars = cjk_chars(text)
    tokens = list(chars)
    tokens.extend(a + b for a, b in zip(chars, chars[1:]))
    return tokens


def bigram_set(text: str):
    chars = cjk_chars(text)
    return {a + b for a, b in zip(chars, chars[1:])}


def similarity(a: str, b: str) -> float:
    """字 bigram Dice 系数。"""
    sa, sb = bigram_set(a), bigram_set(b)
    if not sa or not sb:
        return 0.0
    return 2.0 * len(sa & sb) / (len(sa) + len(sb))


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ── 简繁折叠（OpenCC TSCharacters 单字表）────────────────────────────


@lru_cache(maxsize=1)
def _t2s_table() -> Dict[int, str]:
    """从 OpenCC TSCharacters.txt 构建 繁→简 单字 translate 表。

    只取单字→单字映射（多字候选取第一个），保证长度不变以维持偏移量。
    文件缺失时退化为空表（系统仍可运行，只是繁体查询命中率下降）。
    """
    table: Dict[int, str] = {}
    path = config.CHARMAP_FILE
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            trad, simp_alts = parts[0], parts[1].split()
            if len(trad) == 1 and simp_alts and len(simp_alts[0]) == 1:
                if trad != simp_alts[0]:
                    table[ord(trad)] = simp_alts[0]
    except OSError:
        pass
    return table


# 常见异体字折叠（在 t2s 之后应用；单字映射保长度）。
# OpenCC 表已覆盖大多数繁简对，这里补诗词语料常见异体。
_VARIANT_MAP = str.maketrans({
    "廻": "回", "逥": "回", "峯": "峰", "邨": "村", "牀": "床",
    "畧": "略", "覩": "睹", "遶": "绕", "徧": "遍", "嵗": "岁",
    "蹔": "暂", "讌": "宴", "慿": "凭", "隄": "堤", "颿": "帆",
})


def t2s(text: str) -> str:
    """繁→简折叠（长度不变）。语料索引与查询归一的统一入口。"""
    return (text or "").translate(_t2s_table()).translate(_VARIANT_MAP)


@lru_cache(maxsize=1)
def _s2t_pairs() -> Dict[str, str]:
    """简→繁展示映射（由 t2s 表反转；一简对多繁时保留首见）。"""
    rev: Dict[str, str] = {}
    for k, v in _t2s_table().items():
        rev.setdefault(v, chr(k))
    return rev


def normalize_query(text: str) -> str:
    return t2s((text or "").strip())


def content_only(text: str) -> str:
    """仅保留 CJK 字符（去空白与标点），用于逐字包含核验。"""
    return "".join(cjk_chars(text))


def contains_verbatim(haystack: str, needle: str) -> bool:
    """证据闸门核心：needle 是否逐字存在于 haystack。

    两侧去空白/标点并做繁→简折叠后判定子串。空 needle 视为不通过。
    """
    n = content_only(t2s(needle))
    if not n:
        return False
    return n in content_only(t2s(haystack))


def split_lines(paragraphs: List[str]) -> List[str]:
    """把语料段落切分为句（诗行）。

    chinese-poetry 的一个 paragraph 常含两句（如「春眠不覺曉，處處聞啼鳥。」），
    句是格律计量与证据定位的原子单位。
    """
    lines: List[str] = []
    for para in paragraphs or []:
        for piece in RE_SENT_SPLIT.split(para or ""):
            piece = piece.strip()
            if piece:
                lines.append(piece)
    return lines


def strip_brackets(text: str) -> str:
    """去除小注（括注/尖注），如「（一作…）」「〔…〕」。"""
    return re.sub(r"[（(〔\[【][^）)〕\]】]*[）)〕\]】]", "", text or "")
