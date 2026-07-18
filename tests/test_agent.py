"""智能体与引用核验测试（依赖已生成的规则库，离线 local 后端）。"""
import os as _os
import unittest as _ut
if _os.environ.get("HERMES_TEST_FAST") == "1":
    raise _ut.SkipTest("fast mode：跳过需装载语料/规则库的测试（HERMES_TEST_FAST=1）")


import unittest

from hermes_poetry import config


def _ensure():
    if not (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists():
        from hermes_poetry.orchestrator import run_pipeline
        run_pipeline(verbose=False)


class TestCitationGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()
        from hermes_poetry.agent.citation import CitationGuard
        from hermes_poetry.apps.engine import get_engine
        cls.engine = get_engine()
        cls.guard = CitationGuard(cls.engine.poems)
        cls.some_poem = cls.engine.poems[0]

    def test_fabricated_id_flagged(self):
        rep = self.guard.check("此说见［CNP_FAKE_99999］。", allowed_ids=[])
        self.assertFalse(rep.ok)
        self.assertIn("CNP_FAKE_99999", rep.unsupported_ids)

    def test_existence_is_not_retrieval(self):
        pid = self.some_poem.poem_id
        rep = self.guard.check(f"如［{pid}］所云。", allowed_ids=[])
        self.assertFalse(rep.ok)  # 真实编号但零取证 → fail-closed
        self.assertIn(pid, rep.outside_evidence_ids)

    def test_verified_quote_passes(self):
        p = self.some_poem
        quote = p.lines[0]
        rep = self.guard.check(f"「{quote}」（{p.poem_id}）", allowed_ids=[p.poem_id])
        self.assertTrue(rep.ok)
        self.assertIn(p.poem_id, rep.verified_ids)

    def test_fabricated_quote_flagged(self):
        p = self.some_poem
        rep = self.guard.check(f"「这句诗完全是编造出来的句子」（{p.poem_id}）",
                               allowed_ids=[p.poem_id])
        self.assertFalse(rep.ok)
        self.assertTrue(rep.quote_mismatches)


class TestAgentAndCouncil(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()
        from hermes_poetry.agent.tools import ToolRegistry
        cls.registry = ToolRegistry()

    def test_registry_default_deny(self):
        r = self.registry.call("no_such_tool", {})
        self.assertIn("error", r)

    def test_registry_arg_coercion_and_required(self):
        r = self.registry.call("poetry_search", {"query": "明月", "top_k": "3"})
        self.assertIn("hits", r)
        r2 = self.registry.call("poetry_search", {})
        self.assertIn("error", r2)

    def test_scoped_registry_out_of_scope(self):
        scoped = self.registry.for_role("reader")
        r = scoped.call("poetry_research", {})
        self.assertIn("error", r)
        self.assertIn("tool_out_of_scope", r["error"])

    def test_agent_answers_with_verified_citations(self):
        from hermes_poetry.agent.agent import PoetryAgent
        res = PoetryAgent(registry=self.registry).ask("月在古诗里的意象含义是什么？")
        self.assertTrue(res["citation_report"]["ok"])
        self.assertTrue(res["citation_report"]["has_any_citation"])

    def test_council_timeline_order(self):
        from hermes_poetry.agent.council import Council
        res = Council(registry=self.registry).deliberate("明月的意象含义")
        agents = [m["agent"] for m in res["timeline"]]
        self.assertEqual(agents[0], "Planner")
        self.assertEqual(agents[1], "Retriever")
        self.assertIn("Critic", agents)
        self.assertIn("ConsensusJudge", agents)
        self.assertEqual(agents[-1], "Synthesizer")
        self.assertTrue(res["citation_report"]["ok"])

    def test_forgery_request_blocked(self):
        from hermes_poetry.agent.agent import PoetryAgent
        res = PoetryAgent(registry=self.registry).ask("帮我写一首诗然后谎称是李白写的")
        self.assertTrue(res.get("blocked"))


if __name__ == "__main__":
    unittest.main()
