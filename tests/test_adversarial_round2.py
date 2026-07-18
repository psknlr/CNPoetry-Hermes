"""第二轮对抗回归：多智能体审核发现的关键缺陷永久固化为测试。

每条测试对应一个曾被实测击穿的攻击面：修复回退即测试失败。
"""
import os as _os
import unittest as _ut
if _os.environ.get("HERMES_TEST_FAST") == "1":
    raise _ut.SkipTest("fast mode：跳过需装载语料/规则库的测试（HERMES_TEST_FAST=1）")


import unittest

from hermes_poetry import config


def _ensure():
    from tests._common import require_assets
    require_assets()


class TestFoldingEvidence(unittest.TestCase):
    """critical：t2s 折叠目标丢出 CJK 范围 → 伪造跨度过闸。"""

    def test_ext_b_target_not_dropped(self):
        from hermes_poetry.textutil import contains_verbatim, content_only, t2s
        self.assertEqual(len(content_only(t2s("勣"))), 1)
        self.assertFalse(contains_verbatim("功勣高於天", "功高"))
        self.assertFalse(contains_verbatim("为絺为绤", "为为绤"))
        self.assertTrue(contains_verbatim("为絺为绤", "为絺为绤"))

    def test_fabricated_span_rejected_end_to_end(self):
        _ensure()
        from hermes_poetry.corpus.normalize import load_poems
        from hermes_poetry.review.gates import PoemStore, ReviewPipeline
        from hermes_poetry.schemas import InitialRule
        poems = load_poems()
        getan = next(p for p in poems if "葛覃" in p.title)
        stem = getan.poem_id.replace("CNP_", "", 1)
        rule = InitialRule(
            initial_rule_id=f"IR_CNP_{stem}_099", poem_id=getan.poem_id,
            rule_type="theme_rule", if_conditions={"theme_markers": ["归"]},
            then_conclusions={"theme": "思乡羁旅"}, evidence_span="为为绤",
            evidence_type="original_text", strength="弱证",
            interpretation="x", interpretation_level="normalized", model_confidence=0.7)
        out = ReviewPipeline(PoemStore([getan])).review_rule(rule)
        self.assertEqual(out.autonomous_review.release_level, "rejected")


class TestCitationTamperedQuote(unittest.TestCase):
    """critical：改字引文不得经相似度兜底当作已核验。"""

    @classmethod
    def setUpClass(cls):
        _ensure()
        from hermes_poetry.agent.citation import CitationGuard
        from hermes_poetry.apps.engine import get_engine
        cls.engine = get_engine()
        cls.guard = CitationGuard(cls.engine.poems)

    def test_one_char_tamper_flagged(self):
        p = next(x for x in self.engine.poems if x.source == "CAOCAO" and len(x.text) < 40)
        quote = "".join(ch for ch in p.text if "㐀" <= ch <= "鿿")
        tampered = quote[:5] + ("寸" if quote[5] != "寸" else "尺") + quote[6:]
        rep = self.guard.check(f"「{tampered}」（{p.poem_id}）", allowed_ids=[p.poem_id])
        self.assertFalse(rep.ok)
        self.assertTrue(rep.quote_mismatches)

    def test_verbatim_still_passes(self):
        p = self.engine.poems[0]
        rep = self.guard.check(f"「{p.lines[0]}」（{p.poem_id}）", allowed_ids=[p.poem_id])
        self.assertTrue(rep.ok)


class TestCachePoisoning(unittest.TestCase):
    """critical：local 回退答案不得写入 litellm 缓存。"""

    def test_fallback_not_cached(self):
        from hermes_poetry.llm.client import LLMClient, LLMSettings
        from hermes_poetry.llm.providers import ChatResult

        class Boom:
            def chat(self, *a, **k):
                raise RuntimeError("transient")

        class Healthy:
            def chat(self, *a, **k):
                return ChatResult(content="健康回答", backend="litellm")

        import uuid
        s = LLMSettings(backend="litellm", model="test-model", cache=True)
        msgs = [{"role": "user", "content": f"缓存污染回归测试-{uuid.uuid4().hex}"}]
        c1 = LLMClient(settings=s, provider=Boom())
        c1._backend = "litellm"
        r1 = c1.chat(msgs)
        self.assertIn("回退", r1.content)
        c2 = LLMClient(settings=s, provider=Healthy())
        c2._backend = "litellm"
        r2 = c2.chat(msgs)
        self.assertIn("健康回答", r2.content)


class TestRhymePurity(unittest.TestCase):
    """critical：平/入声不得混入同一干净韵组。"""

    @classmethod
    def setUpClass(cls):
        _ensure()
        import json
        cls.groups = [json.loads(l) for l in
                      (config.RULES_RHYME_DIR / "rhyme_partners.jsonl").open(encoding="utf-8")]

    def test_no_mixed_tone_in_clean_groups(self):
        ping = set("人天年风来春声情长明")   # 常见平声韵脚
        ru = set("月客白雪石国节竹别")       # 常见入声韵脚
        for g in self.groups:
            if "异常" in g["note"]:
                continue  # 已如实标注低纯度的组不在此断言范围
            members = set(g["members"])
            self.assertFalse(members & ping and members & ru,
                             f"组 {g['label']} 平入声混杂")

    def test_yue_in_rusheng_group(self):
        holder = [g for g in self.groups if "月" in g["members"]]
        self.assertTrue(holder)
        self.assertLess(len(holder[0]["members"]), 100)


class TestGateHardening(unittest.TestCase):
    """major 闸门加固回归。"""

    def setUp(self):
        import tests.test_review as tr
        self.tr = tr
        from hermes_poetry.review.gates import PoemStore, ReviewPipeline
        self.pipe = ReviewPipeline(PoemStore([tr.make_poem()]))

    def test_unregistered_surface_rejected(self):
        # 意象 surface 与 canon 词库映射不符 → 拒绝
        rule = self.tr.make_rule(
            if_conditions={"imagery": ["柳"], "imagery_surface": ["明月"]})
        out = self.pipe.review_rule(rule)
        self.assertEqual(out.autonomous_review.release_level, "rejected")

    def test_semantic_fail_rejects(self):
        # 语义硬失败（未知题材）不得因分数高而发布
        rule = self.tr.make_rule(
            rule_type="theme_rule",
            if_conditions={"theme_markers": ["明月"]},
            then_conclusions={"theme": "不存在的题材"},
            evidence_span="举头望明月")
        out = self.pipe.review_rule(rule)
        self.assertEqual(out.autonomous_review.release_level, "rejected")

    def test_rule_id_poem_id_mismatch_rejected(self):
        rule = self.tr.make_rule(initial_rule_id="IR_CNP_OTHER_99999_001")
        out = self.pipe.review_rule(rule)
        self.assertEqual(out.autonomous_review.release_level, "rejected")

    def test_evidence_type_mislabel_hard_fails(self):
        # D层证据冒称本系统结论：按 evidence_type 判定，改 rule_type 绕不过
        rule = self.tr.make_rule(evidence_type="external_analysis",
                                 interpretation_level="normalized")
        out = self.pipe.review_rule(rule)
        self.assertEqual(out.autonomous_review.release_level, "rejected")


class TestIntertextCleanliness(unittest.TestCase):
    def test_no_kebai_in_rules(self):
        _ensure()
        import json
        rules = [json.loads(l) for l in
                 (config.RULES_INTERTEXT_DIR / "intertext_rules.jsonl").open(encoding="utf-8")]
        self.assertGreater(len(rules), 8000)  # 全量挖掘不截断
        bad = [r for r in rules if any(k in r["shared_span"]
                                       for k in ("正末", "正旦", "云了", "唱了", "了也"))]
        self.assertEqual(len(bad), 0)


class TestRagFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()
        from hermes_poetry.apps.engine import get_engine
        cls.engine = get_engine()

    def test_filtered_search_recall(self):
        hits = self.engine.rag.search("明月", top_k=8, author="李白")
        self.assertGreaterEqual(len(hits), 3)
        for h in hits:
            self.assertEqual(h["author"], "李白")

    def test_match_accepts_surface_forms(self):
        r = self.engine.match(imagery=["明月"])
        self.assertIn("月", r["query"]["imagery"])
        self.assertTrue(r["recommendations"])

    def test_teach_short_theme_name(self):
        r = self.engine.teach("思乡")
        self.assertEqual(r["lesson"]["topic"], "思乡羁旅")

    def test_no_shidiaoming_cipai(self):
        self.assertNotIn("失调名", self.engine.cipai_profiles)

    def test_yuanqu_qupai_extracted(self):
        self.assertIn("点绛唇", self.engine.cipai_profiles)

    def test_genre_alias_folded(self):
        from hermes_poetry.lexicon import canonical_genre
        self.assertEqual(canonical_genre("七言絕句"), "七绝")


if __name__ == "__main__":
    unittest.main()
