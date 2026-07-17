"""LLMClient：后端选择、磁盘缓存、用量统计、优雅回退。

后端解析：HERMES_LLM_BACKEND ∈ {auto,litellm,local,scripted}；auto 仅在
litellm 可导入且存在任一供应商 API key 时选 litellm，否则 local。
真实模型构造失败或调用失败 → 回退 local 并在文末标注，绝不抛出。
缓存仅对 litellm、temperature=0、无工具调用的响应生效（可复现性）。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .. import config
from .providers import ChatResult, LiteLLMProvider, LocalProvider, ScriptedProvider

_PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_API_KEY",
                  "POE_API_KEY", "MINIMAX_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY")


@dataclass
class LLMSettings:
    backend: str = ""
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 2048
    cache: bool = True
    fallback: str = "local"

    @classmethod
    def from_env(cls) -> "LLMSettings":
        return cls(
            backend=os.environ.get("HERMES_LLM_BACKEND", "auto"),
            model=os.environ.get("HERMES_LLM_MODEL", "claude-sonnet-5"),
            temperature=float(os.environ.get("HERMES_LLM_TEMPERATURE", "0")),
            max_tokens=int(os.environ.get("HERMES_LLM_MAX_TOKENS", "2048")),
            cache=os.environ.get("HERMES_LLM_CACHE", "1") != "0",
        )

    def resolve_backend(self) -> str:
        b = (self.backend or "auto").lower()
        if b in ("litellm", "local", "scripted"):
            return b
        try:
            import litellm  # noqa: F401
        except Exception:
            return "local"
        return "litellm" if any(os.environ.get(k) for k in _PROVIDER_KEYS) else "local"


def _cache_key(model, messages, tools, temperature, task, json_mode) -> str:
    blob = json.dumps({"m": model, "msgs": messages, "tools": tools, "t": temperature,
                       "task": task, "j": json_mode}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class LLMClient:
    def __init__(self, settings: Optional[LLMSettings] = None, provider=None):
        self.settings = settings or LLMSettings.from_env()
        self._backend = self.settings.resolve_backend()
        self.usage: Dict[str, int] = {"calls": 0, "errors": 0, "cache_hits": 0,
                                      "prompt_tokens": 0, "completion_tokens": 0}
        self._provider = provider or self._build_provider(self._backend)

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def available(self) -> bool:
        """是否接入真实大模型（local 为确定性后端，不算）。"""
        return self._backend == "litellm"

    def _build_provider(self, backend: str):
        if backend == "litellm":
            try:
                return LiteLLMProvider(self.settings)
            except Exception:
                self._backend = "local"
                return LocalProvider(self.settings)
        if backend == "scripted":
            return ScriptedProvider()
        return LocalProvider(self.settings)

    def chat(self, messages: List[Dict], tools=None, temperature: Optional[float] = None,
             json_mode: bool = False, task: Optional[str] = None,
             context: Optional[Dict] = None, use_cache: bool = True) -> ChatResult:
        temp = self.settings.temperature if temperature is None else temperature
        cacheable = (use_cache and self.settings.cache and self._backend == "litellm"
                     and temp == 0.0 and not tools)
        key = None
        if cacheable:
            key = _cache_key(self.settings.model, messages, tools, temp, task, json_mode)
            hit = self._cache_load(key)
            if hit is not None:
                self.usage["cache_hits"] += 1
                return ChatResult(content=hit.get("content", ""), usage=hit.get("usage", {}),
                                  backend=self._backend)
        try:
            res = self._provider.chat(messages, tools=tools, temperature=temp,
                                      json_mode=json_mode, task=task, context=context)
        except Exception as exc:
            self.usage["errors"] += 1
            if self.settings.fallback == "local" and self._backend == "litellm":
                res = LocalProvider(self.settings).chat(messages, tools=tools, temperature=temp,
                                                        json_mode=json_mode, task=task, context=context)
                if res.content:
                    res.content += f"\n\n（注：大模型调用失败已回退 local：{type(exc).__name__}）"
            else:
                raise
        self.usage["calls"] += 1
        for k in ("prompt_tokens", "completion_tokens"):
            self.usage[k] += int(res.usage.get(k, 0))
        if cacheable and key and not res.tool_calls:
            self._cache_store(key, {"content": res.content, "usage": res.usage})
        return res

    # ── 磁盘缓存 ────────────────────────────────────────────────
    def _cache_path(self, key: str):
        return config.LLM_CACHE_DIR / f"{key}.json"

    def _cache_load(self, key: str) -> Optional[Dict[str, Any]]:
        p = self._cache_path(key)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        return None

    def _cache_store(self, key: str, payload: Dict[str, Any]) -> None:
        try:
            config.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._cache_path(key).write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ── 任务助手 ────────────────────────────────────────────────
    def synthesize(self, question: str, evidence: List[Dict], role: str = "reader") -> str:
        from .prompts import synth_system, synth_user
        res = self.chat(
            [{"role": "system", "content": synth_system(role)},
             {"role": "user", "content": synth_user(question, evidence)}],
            task="synthesize",
            context={"question": question, "evidence": evidence, "role": role},
        )
        return res.content


_client: Optional[LLMClient] = None


def get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def set_client(client: Optional[LLMClient]) -> None:
    global _client
    _client = client
