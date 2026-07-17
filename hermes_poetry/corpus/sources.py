"""语料来源注册表与逐集解析器。

chinese-poetry 各集子字段各异（paragraphs/para/content、词牌 rhythmic、
注释 notes、白话导读 prologue、嵌套千家诗），此处统一解析为原始作品字典：
  {book, dynasty, author, title, cipai, section, paragraphs, tags, notes,
   appreciation, genre_tag}

登记为显式白名单：未登记文件不进入语料（fail-closed，与伤寒-赫尔墨斯的
worktype 分层同理）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

from .. import config


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _std(item: Dict[str, Any], book: str, dynasty: str, **over) -> Dict[str, Any]:
    paragraphs = item.get("paragraphs") or item.get("para") or item.get("content") or []
    rec = {
        "book": book,
        "dynasty": dynasty,
        "author": (item.get("author") or "").strip(),
        "title": (item.get("title") or item.get("chapter") or "").strip(),
        "cipai": (item.get("rhythmic") or "").strip(),
        "section": (item.get("section") or item.get("chapter") or "").strip(),
        "paragraphs": [p for p in paragraphs if isinstance(p, str) and p.strip()],
        "tags": [t for t in (item.get("tags") or []) if isinstance(t, str)],
        "notes": [n for n in (item.get("notes") or []) if isinstance(n, str)],
        "appreciation": (item.get("prologue") or "").strip(),
        "genre_tag": "",
    }
    rec.update(over)
    return rec


def _iter_standard(files: List[Path], book: str, dynasty: str, **over) -> Iterator[Dict[str, Any]]:
    for fp in files:
        for item in _load(fp):
            rec = _std(item, book, dynasty, **over)
            if rec["paragraphs"]:
                yield rec


def _iter_shijing(files, book, dynasty):
    for fp in files:
        for item in _load(fp):
            rec = _std(item, book, dynasty)
            rec["section"] = "·".join(x for x in [item.get("chapter"), item.get("section")] if x)
            rec["author"] = "佚名"
            rec["genre_tag"] = "诗经体"
            if rec["paragraphs"]:
                yield rec


def _iter_chuci(files, book, dynasty):
    for fp in files:
        for item in _load(fp):
            rec = _std(item, book, dynasty)
            rec["genre_tag"] = "楚辞体"
            if rec["paragraphs"]:
                yield rec


def _iter_qianjiashi(files, book, dynasty):
    for fp in files:
        data = _load(fp)
        for section in data.get("content", []):
            genre = (section.get("type") or "").strip()
            for item in section.get("content", []):
                rec = _std(item, book, dynasty)
                rec["title"] = (item.get("chapter") or "").strip()
                # 千家诗作者形如「（唐）孟浩然」，拆出朝代与姓名
                raw_author = (item.get("author") or "").strip()
                if raw_author.startswith("（") and "）" in raw_author:
                    dyn, name = raw_author[1:].split("）", 1)
                    rec["dynasty"], rec["author"] = dyn.strip(), name.strip()
                else:
                    rec["author"] = raw_author
                rec["genre_tag"] = genre
                if rec["paragraphs"]:
                    yield rec


_PARSERS = {
    "standard": _iter_standard,
    "shijing": _iter_shijing,
    "chuci": _iter_chuci,
    "qianjiashi": _iter_qianjiashi,
}

# ── 来源登记（显式白名单；key 进入 poem_id）──────────────────────────
SOURCES: List[Dict[str, Any]] = [
    {"key": "SHIJING", "glob": "shijing/shijing.json", "book": "诗经", "dynasty": "先秦", "parser": "shijing"},
    {"key": "CHUCI", "glob": "chuci/chuci.json", "book": "楚辞", "dynasty": "先秦", "parser": "chuci"},
    {"key": "CAOCAO", "glob": "caocao/caocao.json", "book": "曹操诗集", "dynasty": "汉魏", "parser": "standard", "over": {"author": "曹操", "genre_tag": "乐府"}},
    {"key": "TANG300", "glob": "tang300/tang300.json", "book": "唐诗三百首", "dynasty": "唐", "parser": "standard"},
    {"key": "QIANJIA", "glob": "qianjiashi/qianjiashi.json", "book": "千家诗", "dynasty": "", "parser": "qianjiashi"},
    {"key": "SHUIMO", "glob": "shuimo/shuimotangshi.json", "book": "水墨唐诗", "dynasty": "唐", "parser": "standard"},
    {"key": "QTS", "glob": "quantangshi/poet.tang.*.json", "book": "全唐诗（抽样）", "dynasty": "唐", "parser": "standard"},
    {"key": "HUAJIAN", "glob": "wudai/huajianji-*.json", "book": "花间集", "dynasty": "五代", "parser": "standard"},
    {"key": "NANTANG", "glob": "wudai/nantang.json", "book": "南唐二主词", "dynasty": "五代", "parser": "standard"},
    {"key": "QSS", "glob": "quansongshi/poet.song.*.json", "book": "全宋诗（抽样）", "dynasty": "宋", "parser": "standard"},
    {"key": "SONGCI300", "glob": "songci300/songci300.json", "book": "宋词三百首", "dynasty": "宋", "parser": "standard"},
    {"key": "SONGCI", "glob": "songci/ci.song.*.json", "book": "全宋词（抽样）", "dynasty": "宋", "parser": "standard"},
    {"key": "YUANQU", "glob": "yuanqu/yuanqu.json", "book": "元曲", "dynasty": "元", "parser": "standard", "over": {"genre_tag": "曲"}},
    {"key": "NALAN", "glob": "nalan/nalan.json", "book": "纳兰词", "dynasty": "清", "parser": "standard", "over": {"genre_tag": "词"}},
]

AUTHOR_BIO_FILES = {
    "唐": "authors/authors.tang.json",   # {name, desc, id}
    "宋": "authors/author.song.json",
}


def iter_source(spec: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    root = config.CHINESE_POETRY_RAW
    files = sorted(root.glob(spec["glob"]))
    parser = _PARSERS[spec["parser"]]
    over = spec.get("over", {})
    if spec["parser"] == "standard":
        yield from parser(files, spec["book"], spec["dynasty"], **over)
    else:
        yield from parser(files, spec["book"], spec["dynasty"])


def load_author_bios() -> Dict[str, Dict[str, str]]:
    """作者小传（C层）：简体折叠名 → {name, desc, dynasty}。"""
    from ..textutil import t2s
    bios: Dict[str, Dict[str, str]] = {}
    for dynasty, rel in AUTHOR_BIO_FILES.items():
        fp = config.CHINESE_POETRY_RAW / rel
        if not fp.exists():
            continue
        for item in _load(fp):
            name = (item.get("name") or "").strip()
            desc = (item.get("desc") or item.get("description") or "").strip()
            if name and desc:
                bios.setdefault(t2s(name), {"name": name, "desc": desc, "dynasty": dynasty})
    return bios


def load_external_analysis() -> List[Dict[str, Any]]:
    """外部 LLM 分析样本（D层，PoetryMTEB/DeepSeek-V3.1 生成）。"""
    fp = config.HF_ANALYSIS_FILE
    if not fp.exists():
        return []
    out = []
    with fp.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out
