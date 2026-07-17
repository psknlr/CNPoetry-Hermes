"""LLM 后端：LiteLLM（可选，100+ 供应商）与确定性本地后端。

本地后端（LocalProvider）是全系统可离线、可测试、可复现的支柱：
它实现与真实模型完全相同的接口与输出模式——工具循环两步走
（先路由到一个工具，再从工具结果组稿），组稿永远引用工具结果中的
poem_id，使引用核验在离线时同样有意义。真实模型调用失败时优雅
回退到本地后端，绝不让智能体崩溃。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    backend: str = ""
    raw: Any = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LiteLLMProvider:
    def __init__(self, settings):
        import litellm  # noqa: F401 延迟导入；缺依赖时在构造期失败并回退
        self._litellm = litellm
        litellm.drop_params = True
        self.settings = settings

    def chat(self, messages, tools=None, temperature=0.0, json_mode=False,
             task=None, context=None) -> ChatResult:
        kwargs: Dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.settings.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._litellm.completion(**kwargs)
        msg = resp.choices[0].message
        calls = []
        for tc in getattr(msg, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id or f"call_{len(calls)}", name=tc.function.name, arguments=args))
        usage = {}
        if getattr(resp, "usage", None):
            usage = {"prompt_tokens": resp.usage.prompt_tokens or 0,
                     "completion_tokens": resp.usage.completion_tokens or 0}
        return ChatResult(content=msg.content or "", tool_calls=calls, usage=usage,
                          backend="litellm", raw=resp)


class ScriptedProvider:
    """测试用：按队列弹出预置回复。"""

    def __init__(self, queue: Optional[List] = None):
        self.queue = list(queue or [])

    def chat(self, messages, tools=None, temperature=0.0, json_mode=False,
             task=None, context=None) -> ChatResult:
        if not self.queue:
            return ChatResult(content="", backend="scripted")
        item = self.queue.pop(0)
        if isinstance(item, ChatResult):
            return item
        if isinstance(item, dict):
            return ChatResult(**item)
        return ChatResult(content=str(item), backend="scripted")


# ── 确定性本地后端 ───────────────────────────────────────────────────

_RE_CIPAI_Q = re.compile(r"(?:词牌|定格|格式)")
_RE_METRIC_Q = re.compile(r"(?:格律|平仄|押韵|韵脚|体裁|几言|绝句|律诗)")
_RE_IMAGERY_Q = re.compile(r"(?:意象|象征|代表什么|含义)")
_RE_DIFF_Q = re.compile(r"(?:对比|比较|异同|区别|鉴别)")
_RE_AUTHOR_Q = re.compile(r"(?:诗风|生平|小传|哪些诗|档案|风格)")
_RE_INTERTEXT_Q = re.compile(r"(?:化用|袭用|互文|相似|出处相近|重出)")
_RE_MATCH_Q = re.compile(r"(?:推荐|荐诗|想家|思乡|心情|适合|表达.{0,4}的诗)")
_RE_TEACH_Q = re.compile(r"(?:学习|入门|教学|讲讲|介绍一下)")


class LocalProvider:
    def __init__(self, settings=None):
        self.settings = settings

    def chat(self, messages, tools=None, temperature=0.0, json_mode=False,
             task=None, context=None) -> ChatResult:
        context = context or {}
        if task == "synthesize":
            return ChatResult(content=self._synthesize(context, messages), backend="local")
        if task == "plan":
            return ChatResult(content=json.dumps(self._plan(context), ensure_ascii=False), backend="local")
        if task == "critic":
            return ChatResult(content=json.dumps({"result": "pass", "flags": []}, ensure_ascii=False), backend="local")
        if tools:
            if not any(m.get("role") == "tool" for m in messages):
                return self._route_tool(messages, tools)
            return ChatResult(content=self._synthesize_from_tools(messages), backend="local")
        return ChatResult(content=self._synthesize(context, messages), backend="local")

    # ── 工具路由（第一步）────────────────────────────────────────
    def _route_tool(self, messages, tools) -> ChatResult:
        q = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                q = m.get("content") or ""
                break
        names = {t["function"]["name"] for t in tools}

        def call(name: str, args: Dict) -> ChatResult:
            if name not in names:
                name = "poetry_search" if "poetry_search" in names else next(iter(names))
                args = {"query": q}
            return ChatResult(tool_calls=[ToolCall(id="local_1", name=name, arguments=args)],
                              backend="local")

        title = re.search(r"[《〈]([^》〉]{1,20})[》〉]", q)
        if title and _RE_METRIC_Q.search(q):
            return call("poetry_metrics", {"poem_ref": f"《{title.group(1)}》"})
        if title and _RE_INTERTEXT_Q.search(q):
            return call("poetry_intertext", {"poem_ref": f"《{title.group(1)}》"})
        if title:
            return call("poetry_poem", {"poem_ref": f"《{title.group(1)}》"})
        if _RE_CIPAI_Q.search(q):
            cp = re.sub(r"的?(?:词牌|定格|格式).*$", "", q).strip()
            return call("poetry_cipai", {"cipai": cp[-6:] if cp else q})
        if _RE_DIFF_Q.search(q):
            return call("poetry_differential", {"query": q})
        if _RE_IMAGERY_Q.search(q):
            from ..lexicon import IMAGERY_SURFACE
            from ..textutil import t2s
            folded = t2s(q)
            for surface, canon in IMAGERY_SURFACE:
                if surface in folded:
                    return call("poetry_imagery", {"imagery": canon})
        if _RE_AUTHOR_Q.search(q):
            return call("poetry_author", {"author": re.sub(r"的.*$", "", q).strip()[:6]})
        if _RE_MATCH_Q.search(q):
            return call("poetry_match", {"mood": q})
        if _RE_TEACH_Q.search(q):
            return call("poetry_teach", {"topic": q})
        return call("poetry_search", {"query": q})

    # ── 组稿（第二步：只引用工具证据）────────────────────────────
    def _synthesize_from_tools(self, messages) -> str:
        payloads = []
        for m in messages:
            if m.get("role") == "tool":
                try:
                    payloads.append(json.loads(m.get("content") or "{}"))
                except json.JSONDecodeError:
                    continue
        parts = []
        for p in payloads:
            parts.append(self._compose_answer(p))
        text = "\n\n".join(x for x in parts if x)
        return text or "未在语料中找到可回源的证据，无法作答。"

    def _compose_answer(self, payload: Dict) -> str:
        if not isinstance(payload, dict):
            return ""
        if payload.get("error"):
            return f"（工具错误：{payload['error']}）"
        # 检索/荐诗类
        hits = payload.get("hits") or payload.get("recommendations")
        if hits:
            lines = []
            for h in hits[:5]:
                quote = h.get("quote") or ""
                lines.append(f"- 《{h.get('title','')}》（{h.get('author','佚名')}，{h.get('dynasty','')}）"
                             f"「{quote}」［{h.get('poem_id','')}］")
            return "依据语料检索（A层原文）：\n" + "\n".join(lines)
        # 作品全息
        if payload.get("poem"):
            p = payload["poem"]
            body = "／".join(p.get("lines", [])[:8])
            return (f"《{p.get('title','')}》（{p.get('author','')}，{p.get('dynasty','')}）"
                    f"［{p.get('poem_id','')}］：{body}")
        # 意象档案
        if payload.get("imagery_profile"):
            r = payload["imagery_profile"]
            assoc = "；".join(f"{a['emotion']}（{a['support']}例）" for a in r.get("emotion_associations", [])[:4])
            ex = (r.get("emotion_associations") or [{}])[0].get("example", {})
            return (f"意象「{r.get('imagery')}」在 {r.get('n_poems')} 首语料中的情感关联：{assoc}。"
                    f"例：「{ex.get('quote','')}」［{ex.get('poem_id','')}］（语料归纳，非权威定论）")
        # 格律
        if payload.get("metrics"):
            m = payload["metrics"]
            return (f"《{m.get('title')}》格律计量（B层）：体裁 {m.get('genre')}（{m.get('genre_source')}），"
                    f"{m.get('line_count')} 句，句式 {m.get('char_pattern')}，"
                    f"韵脚位置字 {'、'.join(m.get('rhyme_feet', []))}。［{m.get('poem_id','')}］")
        # 词牌
        if payload.get("cipai_profile"):
            r = payload["cipai_profile"]
            ex = (r.get("example_poems") or [{}])[0]
            ex_str = (f"例词：《{ex.get('title','')}》（{ex.get('author','')}）"
                      f"［{ex.get('poem_id','')}］。" if ex.get("poem_id") else "")
            return (f"词牌「{r.get('cipai')}」定格（语料归纳，{r.get('n_poems')} 首）："
                    f"众数句式 {r.get('char_pattern')}，一致率 {round(100*r.get('pattern_consistency',0))}%。"
                    f"{ex_str}{r.get('note','')}")
        # 诗人
        if payload.get("author_profile"):
            r = payload["author_profile"]
            img = "、".join(x["imagery"] for x in r.get("top_imagery", [])[:5])
            return (f"诗人档案：{r.get('author')}（{r.get('dynasty')}），语料 {r.get('n_poems')} 首，"
                    f"高频意象：{img}。" + (f"小传（C层）：{r.get('bio','')[:120]}…" if r.get("bio") else ""))
        # 对比
        if payload.get("contrast"):
            rows = payload["contrast"]
            return "对比（逐轴，证据见各诗）：\n" + "\n".join(
                f"- {row.get('axis')}：{row.get('detail')}" for row in rows[:8])
        # 教学
        if payload.get("lesson"):
            les = payload["lesson"]
            reps = "\n".join(f"- 《{x.get('title')}》（{x.get('author','')}）「{x.get('quote','')}」［{x.get('poem_id')}］"
                             for x in les.get("representative", [])[:5])
            return f"{les.get('outline','')}\n代表作：\n{reps}"
        if payload.get("groups"):
            gs = payload["groups"]
            return "韵伴（语料归纳，非平水韵）：" + "；".join(
                f"【{g.get('label')}】{''.join(g.get('members', [])[:12])}" for g in gs[:3])
        if payload.get("pairs"):
            ps = payload["pairs"]
            return "互文检测：\n" + "\n".join(
                f"- {x.get('mode')}「{x.get('shared_span')}」：{x.get('source_poem_id')} ↔ {x.get('target_poem_id')}"
                for x in ps[:5])
        if payload.get("stats"):
            return "语料统计：" + json.dumps(payload["stats"], ensure_ascii=False)
        if payload.get("analysis"):
            a = payload["analysis"]
            return (f"外部分析（D层，{a.get('dataset','')}，LLM 生成非本系统结论）："
                    f"题材 {a.get('subject','')}；主题 {a.get('theme','')}；情感 {a.get('emotion','')}")
        return ""

    def _synthesize(self, context: Dict, messages) -> str:
        ev = context.get("evidence") or []
        if ev:
            lines = [f"- 《{e.get('title','')}》「{e.get('quote','')}」［{e.get('poem_id','')}］" for e in ev[:6]]
            return "基于已核验证据：\n" + "\n".join(lines)
        return "未取得可回源证据，无法作答。"

    def _plan(self, context: Dict) -> Dict:
        return {"goal": context.get("question", ""), "specialists": context.get("specialists", [])}
