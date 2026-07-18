"""第二轮整合测试：训诂层（gujilab）、SkillRAG、BM25 磁盘缓存、D层绑定。"""
import os as _os
import unittest as _ut
if _os.environ.get("HERMES_TEST_FAST") == "1":
    raise _ut.SkipTest("fast mode：跳过需装载语料/规则库的测试（HERMES_TEST_FAST=1）")


import unittest

from hermes_poetry import config


def _ensure():
    from tests._common import require_assets
    require_assets()


class TestGloss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()
        from hermes_poetry.apps.engine import get_engine
        cls.engine = get_engine()

    def test_shuowen_loaded(self):
        self.assertGreater(len(self.engine.shuowen), 9000)

    def test_gloss_query_char(self):
        r = self.engine.gloss_query("天")
        self.assertEqual(r["layer"], "C")
        g = r["glosses"][0]
        self.assertIsNotNone(g["shuowen"])
        self.assertIn("顚", g["shuowen"]["gloss"])  # 天：顚也

    def test_gloss_traditional_and_simplified(self):
        # 简体查询命中繁体字头
        r = self.engine.gloss_query("鸟")
        sw = r["glosses"][0]["shuowen"]
        self.assertIsNotNone(sw)

    def test_gloss_by_poem_ambiguous_card(self):
        # 《静夜思》语料中有两个异文版本（牀前看月光/牀前明月光）→ 严格歧义卡
        r = self.engine.gloss_query(poem_ref="《静夜思》")
        self.assertEqual(r["error"]["code"], "POEM_AMBIGUOUS")
        refs = [c["ref"] for c in r["error"]["candidates"]]
        self.assertTrue(all("#" in ref for ref in refs))  # 候选卡给出可直接复制的定解语法

    def test_gloss_by_poem_hinted(self):
        # #首句 提示定解（简体输入折叠命中繁体首句）
        r = self.engine.gloss_query(poem_ref="《静夜思》#床前明月光")
        self.assertTrue(r["glosses"])
        self.assertEqual(r["poem_id"], "CNP_QIANJIA_00023")

    def test_erya_groups(self):
        self.assertGreater(len(self.engine.erya), 250)
        r = self.engine.gloss_query("元")
        self.assertTrue(any(g["erya"] for g in r["glosses"]))


class TestSkillRAG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()
        from hermes_poetry.skills.skill_rag import SkillRAG
        cls.sr = SkillRAG()

    def test_loaded(self):
        self.assertGreater(len(self.sr.skills), 500)
        self.assertGreater(len(self.sr.examples), 500)

    def test_example_routing(self):
        r = self.sr.route("浣溪沙的格式是什么")
        self.assertEqual(r["tool"], "poetry_cipai")
        self.assertEqual(r["args"].get("cipai"), "浣溪沙")

    def test_mood_routing(self):
        r = self.sr.route("推荐表达思乡的诗")
        self.assertEqual(r["tool"], "poetry_match")

    def test_graceful_when_missing(self):
        from hermes_poetry.skills.skill_rag import SkillRAG
        from pathlib import Path
        empty = SkillRAG(skills_dir=Path("/nonexistent"))
        self.assertFalse(empty.ready)
        self.assertIsNone(empty.route("任意问题"))


class TestBM25Cache(unittest.TestCase):
    def test_dump_load_roundtrip(self):
        import tempfile
        from pathlib import Path
        from hermes_poetry.rag.bm25 import BM25Index
        idx = BM25Index()
        idx.add("a", "床前明月光")
        idx.add("b", "大漠孤煙直")
        idx.finalize()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.pkl"
            idx.dump(p, fingerprint="fp1")
            loaded = BM25Index.load(p, fingerprint="fp1")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.search("明月")[0][0], idx.search("明月")[0][0])
            # 指纹不符 → 缓存失效
            self.assertIsNone(BM25Index.load(p, fingerprint="fp2"))


class TestExternalBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()

    def test_dlayer_bindings_expanded(self):
        import json
        rules = [json.loads(l) for l in
                 (config.RULES_INITIAL_DIR / "initial_rules.jsonl").read_text(encoding="utf-8").splitlines()]
        ext = [r for r in rules if r["rule_type"] == "external_analysis_rule"]
        self.assertGreater(len(ext), 1000)
        # 每条 D 层规则都通过了双向回源（进入 accepted 即证据核验通过）
        for r in ext[:50]:
            self.assertTrue(r["autonomous_review"]["evidence_verified"])
            self.assertEqual(r["interpretation_level"], "external_llm")


if __name__ == "__main__":
    unittest.main()
