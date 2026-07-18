"""核心单元测试：文本工具、计量、标注、检索（不依赖已生成的规则库）。"""
import unittest

from hermes_poetry.extract.annotate import annotate_poem
from hermes_poetry.extract.metrics import apply_metrics, detect_form
from hermes_poetry.rag.bm25 import BM25Index
from hermes_poetry.schemas import Poem
from hermes_poetry.textutil import (contains_verbatim, similarity, split_lines,
                                    t2s, tokenize)


class TestTextUtil(unittest.TestCase):
    def test_t2s_folds_traditional(self):
        self.assertEqual(t2s("牀前明月光"), t2s("床前明月光"))
        self.assertEqual(t2s("楊柳"), "杨柳")

    def test_contains_verbatim_cross_script(self):
        self.assertTrue(contains_verbatim("床前明月光，疑是地上霜。", "牀前明月光"))
        self.assertTrue(contains_verbatim("大漠孤煙直，長河落日圓。", "大漠孤烟直"))
        self.assertFalse(contains_verbatim("床前明月光", "海上生明月"))
        self.assertFalse(contains_verbatim("床前明月光", ""))

    def test_tokenize_bigrams(self):
        toks = tokenize("明月光")
        self.assertIn("明月", toks)
        self.assertIn("月光", toks)
        self.assertIn("明", toks)

    def test_similarity(self):
        self.assertGreater(similarity("床前明月光", "床前看月光"), 0.3)
        self.assertEqual(similarity("床前明月光", "完全无关文本"), 0.0)

    def test_split_lines(self):
        lines = split_lines(["春眠不覺曉，處處聞啼鳥。", "夜來風雨聲，花落知多少。"])
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "春眠不覺曉")


def poem(lines, **kw):
    base = dict(poem_id="CNP_TEST_00001", source="TEST", book="t", dynasty="唐",
                author="佚名", title="t", lines=lines, text="\n".join(lines))
    base.update(kw)
    return Poem(**base)


class TestMetrics(unittest.TestCase):
    def test_wujue(self):
        p = poem(["春眠不覺曉", "處處聞啼鳥", "夜來風雨聲", "花落知多少"])
        m = detect_form(p)
        self.assertEqual(m["form_metric"], "五绝")
        self.assertEqual(m["rhyme_feet"], ["鳥", "少"])

    def test_qilu(self):
        p = poem(["昔人已乘黃鶴去"] * 8)
        self.assertEqual(detect_form(p)["form_metric"], "七律")

    def test_ci_by_cipai(self):
        p = poem(["明月幾時有", "把酒問青天"], cipai="水调歌头")
        self.assertEqual(detect_form(p)["form_metric"], "词")

    def test_tag_overrides_metric(self):
        p = poem(["春眠不覺曉", "處處聞啼鳥", "夜來風雨聲", "花落知多少"],
                 tags=["五言绝句"])
        apply_metrics(p)
        self.assertEqual(p.genre, "五绝")
        self.assertEqual(p.genre_source, "tag")


class TestAnnotate(unittest.TestCase):
    def test_imagery_longest_first(self):
        p = poem(["舉頭望明月", "低頭思故鄉"])
        annotate_poem(p)
        self.assertIn("月", p.imagery)
        self.assertIn("思念怀想", p.emotions)

    def test_negated_emotion_not_positive(self):
        p = poem(["此行不愁思"])
        hits = annotate_poem(p)
        # 「不愁」→ 否定情感，不计正向（「思」不与愁重叠时仍可为正向）
        neg = [x for h in hits for x in h.negated_emotions]
        self.assertTrue(any(cat == "愁苦哀伤" for cat, _ in neg))
        pos = [m for h in hits for c, m in h.emotions if c == "愁苦哀伤"]
        self.assertFalse(pos)


class TestBM25(unittest.TestCase):
    def test_search_ranks_relevant_first(self):
        idx = BM25Index()
        idx.add("a", "床前明月光 疑是地上霜")
        idx.add("b", "大漠孤煙直 長河落日圓")
        idx.finalize()
        hits = idx.search("明月")
        self.assertEqual(hits[0][0], "a")


if __name__ == "__main__":
    unittest.main()
