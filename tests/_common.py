"""测试公共工具：分层口径。

层级（评审建议的五层测试中的前四层落位）：
  unit（test_core/test_review）      —— 不加载真实语料，<5s
  fixture（test_review make_poem 族）—— 手工微语料
  integration（test_apps/agent/server/integrations/adversarial_round2）
      —— 需要已生成资产；缺资产时**跳过并提示**，绝不在测试内触发
         完整 pipeline（评审指出的冷启动陷阱）
  pipeline —— 显式运行 `python3 -m hermes_poetry pipeline` 单独验证
"""
import unittest

from hermes_poetry import config


def require_assets() -> None:
    if not (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists():
        raise unittest.SkipTest(
            "集成层测试需要已生成的规则资产：请先运行 "
            "`python3 -m hermes_poetry pipeline`（测试不会代跑流水线）")
