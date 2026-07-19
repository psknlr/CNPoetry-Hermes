"""第四轮功能回归：韵伴例证/诗人别名/词谱/全量例词/意象例证/飞花令/古风创作/多后端。"""
import os as _os
import unittest as _ut
if _os.environ.get("HERMES_TEST_FAST") == "1":
    raise _ut.SkipTest("fast mode：跳过需装载语料/规则库的测试（HERMES_TEST_FAST=1）")


import unittest


def _engine():
    from tests._common import require_assets
    require_assets()
    from hermes_poetry.apps.engine import get_engine
    return get_engine()


class TestAuthorAlias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = _engine()

    def test_sudongpo_resolves(self):
        r = self.e.resolve_author("苏东坡")
        self.assertEqual(r["status"], "unique")
        self.assertEqual(r["author"], "苏轼")
        self.assertIn("别名归并", r["via"])

    def test_traditional_alias(self):
        self.assertEqual(self.e.resolve_author("蘇東坡")["author"], "苏轼")

    def test_direct_name_no_via(self):
        r = self.e.resolve_author("李白")
        self.assertEqual((r["status"], r["via"]), ("unique", ""))

    def test_unknown_gives_suggestions(self):
        r = self.e.resolve_author("不存在的诗人")
        self.assertEqual(r["status"], "not_found")


class TestCipuAndCipai(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = _engine()

    def test_cipu_loaded_153(self):
        from hermes_poetry.corpus.cipu import load_cipu
        self.assertEqual(len(load_cipu()), 153)

    def test_yijiangnan_resolves_with_pu_and_corpus(self):
        r = self.e.cipai_query("忆江南")
        self.assertEqual(r["cipu"]["cipai"], "忆江南")
        self.assertIn("望江南", r["cipu"]["aliases"])
        self.assertIsNotNone(r["cipai_profile"])  # 归并到语料复合键
        self.assertGreater(len(r["all_poems"]), 20)

    def test_all_poems_complete(self):
        r = self.e.cipai_query("水调歌头")
        self.assertEqual(len(r["all_poems"]), r["cipai_profile"]["n_poems"])
        self.assertEqual(len(r["all_poems"]), 40)

    def test_pattern_symbols_converted(self):
        r = self.e.cipai_query("忆江南")
        pat = r["cipu"]["forms"][0]["pattern"]
        self.assertTrue(set(pat) & set("○●⊙△"))
        self.assertFalse(set(pat) & set("－＋│％＊"))  # 原始符号不外泄


class TestImageryExamples(unittest.TestCase):
    def test_full_browse_with_quotes(self):
        e = _engine()
        r = e.imagery_examples("月")
        self.assertGreater(r["n_listed"], 100)
        self.assertGreaterEqual(r["n_total"], r["n_listed"])
        first = r["examples"][0]
        self.assertTrue(first["poem_id"].startswith("CNP_"))
        self.assertTrue(first["quote"])  # 命中原句非空


class TestRhymeVerseExamples(unittest.TestCase):
    def test_examples_clickable_and_rhyming(self):
        e = _engine()
        r = e.rhyme_query("秋")
        g = r["groups"][0]
        self.assertTrue(g["verse_examples"])
        ex = g["verse_examples"][0]
        self.assertIn("poem_id", ex)
        self.assertGreaterEqual(len(ex["rhyming_lines"]), 2)
        feet = {x["foot"] for x in ex["rhyming_lines"]}
        self.assertTrue(feet <= set(g["members"]))


class TestFeihua(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = _engine()

    def test_reply_contains_char_and_sourced(self):
        r = self.e.feihua("花", round_no=1)
        self.assertIn("花", r["reply"]["line"].replace("華", "花"))
        self.assertIn(r["reply"]["poem_id"], self.e.by_id)

    def test_valid_user_line(self):
        r = self.e.feihua("花", user_line="感时花溅泪")
        self.assertTrue(r["user_check"]["valid"])
        self.assertEqual(r["user_check"]["title"], "春望")

    def test_fabricated_line_rejected(self):
        r = self.e.feihua("花", user_line="花开月圆真好呀")
        self.assertFalse(r["user_check"]["valid"])

    def test_line_without_char_rejected(self):
        r = self.e.feihua("花", user_line="白日依山尽")
        self.assertFalse(r["user_check"]["valid"])
        self.assertIn("令字", r["user_check"]["reason"])

    def test_exclude_respected(self):
        r1 = self.e.feihua("月", round_no=1)
        r2 = self.e.feihua("月", exclude_ids=[r1["reply"]["poem_id"]], round_no=1)
        self.assertNotEqual(r1["reply"]["poem_id"], r2["reply"]["poem_id"])


class TestGufeng(unittest.TestCase):
    def test_offline_plan_honest(self):
        from hermes_poetry.apps.compose import compose_gufeng
        g = compose_gufeng(theme="离乡", rhyme_char="秋", n_lines=16)
        self.assertIsNone(g["poem"])  # local 不代笔
        self.assertEqual(g["plan"]["segments"], 4)
        self.assertEqual(g["plan"]["rhyme_plan"][0]["group"].count("·") >= 1, True)
        self.assertIn("秋", g["plan"]["rhyme_plan"][0]["candidates"])
        self.assertEqual(g["plan"]["references"][0]["title"], "長恨歌")

    def test_generation_verify_repair(self):
        from hermes_poetry.llm.client import LLMClient, LLMSettings
        from hermes_poetry.llm.providers import ChatResult, ScriptedProvider
        from hermes_poetry.apps.compose import compose_gufeng
        bad = "\n".join(["少年负剑出乡关", "身外浮名付酒殇",
                         "回望千门灯火里", "一蓑烟雨梦潇湘",
                         "孤舟夜泊枫桥岸", "霜月满天照客愁",
                         "鸿雁不传家信远", "长歌一曲寄东流"])
        good = "\n".join(["少年负剑出乡关", "身外浮名一叶舟",
                          "回望千门灯火里", "半肩风雨半肩秋",
                          "孤帆夜泊枫桥岸", "霜月满天照客愁",
                          "鸿雁不传家信远", "长歌一曲寄东流"])
        sp = ScriptedProvider([ChatResult(content=bad, backend="scripted"),
                               ChatResult(content=good, backend="scripted")])
        c = LLMClient(settings=LLMSettings(backend="scripted", cache=False), provider=sp)
        c._backend = "poe"  # 模拟真实后端
        g = compose_gufeng(theme="离乡远行", rhyme_char="秋", n_lines=8, client=c)
        self.assertTrue(g["verification"]["passed"])  # 首稿被拒，二稿通过
        self.assertEqual(len(g["poem"]), 8)


class TestNativeBackends(unittest.TestCase):
    def test_resolution_and_fallback(self):
        import os
        from hermes_poetry.llm.client import LLMClient, LLMSettings
        for k in ("POE_API_KEY", "MINIMAX_API_KEY", "AZURE_OPENAI_ENDPOINT",
                  "HERMES_LLM_BASE_URL"):
            os.environ.pop(k, None)
        # 无钥时显式 azure → 构造失败优雅回退 local
        self.assertEqual(LLMClient(settings=LLMSettings(backend="azure")).backend, "local")
        os.environ["POE_API_KEY"] = "test-key"
        try:
            self.assertEqual(LLMSettings(backend="auto").resolve_backend(), "poe")
        finally:
            os.environ.pop("POE_API_KEY")

    def test_available_covers_native(self):
        from hermes_poetry.llm.client import REAL_BACKENDS
        for b in ("azure", "poe", "minimax", "openai_compat", "litellm"):
            self.assertIn(b, REAL_BACKENDS)

    def test_minimax_region_endpoints(self):
        import os
        from hermes_poetry.llm.client import LLMSettings
        from hermes_poetry.llm.providers import OpenAICompatProvider
        os.environ["MINIMAX_API_KEY"] = "test"
        s = LLMSettings(backend="minimax", model="MiniMax-M3")
        try:
            for k in ("MINIMAX_REGION", "MINIMAX_BASE_URL"):
                os.environ.pop(k, None)
            self.assertIn("api.minimaxi.com", OpenAICompatProvider(s, "minimax").url)  # 国内默认
            for region in ("intl", "国际", "海外"):
                os.environ["MINIMAX_REGION"] = region
                self.assertIn("api.minimax.io", OpenAICompatProvider(s, "minimax").url)
            os.environ["MINIMAX_BASE_URL"] = "https://proxy.example.com/v1"
            self.assertIn("proxy.example.com", OpenAICompatProvider(s, "minimax").url)
        finally:
            for k in ("MINIMAX_API_KEY", "MINIMAX_REGION", "MINIMAX_BASE_URL"):
                os.environ.pop(k, None)


if __name__ == "__main__":
    unittest.main()
