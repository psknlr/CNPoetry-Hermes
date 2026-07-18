"""对抗性审核测试：注入伪造证据并断言闸门拒绝或修复。

这是「无原文，不成论断」的可执行契约（对应伤寒-赫尔墨斯 test_review.py）。
"""
import unittest

from hermes_poetry.review.gates import PoemStore, ReviewPipeline
from hermes_poetry.schemas import InitialRule, Poem


def make_poem(**kw):
    base = dict(
        poem_id="CNP_TEST_00001",
        source="TEST", book="测试集", dynasty="唐", author="李白", title="静夜思",
        lines=["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"],
        text="床前明月光，疑是地上霜。\n举头望明月，低头思故乡。",
        metrics={"line_count": 4, "char_counts": [5, 5, 5, 5], "uniform": True,
                 "char_per_line": 5, "form_metric": "五绝", "rhyme_feet": ["霜", "乡"],
                 "total_chars": 20},
        genre="五绝", genre_source="metric",
    )
    base.update(kw)
    return Poem(**base)


def make_rule(**kw):
    base = dict(
        initial_rule_id="IR_CNP_TEST_00001_001",
        poem_id="CNP_TEST_00001",
        rule_type="imagery_emotion_rule",
        if_conditions={"imagery": ["月"], "imagery_surface": ["明月"]},
        then_conclusions={"emotion": "思念怀想", "emotion_marker": "思"},
        evidence_span="举头望明月，低头思故乡",
        evidence_type="original_text",
        strength="邻证",
        interpretation="明月与思乡同联共现。",
        interpretation_level="normalized",
        model_confidence=0.85,
    )
    base.update(kw)
    return InitialRule(**base)


class TestReviewGates(unittest.TestCase):
    def setUp(self):
        self.store = PoemStore([make_poem()])
        self.pipe = ReviewPipeline(self.store)

    def test_good_rule_passes(self):
        rule = self.pipe.review_rule(make_rule())
        self.assertTrue(rule.autonomous_review.evidence_verified)
        self.assertIn(rule.autonomous_review.release_level, ("gold", "silver", "bronze"))

    def test_fabricated_evidence_rejected(self):
        rule = self.pipe.review_rule(make_rule(evidence_span="海上生明月，天涯共此时"))
        self.assertEqual(rule.autonomous_review.release_level, "rejected")
        self.assertFalse(rule.autonomous_review.evidence_verified)

    def test_wrong_poem_id_rejected(self):
        rule = self.pipe.review_rule(make_rule(poem_id="CNP_TEST_09999"))
        self.assertEqual(rule.autonomous_review.release_level, "rejected")

    def test_unattested_imagery_rejected(self):
        # 断言证据句里根本没有的意象表面形式
        rule = self.pipe.review_rule(make_rule(
            if_conditions={"imagery": ["柳"], "imagery_surface": ["杨柳"]}))
        self.assertEqual(rule.autonomous_review.release_level, "rejected")

    def test_negated_emotion_hard_fails(self):
        poem = make_poem(poem_id="CNP_TEST_00002",
                         lines=["此行不愁思", "胜赏欲与谁"],
                         text="此行不愁思，胜赏欲与谁。")
        store = PoemStore([poem])
        pipe = ReviewPipeline(store)
        rule = make_rule(poem_id="CNP_TEST_00002",
                         initial_rule_id="IR_CNP_TEST_00002_001",
                         if_conditions={"imagery": ["月"], "imagery_surface": ["月"]},
                         then_conclusions={"emotion": "愁苦哀伤", "emotion_marker": "愁"},
                         evidence_span="此行不愁思")
        out = pipe.review_rule(rule)
        # 「不愁」被计为正向愁 → 批评硬失败 → 拒绝（月也不在句中，双重违规）
        self.assertEqual(out.autonomous_review.release_level, "rejected")

    def test_posthoc_term_moved_out_of_body(self):
        rule = self.pipe.review_rule(make_rule(
            then_conclusions={"emotion": "思念怀想", "emotion_marker": "思",
                              "device": "借景抒情"}))
        rv = rule.autonomous_review
        self.assertNotIn("借景抒情", str(rule.then_conclusions))
        self.assertTrue(any("posthoc" in r for r in rv.repairs))
        self.assertEqual(rule.interpretation_level, "model_inference")

    def test_strength_overclaim_downgraded(self):
        # 明月在句3、思在句4 —— 冒称显证（同句）应被降级为邻证
        rule = self.pipe.review_rule(make_rule(strength="显证"))
        self.assertEqual(rule.strength, "邻证")
        self.assertIn("strength_downgraded", rule.autonomous_review.repairs)

    def test_schema_violation_rejected(self):
        rule = self.pipe.review_rule(make_rule(rule_type="not_a_rule_type"))
        self.assertEqual(rule.autonomous_review.release_level, "rejected")

    def test_external_analysis_requires_dual_grounding(self):
        # D层规则：外部分析文本中不含该诗首句 → 拒绝
        store = PoemStore([make_poem()], external=[
            {"id": "77", "text": "完全无关的文本", "author": "李白"}])
        pipe = ReviewPipeline(store)
        rule = make_rule(rule_type="external_analysis_rule",
                         if_conditions={"external_id": "77", "external_dataset": "x"},
                         then_conclusions={"subject": "思乡诗"},
                         evidence_span="床前明月光",
                         evidence_type="external_analysis",
                         interpretation_level="external_llm")
        out = pipe.review_rule(rule)
        self.assertEqual(out.autonomous_review.release_level, "rejected")


if __name__ == "__main__":
    unittest.main()
