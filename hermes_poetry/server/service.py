"""ServiceContext：服务端共享上下文（懒加载引擎/智能体/合议）。"""
from __future__ import annotations

from typing import Dict, Optional

from .. import config
from .._version import __version__


class ServiceContext:
    def __init__(self):
        self._engine = None
        self._agent = None
        self._council = None
        self._registry = None

    def ready(self) -> bool:
        return (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists()

    @property
    def engine(self):
        if self._engine is None:
            from ..apps.engine import get_engine
            self._engine = get_engine()
        return self._engine

    @property
    def registry(self):
        if self._registry is None:
            from ..agent.tools import ToolRegistry
            self._registry = ToolRegistry(self.engine)
        return self._registry

    @property
    def agent(self):
        if self._agent is None:
            from ..agent.agent import PoetryAgent
            self._agent = PoetryAgent(registry=self.registry)
        return self._agent

    @property
    def council(self):
        if self._council is None:
            from ..agent.council import Council
            self._council = Council(registry=self.registry)
        return self._council

    def warm(self) -> None:
        _ = self.registry

    # ── API 方法 ────────────────────────────────────────────────
    def health(self) -> Dict:
        from ..llm import get_client
        return {"ok": True, "ready": self.ready(), "version": __version__,
                "backend": get_client().backend}

    def stats(self) -> Dict:
        return self.engine.stats()

    def search(self, body: Dict) -> Dict:
        return {"hits": self.engine.rag.search(
            body.get("query", ""), top_k=int(body.get("top_k", 8)),
            dynasty=body.get("dynasty", ""), author=body.get("author", ""),
            genre=body.get("genre", ""), cipai=body.get("cipai", ""),
            expand=bool(body.get("expand")))}

    def poem(self, body: Dict) -> Dict:
        return self.engine.explain_poem(body.get("ref", ""))

    def match(self, body: Dict) -> Dict:
        return self.engine.match(body.get("mood", ""), body.get("imagery"),
                                 body.get("themes"), int(body.get("top_k", 6)))

    def differential(self, body: Dict) -> Dict:
        return self.engine.differential(body.get("refs") or [])

    def teach(self, body: Dict) -> Dict:
        return self.engine.teach(body.get("topic", ""))

    def imagery(self, body: Dict) -> Dict:
        name = body.get("imagery", "")
        prof = self.engine.imagery_profiles.get(name)
        return {"imagery_profile": prof} if prof else \
            {"error": f"无意象档案「{name}」", "available": list(self.engine.imagery_profiles)}

    def cipai(self, body: Dict) -> Dict:
        from ..textutil import t2s
        prof = self.engine.cipai_profiles.get(t2s(body.get("cipai", "")))
        return {"cipai_profile": prof} if prof else {"error": "无该词牌档案"}

    def author(self, body: Dict) -> Dict:
        from ..textutil import t2s
        prof = self.engine.author_profiles.get(t2s(body.get("author", "")))
        return {"author_profile": prof} if prof else {"error": "无该诗人档案"}

    def rhyme(self, body: Dict) -> Dict:
        return self.engine.rhyme_query(body.get("char", ""), body.get("poem_ref", ""))

    def intertext(self, body: Dict) -> Dict:
        return self.engine.intertext_query(body.get("poem_ref", ""), body.get("text", ""))

    def scene(self, body: Dict) -> Dict:
        return self.engine.scene(body.get("ref", ""))

    def gloss(self, body: Dict) -> Dict:
        return self.engine.gloss_query(body.get("chars", ""), body.get("poem_ref", ""))

    def research(self, body: Dict) -> Dict:
        return self.engine.research(body.get("topic", ""))

    def ask(self, body: Dict) -> Dict:
        return self.agent.ask(body.get("question", ""), role=body.get("role", ""))

    def run_council(self, body: Dict) -> Dict:
        return self.council.deliberate(body.get("question", ""), role=body.get("role", ""))

    def compose(self, body: Dict) -> Dict:
        from ..apps.compose import compose_helper
        return compose_helper(genre=body.get("genre", "七绝"),
                              rhyme_char=body.get("rhyme_char", ""),
                              mood=body.get("mood", ""),
                              avoid_imagery=body.get("avoid_imagery"),
                              engine=self.engine)

    def check_draft(self, body: Dict) -> Dict:
        from ..apps.compose import check_draft
        lines = [ln.strip() for ln in (body.get("lines") or []) if ln and ln.strip()]
        if not lines:
            return {"error": {"code": "EMPTY_DRAFT", "message": "请提供草稿诗句（每行一句）",
                              "recoverable": True}}
        return check_draft(lines, genre=body.get("genre", ""))

    def tool(self, body: Dict) -> Dict:
        return self.registry.call(body.get("name", ""), body.get("arguments") or {})

    def tools(self) -> Dict:
        return {"tools": self.registry.specs()}

    def skills(self) -> Dict:
        import json as _json
        manifest = config.SKILLS_DIR / "skills_manifest.json"
        if manifest.exists():
            return _json.loads(manifest.read_text(encoding="utf-8"))
        return {"error": "skills_not_built"}
