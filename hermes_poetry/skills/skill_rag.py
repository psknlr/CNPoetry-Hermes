"""SkillRAG：把编译出的 Skill 树变成问题路由器（自我消费的技能库）。

装载 data/skills/cnpoetry/ 下所有 SKILL.md（frontmatter name/description）与
examples.jsonl（query → route + args），路由分两级：
  1. 示例精确/子串命中（如「浣溪沙的格式」命中词牌技能示例）；
  2. BM25 兜底：对技能描述建索引，取 top-1。
返回 {skill, route, args, confidence}；无技能树时返回 None（优雅降级）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from .. import config
from ..rag.bm25 import BM25Index
from ..textutil import t2s

# route → 工具名（与 ToolRegistry 对齐）
ROUTE_TOOL = {
    "imagery": "poetry_imagery",
    "cipai": "poetry_cipai",
    "author": "poetry_author",
    "teach": "poetry_teach",
    "match": "poetry_match",
    "rhyme": "poetry_rhyme",
    "search": "poetry_search",
    "gloss": "poetry_gloss",
}


class SkillRAG:
    def __init__(self, skills_dir: Optional[Path] = None):
        self.root = skills_dir or config.SKILLS_DIR
        self.skills: List[Dict] = []
        self.examples: List[Dict] = []
        self.index = BM25Index()
        self._load()

    def _load(self) -> None:
        if not self.root.exists():
            return
        rx_front = re.compile(r"^---\n(.*?)\n---", re.S)
        for skill_md in sorted(self.root.rglob("SKILL.md")):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            m = rx_front.match(text)
            meta = {}
            if m:
                for line in m.group(1).splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
            name = meta.get("name", skill_md.parent.name)
            desc = meta.get("description", "")
            self.skills.append({"name": name, "description": desc, "dir": str(skill_md.parent)})
            self.index.add(name, t2s(f"{name} {desc}"))
            ex_path = skill_md.parent / "examples.jsonl"
            if ex_path.exists():
                for line in ex_path.read_text(encoding="utf-8").splitlines():
                    try:
                        ex = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ex.get("query") and ex.get("route"):
                        ex["skill"] = name
                        self.examples.append(ex)
        if self.skills:
            self.index.finalize()

    @property
    def ready(self) -> bool:
        return bool(self.skills)

    def route(self, question: str) -> Optional[Dict]:
        if not self.ready or not question:
            return None
        q = t2s(question.strip())
        # 一级：示例命中（示例 query 的核心词出现在问题里）
        best_ex, best_len = None, 0
        for ex in self.examples:
            key = t2s(ex["query"]).replace("的", "")
            core = key[:4]
            if (t2s(ex["query"]) in q) or (len(core) >= 2 and core in q):
                if len(core) > best_len:
                    best_ex, best_len = ex, len(core)
        if best_ex:
            return {"skill": best_ex["skill"], "route": best_ex["route"],
                    "tool": ROUTE_TOOL.get(best_ex["route"], "poetry_search"),
                    "args": best_ex.get("args", {}), "confidence": 0.85,
                    "via": "example_match"}
        # 二级：BM25 描述兜底
        hits = self.index.search(q, top_k=1)
        if hits:
            name = hits[0][0]
            route = "search"
            for key, r in (("imagery", "imagery"), ("cipai", "cipai"), ("author", "author"),
                           ("theme", "teach"), ("rhyme", "rhyme")):
                if f".{key}." in name or name.endswith(f".{key}"):
                    route = r
                    break
            args: Dict = {}
            tail = name.rsplit(".", 1)[-1]
            if route in ("imagery", "cipai", "author") and not tail.startswith("hermes"):
                args = {route if route != "imagery" else "imagery": tail}
            if route == "teach":
                args = {"topic": tail}
            return {"skill": name, "route": route,
                    "tool": ROUTE_TOOL.get(route, "poetry_search"),
                    "args": args, "confidence": 0.5, "via": "bm25_description"}
        return None


_skill_rag: Optional[SkillRAG] = None


def get_skill_rag() -> SkillRAG:
    global _skill_rag
    if _skill_rag is None:
        _skill_rag = SkillRAG()
    return _skill_rag
