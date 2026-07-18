"""领域引擎与检索测试（依赖已生成的规则库）。"""
import os as _os
import unittest as _ut
if _os.environ.get("HERMES_TEST_FAST") == "1":
    raise _ut.SkipTest("fast mode：跳过需装载语料/规则库的测试（HERMES_TEST_FAST=1）")


import unittest

from hermes_poetry import config


def _ensure():
    from tests._common import require_assets
    require_assets()


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()
        from hermes_poetry.apps.engine import get_engine
        cls.engine = get_engine()

    def test_stats(self):
        s = self.engine.stats()
        self.assertGreater(s["poems"], 20000)
        self.assertGreater(s["imagery_profiles"], 30)

    def test_search_simplified_query_hits_traditional_poem(self):
        hits = self.engine.rag.search("大漠孤烟直", top_k=3)
        self.assertTrue(hits)
        self.assertIn("使至塞上", hits[0]["title"])

    def test_search_direct_title(self):
        hits = self.engine.rag.search("《静夜思》")
        self.assertEqual(hits[0]["match_source"], "direct_title")

    def test_search_filters(self):
        hits = self.engine.rag.search("明月", top_k=5, dynasty="宋")
        for h in hits:
            self.assertEqual(h["dynasty"], "宋")

    def test_match_mood(self):
        r = self.engine.match("想家")
        self.assertIn("思乡羁旅", r["query"]["themes"])
        self.assertTrue(r["recommendations"])
        # 每条推荐都有可回源证据
        for rec in r["recommendations"]:
            self.assertTrue(rec["poem_id"].startswith("CNP_"))
            self.assertTrue(rec["quote"])

    def test_differential(self):
        r = self.engine.differential(["《静夜思》", "《春晓》"])
        self.assertIn("contrast", r)
        axes = [row["axis"] for row in r["contrast"]]
        self.assertIn("共有意象", axes)

    def test_teach_theme_and_genre(self):
        r = self.engine.teach("送别怀人")
        self.assertEqual(r["lesson"]["type"], "theme")
        r2 = self.engine.teach("七绝")
        self.assertEqual(r2["lesson"]["type"], "genre")

    def test_explain_poem_layers(self):
        r = self.engine.explain_poem("《静夜思》")
        self.assertEqual(r["poem"]["layer"], "A")
        self.assertEqual(r["metrics"]["layer"], "B")

    def test_rhyme_query(self):
        r = self.engine.rhyme_query(char="天")
        self.assertIn("非平水韵", r["note"])

    def test_cipai_profile_quality(self):
        prof = self.engine.cipai_profiles.get("浣溪沙")
        self.assertIsNotNone(prof)
        self.assertEqual(prof["char_pattern"], "7-7-7-7-7-7")


class TestEvalSuites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()

    def test_metrics_eval_high_agreement(self):
        from hermes_poetry.eval.suites import eval_metrics
        r = eval_metrics()
        self.assertGreater(r["n"], 100)
        self.assertGreater(r["agreement"], 0.8)

    def test_retrieval_eval(self):
        from hermes_poetry.eval.suites import eval_retrieval
        r = eval_retrieval(limit=40)
        self.assertGreater(r["top5"], 0.8)


if __name__ == "__main__":
    unittest.main()
