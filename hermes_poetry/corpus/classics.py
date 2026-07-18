"""全古文平台接口预留（第四阶段）：ClassicalWork 统一抽象。

诗词不外溢：古文（句读/虚词/论证结构/篇章层级）需要独立数据类与
流水线，不塞进 Poem。本模块仅定义接口与装载协议；gujilab 语料
（十三经/史记/资治通鉴，CC0）经 `fetch` 下载后可按此接口渐进接入。
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ClassicalWork:
    work_id: str = ""
    source: str = ""          # 书名（史记/论语…）
    category: str = ""        # 经/史/子/集
    author: str = ""
    era: str = ""
    chapter: str = ""
    content: str = ""
    # 古文专属层（后续流水线填充）：句读/虚词/活用/论证结构
    annotations: Dict = field(default_factory=dict)
    layer: str = "A"


def load_classics(path=None) -> List[ClassicalWork]:
    """装载 gujilab corpus.jsonl（若已 fetch）；缺失时返回空并不报错。"""
    import json
    from .. import config
    p = path or (config.RAW_DIR / "gujilab" / "corpus.jsonl")
    out: List[ClassicalWork] = []
    if not p.exists():
        return out
    with p.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.append(ClassicalWork(
                work_id=f"CW_{i:05d}", source=r.get("source", ""),
                category=r.get("category", ""), author=r.get("author", ""),
                era=r.get("era", ""), chapter=r.get("chapter", "") or "",
                content=r.get("content", "")))
    return out
