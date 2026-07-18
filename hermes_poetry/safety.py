"""角色治理与表述守卫。

诗词域没有临床风险，但有同样致命的「学术性危害」：杜撰诗句、张冠李戴、
把语料归纳冒称权威定论。守卫策略：
  * 引用完整性由 CitationGuard 强制（代码层，不靠提示词）；
  * 角色决定表述口径与工具面（reader/student/researcher）；
  * 生成创作类请求（代写诗）明确声明创作内容非语料原文，禁止伪托古人。
"""
from __future__ import annotations

import re
from typing import Dict, List

ROLES = ("reader", "student", "researcher")

ROLE_LABEL = {"reader": "读者端", "student": "学生端", "researcher": "研究端"}

# 伪托检测：请求把生成内容说成古人作品
RE_FORGERY = re.compile(r"(?:假装|冒充|伪造|谎称|说成)(?:是)?(?:李白|杜甫|苏轼|古人|唐诗|宋词)")
RE_COMPOSE = re.compile(r"(?:帮我写|替我写|创作|作一首|写一首)")


def infer_role(question: str) -> str:
    q = question or ""
    if re.search(r"(?:统计|分布|共现|网络|频次|计量|语料|数据|论文|研究)", q):
        return "researcher"
    if re.search(r"(?:作业|背诵|考试|默写|练习|学习|入门)", q):
        return "student"
    return "reader"


def intent_guard(question: str) -> Dict:
    """返回 {allowed, notice}。创作请求放行但强制声明；伪托请求拒绝。"""
    q = question or ""
    if RE_FORGERY.search(q):
        return {"allowed": False,
                "notice": "不能把生成内容伪托为古人作品：这会污染文献归属。"
                          "可以为你创作标明「今人拟作」的作品，或检索真实原作。"}
    if RE_COMPOSE.search(q):
        return {"allowed": True,
                "notice": "【创作声明】以下如含新创作内容，均为今人拟作，非语料原文；"
                          "引用的古典诗句仍逐字回源并带 poem_id。"}
    return {"allowed": True, "notice": ""}


def governed(payload: Dict, role: str) -> Dict:
    payload = dict(payload)
    payload["_role"] = role
    payload["_role_label"] = ROLE_LABEL.get(role, role)
    return payload


def role_tool_scope(role: str, all_tools: List[str]) -> List[str]:
    """工具面按角色裁剪（能力层最小权限，非提示词约束）。"""
    if role == "reader":
        heavy = {"poetry_research", "poetry_stats"}
        return [t for t in all_tools if t not in heavy]
    return list(all_tools)
