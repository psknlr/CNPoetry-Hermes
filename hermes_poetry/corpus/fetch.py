"""语料扩充：从公开数据源按需下载更多原始文件。

种子语料随仓库提交；本模块用于扩充（如全唐诗 58 个分片、全宋词 22 个
分片）。下载后重跑 pipeline 即可纳入。仅用标准库 urllib。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import List

from .. import config

GH = "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master"

EXPANSIONS = [
    {"name": "quantangshi_full", "desc": "全唐诗全量（58 个分片，约 5.7 万首，~50MB）",
     "paths": [f"全唐诗/poet.tang.{i}.json" for i in range(0, 58000, 1000)],
     "dest": "quantangshi"},
    {"name": "songci_full", "desc": "全宋词全量（22 个分片，约 2.1 万首）",
     "paths": [f"宋词/ci.song.{i}.json" for i in range(0, 22000, 1000)],
     "dest": "songci"},
    {"name": "quansongshi_sample", "desc": "全宋诗更多抽样（前 20 个分片）",
     "paths": [f"全唐诗/poet.song.{i}.json" for i in range(0, 20000, 1000)],
     "dest": "quansongshi"},
]

EXTERNAL_DATASETS = [
    {"name": "PoetryMTEB/ChineseClassicalPoetryDatabase",
     "url": "https://huggingface.co/datasets/PoetryMTEB/ChineseClassicalPoetryDatabase",
     "note": "96.5 万首＋LLM 分析层（parquet）；种子样本已内置 data/raw/hf_poetrymteb/"},
    {"name": "gujilab/chinese-classical-corpus",
     "url": "https://huggingface.co/datasets/gujilab/chinese-classical-corpus",
     "note": "十三经+二十四史+197 万条古译今指令对（CC0）；其说文解字 9829 条与"
             "尔雅 19 篇已抽取入 data/raw/gujilab/ 作 C 层训诂（poetry_gloss 工具）"},
]


def fetch_main(list_only: bool = False) -> int:
    if list_only:
        print("可扩充来源（`fetch` 不带 --list 时逐项询问下载）：")
        for e in EXPANSIONS:
            print(f"  [{e['name']}] {e['desc']}")
        print("\n外部数据集（手动扩展参考）：")
        for d in EXTERNAL_DATASETS:
            print(f"  {d['name']} — {d['note']}\n    {d['url']}")
        return 0
    for e in EXPANSIONS:
        ans = input(f"下载 {e['desc']}? [y/N] ").strip().lower()
        if ans != "y":
            continue
        dest_dir = config.CHINESE_POETRY_RAW / e["dest"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        ok = fail = skip = 0
        for path in e["paths"]:
            fname = path.split("/")[-1]
            out = dest_dir / fname
            if out.exists():
                skip += 1
                continue
            url = f"{GH}/{urllib.parse.quote(path)}"
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    data = resp.read()
                json.loads(data)  # 验证 JSON
                out.write_bytes(data)
                ok += 1
            except Exception as exc:
                fail += 1
                print(f"  失败 {fname}: {type(exc).__name__}")
        print(f"  完成：新增 {ok}，跳过 {skip}，失败 {fail}")
    print("下载完成后请重跑 `python3 -m hermes_poetry pipeline` 纳入新语料。")
    return 0
