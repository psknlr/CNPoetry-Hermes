"""PoetryAgent：单智能体 ReAct 循环 + 守卫驱动的反思修复。

流程：意图守卫 → 角色裁剪工具面 → 有界工具循环（全局预算逐次核减）→
CitationGuard 作为控制器（发现违规把裁定回灌重试，最多两轮）→ 标注落款。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from ..llm import get_client
from ..llm.prompts import agent_system
from ..safety import governed, infer_role, intent_guard
from .citation import CitationGuard
from .tools import ToolRegistry

RE_POEM_ID = re.compile(r"CNP_[A-Z0-9]+_\d{5}")


class PoetryAgent:
    def __init__(self, registry: Optional[ToolRegistry] = None, client=None,
                 max_steps: int = 5, max_tool_calls: int = 10, max_repair_rounds: int = 2):
        self.registry = registry or ToolRegistry()
        self.client = client or get_client()
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.max_repair_rounds = max_repair_rounds
        self.guard = CitationGuard(self.registry.engine.poems)

    def ask(self, question: str, role: str = "") -> Dict:
        role = role or infer_role(question)
        ig = intent_guard(question)
        if not ig["allowed"]:
            return governed({"question": question, "answer": ig["notice"],
                             "blocked": True, "trace": []}, role)
        registry = self.registry.for_role(role)
        messages = [{"role": "system", "content": agent_system(role)}]
        skill_route = None
        try:
            from ..skills.skill_rag import get_skill_rag
            skill_route = get_skill_rag().route(question)
        except Exception:
            skill_route = None
        if skill_route:
            messages.append({"role": "system", "content":
                             f"路由提示（SkillRAG）：技能 {skill_route['skill']}，"
                             f"建议工具 {skill_route['tool']}，"
                             f"参数 {json.dumps(skill_route['args'], ensure_ascii=False)}。"
                             "仅当与问题相符时采用，不相符时按自己的判断取证。"})
        messages.append({"role": "user", "content": question})
        tool_results: List[Dict] = []
        answer = self._react(messages, tool_results, registry)
        allowed_ids = self._evidence_ids(tool_results)
        report = self.guard.check(answer, allowed_ids=allowed_ids)
        rounds = 0
        while not report.ok and rounds < self.max_repair_rounds:
            rounds += 1
            verdict = json.dumps(report.to_dict(), ensure_ascii=False)
            messages.append({"role": "assistant", "content": answer})
            messages.append({"role": "user", "content":
                             f"引用核验未通过：{verdict}\n请仅使用本轮工具证据中的 poem_id 重写答案，"
                             "删除无法回源的引用与引文。"})
            answer = self._react(messages, tool_results, registry)
            report = self.guard.check(answer, allowed_ids=self._evidence_ids(tool_results))
        # 第二道闸门（控制器而非尾注）：事实违例 → 强制重写一轮；
        # 仍违例 → 不发布错误正文，只返回已验证的更正信息
        from .claims import ClaimGuard, annotate_claims
        cguard = ClaimGuard(self.registry.engine)
        claim_report = cguard.check(answer)
        if claim_report.violations:
            messages.append({"role": "assistant", "content": answer})
            messages.append({"role": "user", "content":
                             "论断核验发现事实错误：" +
                             json.dumps(claim_report.violations, ensure_ascii=False) +
                             "\n请修正后重写答案（不得保留错误归属/数字）。"})
            answer = self._react(messages, tool_results, registry)
            report = self.guard.check(answer, allowed_ids=self._evidence_ids(tool_results))
            claim_report = cguard.check(answer)
            if claim_report.violations:
                fixes = "；".join(v["problem"] for v in claim_report.violations[:3])
                answer = ("回答未通过论断核验，为避免传播错误信息不予发布。"
                          f"已验证的更正：{fixes}")
                report = self.guard.check(answer, allowed_ids=None)
                claim_report = cguard.check(answer)
        if ig["notice"]:
            answer = ig["notice"] + "\n\n" + answer
        final = self.guard.annotate(answer, report)
        final = annotate_claims(final, claim_report)
        return governed({
            "question": question,
            "answer": final,
            "citation_report": report.to_dict(),
            "claim_report": claim_report.to_dict(),
            "tool_trace": [{"tool": t["tool"], "arguments": t["arguments"]} for t in tool_results],
            "evidence_ids": self._evidence_ids(tool_results),
            "skill_route": skill_route,
            "backend": self.client.backend,
        }, role)

    # ── 有界 ReAct 循环 ──────────────────────────────────────────
    def _react(self, messages: List[Dict], tool_results: List[Dict], registry) -> str:
        specs = registry.specs()
        for _ in range(self.max_steps):
            over = len(tool_results) >= self.max_tool_calls
            res = self.client.chat(messages, tools=None if over else specs)
            if res.tool_calls:
                messages.append({"role": "assistant", "content": res.content or None,
                                 "tool_calls": [{"id": tc.id, "type": "function",
                                                 "function": {"name": tc.name,
                                                              "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                                                for tc in res.tool_calls]})
                for tc in res.tool_calls:
                    if len(tool_results) >= self.max_tool_calls:
                        messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name,
                                         "content": json.dumps({"error": "BUDGET_EXHAUSTED"})})
                        continue
                    result = registry.call(tc.name, tc.arguments)
                    tool_results.append({"tool": tc.name, "arguments": tc.arguments, "result": result})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name,
                                     "content": json.dumps(result, ensure_ascii=False)})
                continue
            return res.content
        # 步数耗尽：禁用工具做一轮收尾综合，绝不返回空答案
        res = self.client.chat(messages + [{
            "role": "user",
            "content": "工具预算已用尽。请基于以上工具证据直接作答（引用其中的 poem_id）。"}],
            tools=None)
        return res.content

    @staticmethod
    def _evidence_ids(tool_results: List[Dict]) -> List[str]:
        ids: List[str] = []
        for t in tool_results:
            blob = json.dumps(t.get("result", {}), ensure_ascii=False)
            for m in RE_POEM_ID.findall(blob):
                if m not in ids:
                    ids.append(m)
        return ids
