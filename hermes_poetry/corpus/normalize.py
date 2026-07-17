"""语料归一化：原始集子 → poems.jsonl + corpus_manifest.json。

要点：
  * poem_id 稳定编号：CNP_{SOURCE}_{n:05d}，按登记顺序与文件顺序确定；
  * 跨集去重（重出互见）：以「简体作者 + 正文前12个 CJK 字」为键；
    后见记录并入首见记录（合并 tags/notes/appreciation/also_in），
    精选集在前登记故成为保留方；
  * manifest 记录每个来源的文件 sha256 —— 语料版本指纹；
  * 归一化只整理不改写：原文 text/lines 保持原样（含繁简差异）。
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Dict, List, Tuple

from .. import config
from ..schemas import Poem, write_jsonl
from ..textutil import content_only, split_lines, t2s
from . import sources as src


def _dedup_key(author: str, paragraphs: List[str]) -> str:
    body = content_only(t2s("".join(paragraphs)))[:12]
    return f"{content_only(t2s(author))}|{body}"


def build_poems(verbose: bool = True) -> Tuple[List[Poem], Dict]:
    poems: List[Poem] = []
    seen: Dict[str, Poem] = OrderedDict()
    per_source: Dict[str, Dict[str, int]] = {}
    merged_dups = 0

    for spec in src.SOURCES:
        key = spec["key"]
        counter = 0
        raw_count = 0
        for rec in src.iter_source(spec):
            raw_count += 1
            dk = _dedup_key(rec["author"], rec["paragraphs"])
            if dk in seen and len(dk) > 8:  # 键太短（极短诗）不参与去重
                keep = seen[dk]
                if rec["book"] not in keep.also_in and rec["book"] != keep.book:
                    keep.also_in.append(rec["book"])
                keep.tags.extend(t for t in rec["tags"] if t not in keep.tags)
                keep.notes.extend(n for n in rec["notes"] if n not in keep.notes)
                if rec["appreciation"] and not keep.appreciation:
                    keep.appreciation = rec["appreciation"]
                if rec.get("genre_tag") and "genre_tag" not in keep.tags:
                    keep.tags.append(rec["genre_tag"])
                merged_dups += 1
                continue
            counter += 1
            text = "\n".join(rec["paragraphs"])
            poem = Poem(
                poem_id=f"{config.POEM_ID_PREFIX}_{key}_{counter:05d}",
                source=key,
                book=rec["book"],
                dynasty=rec["dynasty"] or "未知",
                author=rec["author"] or "佚名",
                title=rec["title"] or (rec["cipai"] or "无题"),
                cipai=rec["cipai"],
                section=rec["section"],
                genre=rec.get("genre_tag", ""),
                genre_source="tag" if rec.get("genre_tag") else "",
                lines=split_lines(rec["paragraphs"]),
                text=text,
                tags=rec["tags"],
                notes=rec["notes"],
                appreciation=rec["appreciation"],
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
            seen[dk] = poem
            poems.append(poem)
        per_source[key] = {"raw": raw_count, "kept": counter}
        if verbose:
            print(f"  [{key}] {spec['book']}: 原始 {raw_count} 首，保留 {counter} 首")

    manifest = {
        "system": "Hermes-CNPoetry",
        "poem_count": len(poems),
        "merged_duplicates": merged_dups,
        "per_source": per_source,
        "layer_legend": config.LAYER_LABEL,
        "sources": _source_fingerprints(),
    }
    return poems, manifest


def _source_fingerprints() -> List[Dict]:
    out = []
    root = config.CHINESE_POETRY_RAW
    for spec in src.SOURCES:
        files = sorted(root.glob(spec["glob"]))
        out.append({
            "key": spec["key"],
            "book": spec["book"],
            "files": [f.name for f in files],
            "file_sha256": {
                f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files
            },
        })
    return out


def persist(poems: List[Poem], manifest: Dict) -> None:
    write_jsonl(config.POEM_DIR / "poems.jsonl", poems)
    config.MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.MANIFEST_DIR / "corpus_manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(config.MANIFEST_DIR / "corpus_manifest.json")


def load_poems() -> List[Poem]:
    from ..schemas import read_jsonl
    return [Poem.from_dict(d) for d in read_jsonl(config.POEM_DIR / "poems.jsonl")]
