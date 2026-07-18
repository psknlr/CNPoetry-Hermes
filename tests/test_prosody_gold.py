"""格律金标测试：真实名作的起式判定（纯单元层，不加载语料）。

金标口径：起式以首句第二字平仄定名（王力惯例）；七言与五言的
名称↔句式序列映射相反（曾发生反转事故，此处永久固化）。
注：外部评审金标表中「山居秋暝=仄起」有误——首句第二字「山」
为平声（先韵），正确为平起首句不入韵。
"""
import unittest

from hermes_poetry.extract.phonology import get_phonology

GOLD = [
    ("春望", ["国破山河在", "城春草木深", "感时花溅泪", "恨别鸟惊心",
              "烽火连三月", "家书抵万金", "白头搔更短", "浑欲不胜簪"],
     ["深", "心", "金", "簪"], "仄起不入韵", False),
    ("登高", ["风急天高猿啸哀", "渚清沙白鸟飞回", "无边落木萧萧下", "不尽长江滚滚来",
              "万里悲秋常作客", "百年多病独登台", "艰难苦恨繁霜鬓", "潦倒新停浊酒杯"],
     ["回", "来", "台", "杯"], "仄起入韵", True),
    ("无题·相见时难", ["相见时难别亦难", "东风无力百花残", "春蚕到死丝方尽", "蜡炬成灰泪始干",
                       "晓镜但愁云鬓改", "夜吟应觉月光寒", "蓬山此去无多路", "青鸟殷勤为探看"],
     ["残", "干", "寒", "看"], "仄起入韵", True),
    ("山居秋暝", ["空山新雨后", "天气晚来秋", "明月松间照", "清泉石上流",
                  "竹喧归浣女", "莲动下渔舟", "随意春芳歇", "王孙自可留"],
     ["秋", "流", "舟", "留"], "平起不入韵", False),
]


class TestProsodyGold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ph = get_phonology()
        if not cls.ph.ready:
            raise unittest.SkipTest("广韵数据缺失")

    def test_qishi_gold(self):
        for name, lines, feet, expect_qishi, expect_first in GOLD:
            r = self.ph.analyze_poem(lines, feet)
            self.assertEqual(r["template_match"]["best_fit"], expect_qishi,
                             f"{name} 起式判定错误")
            self.assertEqual(r["first_line_rhymes"], expect_first,
                             f"{name} 首句入韵判定错误")

    def test_seven_char_naming_not_inverted(self):
        # 七言平起不入韵首句应为 平平仄仄平平仄（第二字平）
        t7 = self.ph._template_lines("平起不入韵", 7, 4)
        self.assertEqual(t7[0][1], "平")
        t7z = self.ph._template_lines("仄起入韵", 7, 4)
        self.assertEqual(t7z[0][1], "仄")
        self.assertEqual(t7z[0][-1], "平")  # 入韵式首句收平
        # 五言仄起不入韵首句第二字仄
        t5 = self.ph._template_lines("仄起不入韵", 5, 4)
        self.assertEqual(t5[0][1], "仄")


if __name__ == "__main__":
    unittest.main()
