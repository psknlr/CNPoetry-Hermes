"""ToolRegistry：只读能力代理（capability broker）。

调用管线：未知工具默认拒绝 → 参数矫治（"6"→6、"月"→["月"]）→ JSON-Schema
子集校验 → 执行 → 输出形状与大小护栏 → 证据层标注 → 环形审计日志。
ScopedRegistry 是最小权限包装：角色只见白名单工具，越权调用直接拒绝。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from ..apps.engine import Engine
from ..health import assert_ready

MAX_RESULT_BYTES = 400_000


class Tool:
    def __init__(self, name: str, description: str, parameters: Dict, func: Callable[..., Dict]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def spec(self) -> Dict:
        return {"type": "function",
                "function": {"name": self.name, "description": self.description,
                             "parameters": self.parameters}}


MAX_STRING_ARG = 500


def _coerce(value, typ):
    if typ == "integer" and isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    if typ == "boolean" and isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "是")
    if typ == "array" and isinstance(value, str):
        return [x.strip() for x in value.replace("，", ",").split(",") if x.strip()]
    if typ == "array" and isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return value


class ToolRegistry:
    def __init__(self, engine: Optional[Engine] = None):
        assert_ready("ToolRegistry")
        from ..apps.engine import get_engine
        self.engine = engine or get_engine()
        self._tools: Dict[str, Tool] = {}
        self.audit: List[Dict] = []
        self._register_all()

    # ── 注册 ─────────────────────────────────────────────────────
    def _register_all(self) -> None:
        e = self.engine

        def add(name, desc, props, func, required=None):
            self._tools[name] = Tool(name, desc, {
                "type": "object", "properties": props, "required": required or []}, func)

        add("poetry_search", "检索诗词原文（BM25+结构化过滤+意象扩展）。返回带 poem_id 与引句的命中列表。",
            {"query": {"type": "string"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
             "dynasty": {"type": "string"}, "author": {"type": "string"},
             "genre": {"type": "string"}, "cipai": {"type": "string"},
             "expand": {"type": "boolean"}},
            lambda query="", top_k=8, dynasty="", author="", genre="", cipai="", expand=False:
                {"hits": e.rag.search(query, top_k=top_k, dynasty=dynasty, author=author,
                                      genre=genre, cipai=cipai, expand=bool(expand))},
            required=["query"])
        add("poetry_poem", "按 poem_id 或《题名》取作品全息（原文A/计量B/旁证C/外部分析D/互文）。",
            {"poem_ref": {"type": "string"}},
            lambda poem_ref="": e.explain_poem(poem_ref), required=["poem_ref"])
        add("poetry_match", "情境荐诗：按心境/场景/意象推荐作品，逐条带证据引句。",
            {"mood": {"type": "string"}, "imagery": {"type": "array"},
             "themes": {"type": "array"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 20}},
            lambda mood="", imagery=None, themes=None, top_k=6:
                e.match(mood, imagery, themes, top_k))
        add("poetry_differential", "多首作品对比鉴赏（体裁/意象/题材/情感/互文逐轴对比）。",
            {"poem_refs": {"type": "array"}, "query": {"type": "string"}},
            self._differential)
        add("poetry_imagery", "意象档案：跨诗归纳的情感关联、共现意象与证据链。",
            {"imagery": {"type": "string"}},
            lambda imagery="": ({"imagery_profile": e.imagery_profiles[imagery]}
                                if imagery in e.imagery_profiles
                                else {"error": f"无意象档案「{imagery}」",
                                      "available": list(e.imagery_profiles)[:30]}),
            required=["imagery"])
        add("poetry_metrics", "格律计量（B层）：体裁判定、句式、韵脚位置字。",
            {"poem_ref": {"type": "string"}}, self._metrics, required=["poem_ref"])
        add("poetry_cipai", "词牌定格（语料归纳）：众数句式与一致率。",
            {"cipai": {"type": "string"}}, self._cipai, required=["cipai"])
        add("poetry_author", "诗人档案：语料内作品数、高频意象、题材与小传（C层）。",
            {"author": {"type": "string"}}, self._author, required=["author"])
        add("poetry_theme", "题材档案：定义、标记词、朝代分布与例证。",
            {"theme": {"type": "string"}},
            lambda theme="": ({"theme_profile": e.theme_profiles[theme]}
                              if theme in e.theme_profiles
                              else {"error": f"无题材档案「{theme}」", "available": list(e.theme_profiles)}),
            required=["theme"])
        add("poetry_rhyme", "韵伴查询（语料归纳，非平水韵）：按字或按作品查韵组。",
            {"char": {"type": "string"}, "poem_ref": {"type": "string"}},
            lambda char="", poem_ref="": e.rhyme_query(char, poem_ref))
        add("poetry_intertext", "互文检测：作品或诗句的逐字复用（重出互见/袭用/化用）。",
            {"poem_ref": {"type": "string"}, "text": {"type": "string"}},
            lambda poem_ref="", text="": e.intertext_query(poem_ref, text))
        add("poetry_teach", "教学：题材/体裁/意象/诗人四类主题的结构化课程。",
            {"topic": {"type": "string"}}, lambda topic="": e.teach(topic), required=["topic"])
        add("poetry_external_analysis", "外部LLM分析（D层）：PoetryMTEB 数据集对该诗的意图/题材/情感分析。",
            {"poem_ref": {"type": "string"}}, self._external, required=["poem_ref"])
        add("poetry_gloss", "字义训诂（C层）：说文解字本义（部首/反切/释文）与尔雅训释组。",
            {"chars": {"type": "string"}, "poem_ref": {"type": "string"}},
            lambda chars="", poem_ref="": e.gloss_query(chars, poem_ref))
        add("poetry_research", "研究端：意象共现网络、朝代分布、情感×意象矩阵。",
            {"topic": {"type": "string"}}, lambda topic="": e.research(topic))
        add("poetry_stats", "语料与规则库统计。", {}, lambda: {"stats": e.stats()})

    # ── 复合处理器 ───────────────────────────────────────────────
    def _differential(self, poem_refs=None, query="") -> Dict:
        refs = list(poem_refs or [])
        if not refs and query:
            import re as _re
            refs = [f"《{t}》" for t in _re.findall(r"[《〈]([^》〉]{1,20})[》〉]", query)]
        if len(refs) < 2 and query:
            # 已解析的题名保留，检索命中只补足缺口（不整组替换）
            have = {self.engine.resolve_poem(r).poem_id
                    for r in refs if self.engine.resolve_poem(r)}
            for h in self.engine.rag.search(query, top_k=4):
                if h["poem_id"] not in have:
                    refs.append(h["poem_id"])
                    have.add(h["poem_id"])
                if len(refs) >= 2:
                    break
        return self.engine.differential(refs)

    def _metrics(self, poem_ref="") -> Dict:
        p = self.engine.resolve_poem(poem_ref)
        if p is None:
            return {"error": f"无法解析作品「{poem_ref}」。"}
        from ..extract.metrics import describe
        return {"metrics": describe(p)}

    def _cipai(self, cipai="") -> Dict:
        from ..textutil import t2s
        prof = self.engine.cipai_profiles.get(t2s(cipai.strip()))
        if prof:
            return {"cipai_profile": prof}
        cands = [c["cipai"] for c in self.engine.cipai_profiles.values()][:20]
        return {"error": f"无词牌档案「{cipai}」", "available": cands}

    def _author(self, author="") -> Dict:
        from ..textutil import t2s
        prof = self.engine.author_profiles.get(t2s(author.strip()))
        if prof:
            return {"author_profile": prof}
        return {"error": f"无诗人档案「{author}」（语料内作品≥5首才建档）。"}

    def _external(self, poem_ref="") -> Dict:
        p = self.engine.resolve_poem(poem_ref)
        if p is None:
            return {"error": f"无法解析作品「{poem_ref}」。"}
        ext = self.engine._ext_by_poem.get(p.poem_id)
        if not ext:
            return {"poem_id": p.poem_id, "analysis": None,
                    "note": "该诗无外部分析绑定（样本层仅覆盖部分作品）。"}
        return {"poem_id": p.poem_id, "analysis": {
            "dataset": "PoetryMTEB/ChineseClassicalPoetryDatabase (DeepSeek-V3.1)",
            "subject": ext.get("subject"), "theme": ext.get("theme"),
            "intent": ext.get("intent"), "emotion": ext.get("emotion"), "layer": "D"}}

    # ── 调用管线 ─────────────────────────────────────────────────
    def names(self) -> List[str]:
        return sorted(self._tools)

    def specs(self) -> List[Dict]:
        return [t.spec() for _, t in sorted(self._tools.items())]

    def call(self, name: str, arguments: Optional[Dict] = None) -> Dict:
        if name not in self._tools:
            return {"error": f"unknown_tool:{name}", "available": self.names()}
        tool = self._tools[name]
        args = dict(arguments or {})
        props = tool.parameters.get("properties", {})
        # 参数矫治 + 校验
        clean: Dict[str, Any] = {}
        for k, v in args.items():
            if k not in props:
                continue
            v = _coerce(v, props[k].get("type"))
            typ = props[k].get("type")
            if typ == "integer":
                if not isinstance(v, int):
                    return {"error": f"bad_arg_type:{k}"}
                lo, hi = props[k].get("minimum"), props[k].get("maximum")
                if lo is not None:
                    v = max(lo, v)
                if hi is not None:
                    v = min(hi, v)
            if typ == "string":
                v = str(v)[:MAX_STRING_ARG]
            if typ == "array":
                if not isinstance(v, list):
                    return {"error": f"bad_arg_type:{k}"}
                v = [str(x)[:MAX_STRING_ARG] for x in v[:20]]
            if typ == "boolean" and not isinstance(v, bool):
                return {"error": f"bad_arg_type:{k}"}
            clean[k] = v
        for req in tool.parameters.get("required", []):
            if not clean.get(req):
                return {"error": f"missing_required_arg:{req}"}
        try:
            result = tool.func(**clean)
        except Exception as exc:  # 工具内部错误不外泄细节
            result = {"error": f"tool_failed:{type(exc).__name__}"}
        if not isinstance(result, dict):
            result = {"error": "tool_returned_non_dict"}
        blob = json.dumps(result, ensure_ascii=False)
        if len(blob.encode("utf-8")) > MAX_RESULT_BYTES:
            result = {"error": "result_too_large"}
        self.audit.append({"tool": name,
                           "args": {k: (v[:80] if isinstance(v, str) else v)
                                    for k, v in clean.items()},
                           "ok": "error" not in result})
        if len(self.audit) > 512:
            del self.audit[:256]
        return result

    def for_role(self, role: str) -> "ScopedRegistry":
        from ..safety import role_tool_scope
        return ScopedRegistry(self, role_tool_scope(role, self.names()))


class ScopedRegistry:
    """最小权限包装：只暴露白名单工具。"""

    def __init__(self, base: ToolRegistry, allowed: List[str]):
        self.base = base
        self.allowed = set(allowed)
        self.engine = base.engine

    def names(self) -> List[str]:
        return sorted(self.allowed & set(self.base.names()))

    def specs(self) -> List[Dict]:
        return [s for s in self.base.specs() if s["function"]["name"] in self.allowed]

    def call(self, name: str, arguments: Optional[Dict] = None) -> Dict:
        if name not in self.allowed:
            return {"error": f"tool_out_of_scope:{name}", "available": self.names()}
        return self.base.call(name, arguments)

    def for_role(self, role: str) -> "ScopedRegistry":
        return self.base.for_role(role)
