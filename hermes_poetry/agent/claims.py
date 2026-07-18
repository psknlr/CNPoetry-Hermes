"""ClaimGuard：论断分型核验——CitationGuard 之上的第二道闸门。

CitationGuard 保证「引文真实」；ClaimGuard 检查「论断本身」：
  * FactualClaim   作者/朝代/体裁归属 → 查库核验；
  * MetricClaim    句数/字数 数字断言 → 算法复算；
  * InterpretiveClaim 意象功能/情感/意义 → 要求证据绑定 + 限定语，
    无限定的强解释（断言古人心理状态/唯一确解）标记为过度阐释风险。

诚实边界：这是启发式的下界核验——能抓住明显的张冠李戴、数字错误
与无证据强解释；不能证明一段解释在诗学上正确。报告字段如实标注
verifier 版本与边界。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..textutil import t2s

RE_POEM_ID = re.compile(r"CNP_[A-Z0-9]+_\d{5}")
RE_SENT = re.compile(r"[^。！？\n]+[。！？]?")

# 作者归属句式：「《X》是/为 Y 所作/的诗」「Y 的《X》」
RE_ATTRIB = re.compile(r"[《〈]([^》〉]{1,20})[》〉](?:是|为|乃)([㐀-鿿]{2,4})(?:所作|的作品|写的|之作)")
RE_ATTRIB2 = re.compile(r"([㐀-鿿]{2,4})的[《〈]([^》〉]{1,20})[》〉]")
RE_DYNASTY = re.compile(r"[《〈]([^》〉]{1,20})[》〉]是([㐀-鿿]{1,3})代?(?:的诗|的词|作品)")
RE_LINECOUNT = re.compile(r"[《〈]([^》〉]{1,20})[》〉][^。]{0,12}?(?:共|全诗)?([一二两三四五六七八九十百\d]+)句")
# 强解释标记：断言心理状态/唯一确解而无限定语
RE_STRONG_INTERP = re.compile(r"(?:说明|证明|表明|一定|必然|无疑|只能理解为)")
RE_HEDGE = re.compile(r"(?:或|可能|大概|似|可读作|一种理解|语料显示|据统计|倾向|多与)")
RE_PSYCH = re.compile(r"(?:绝望|抑郁|崩溃|发疯|自杀|精神失常)")

_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9, "十": 10, "十二": 12, "十四": 14, "十六": 16}


def _to_int(s: str) -> Optional[int]:
    if s.isdigit():
        return int(s)
    return _CN_NUM.get(s)


@dataclass
class ClaimReport:
    claims: List[Dict] = field(default_factory=list)
    violations: List[Dict] = field(default_factory=list)
    overclaim_warnings: List[Dict] = field(default_factory=list)
    verifier: str = "claim_heuristics_v1"
    note: str = "启发式下界核验：抓归属/数字/无证据强解释错误，不证明解释诗学正确。"

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> Dict:
        return {"ok": self.ok, "claims": self.claims, "violations": self.violations,
                "overclaim_warnings": self.overclaim_warnings,
                "verifier": self.verifier, "note": self.note}


class ClaimGuard:
    def __init__(self, engine):
        self.engine = engine

    def _find_poem(self, title: str):
        return self.engine.resolve_poem(f"《{title}》")

    def check(self, answer: str) -> ClaimReport:
        rep = ClaimReport()
        text = answer or ""
        # ── FactualClaim：作者归属 ──
        for m in list(RE_ATTRIB.finditer(text)):
            title, author = m.group(1), m.group(2)
            self._check_attrib(rep, title, author, m.group(0))
        for m in list(RE_ATTRIB2.finditer(text)):
            author, title = m.group(1), m.group(2)
            if len(author) >= 2 and t2s(author) in self.engine.author_profiles or \
                    self.engine.rag._author_index.get(t2s(author)):
                self._check_attrib(rep, title, author, m.group(0))
        # ── FactualClaim：朝代 ──
        for m in RE_DYNASTY.finditer(text):
            title, dyn = m.group(1), m.group(2)
            p = self._find_poem(title)
            if p and dyn and dyn not in p.dynasty and p.dynasty not in dyn:
                rep.violations.append({
                    "type": "FactualClaim", "claim": m.group(0),
                    "problem": f"朝代不符：语料记载《{p.title}》为{p.dynasty}代（{p.poem_id}）"})
            elif p:
                rep.claims.append({"type": "FactualClaim", "claim": m.group(0), "verified": True})
        # ── MetricClaim：句数 ──
        for m in RE_LINECOUNT.finditer(text):
            title, num_s = m.group(1), m.group(2)
            n = _to_int(num_s)
            p = self._find_poem(title)
            if p and n is not None:
                actual = (p.metrics or {}).get("line_count")
                if actual and actual != n:
                    rep.violations.append({
                        "type": "MetricClaim", "claim": m.group(0),
                        "problem": f"句数复算不符：《{p.title}》实为 {actual} 句（{p.poem_id}）"})
                else:
                    rep.claims.append({"type": "MetricClaim", "claim": m.group(0), "verified": True})
        # ── InterpretiveClaim：无证据/无限定的强解释 ──
        for sent in RE_SENT.findall(text):
            if "【" in sent:
                continue
            strong = RE_STRONG_INTERP.search(sent)
            psych = RE_PSYCH.search(sent)
            if not (strong or psych):
                continue
            has_evidence = bool(RE_POEM_ID.search(sent))
            has_hedge = bool(RE_HEDGE.search(sent))
            if psych and not has_hedge:
                rep.overclaim_warnings.append({
                    "type": "InterpretiveClaim", "claim": sent.strip()[:60],
                    "problem": "对古人心理状态的强断言（引文真实≠推论成立），须加限定或删除"})
            elif strong and not (has_evidence or has_hedge):
                rep.overclaim_warnings.append({
                    "type": "InterpretiveClaim", "claim": sent.strip()[:60],
                    "problem": "强解释无证据绑定亦无限定语，存在过度阐释风险"})
        return rep

    def _check_attrib(self, rep: ClaimReport, title: str, author: str, claim: str) -> None:
        p = self._find_poem(title)
        if p is None:
            return
        if t2s(p.author) != t2s(author):
            # 同题异作：语料中存在该作者的同题作品则不算违例
            others = self.engine.rag._title_index.get(t2s(title), [])
            if not any(t2s(o.author) == t2s(author) for o in others):
                rep.violations.append({
                    "type": "FactualClaim", "claim": claim,
                    "problem": f"作者归属不符：语料记载《{p.title}》为{p.author}作（{p.poem_id}）",
                    "candidates": [{"poem_id": o.poem_id, "author": o.author}
                                   for o in others[:3]]})
                return
        rep.claims.append({"type": "FactualClaim", "claim": claim, "verified": True})


def annotate_claims(answer: str, rep: ClaimReport) -> str:
    if rep.ok and not rep.overclaim_warnings:
        return answer
    lines = ["", "【论断核验】"]
    for v in rep.violations[:4]:
        lines.append(f"✗ {v['problem']}")
    for w in rep.overclaim_warnings[:3]:
        lines.append(f"⚠ {w['problem']}：「{w['claim']}…」")
    return (answer or "") + "\n".join(lines)
