"""CitationGuard：引用核验（存在性 + 逐字引文 + 归属 + 本轮取证）。

三重核验（与伤寒-赫尔墨斯同构）：
  1. 存在性：被引 poem_id 必须存在于语料（不存在 = 杜撰）；
  2. 引文：引号内诗句必须逐字存在于某个被引作品（Dice 兜底），
     并检查就近归属（引文实际属于别的被引作品 → 归属警告）；
  3. 取证闭环：allowed_ids 之外的真实 poem_id 视为「存在≠取证」违规——
     传入空列表即 fail-closed：零取证时连猜中的真实编号也不放行。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..schemas import Poem
from ..textutil import contains_verbatim, similarity, t2s

RE_POEM_ID = re.compile(r"CNP_[A-Z0-9]+_\d{5}")
RE_QUOTE = re.compile(r"[「『“\"]([^」』”\"]{4,60})[」』”\"]")


@dataclass
class CitationReport:
    cited_ids: List[str] = field(default_factory=list)
    verified_ids: List[str] = field(default_factory=list)
    unsupported_ids: List[str] = field(default_factory=list)
    outside_evidence_ids: List[str] = field(default_factory=list)
    quote_mismatches: List[Dict] = field(default_factory=list)
    attribution_warnings: List[Dict] = field(default_factory=list)
    has_any_citation: bool = False

    @property
    def ok(self) -> bool:
        return not (self.unsupported_ids or self.quote_mismatches or self.outside_evidence_ids)

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok,
            "cited_ids": self.cited_ids,
            "verified_ids": self.verified_ids,
            "unsupported_ids": self.unsupported_ids,
            "outside_evidence_ids": self.outside_evidence_ids,
            "quote_mismatches": self.quote_mismatches,
            "attribution_warnings": self.attribution_warnings,
            "has_any_citation": self.has_any_citation,
        }


class CitationGuard:
    def __init__(self, poems: List[Poem]):
        self.store: Dict[str, Poem] = {p.poem_id: p for p in poems}

    def check(self, answer: str, allowed_ids: Optional[List[str]] = None) -> CitationReport:
        rep = CitationReport()
        ids = list(dict.fromkeys(RE_POEM_ID.findall(answer or "")))
        rep.cited_ids = ids
        rep.has_any_citation = bool(ids)
        allowed = set(allowed_ids) if allowed_ids is not None else None
        for pid in ids:
            if pid not in self.store:
                rep.unsupported_ids.append(pid)
            elif allowed is not None and pid not in allowed:
                rep.outside_evidence_ids.append(pid)
                rep.verified_ids.append(pid)
            else:
                rep.verified_ids.append(pid)
        # 引文核验：存在性 + 就近归属
        corpus = {pid: self.store[pid].text for pid in rep.verified_ids}
        if corpus:
            id_positions = [(m.start(), m.group(0)) for m in RE_POEM_ID.finditer(answer)
                            if m.group(0) in corpus]
            for qm in RE_QUOTE.finditer(answer):
                q = qm.group(1)
                if not re.search(r"[㐀-鿿]{4,}", q):
                    continue  # 非诗句引文（口语引号）跳过
                holders = [pid for pid, text in corpus.items()
                           if contains_verbatim(text, q) or similarity(t2s(q), t2s(text)) >= 0.6]
                if not holders:
                    best = max((similarity(t2s(q), t2s(t)) for t in corpus.values()), default=0.0)
                    if best < 0.45:
                        rep.quote_mismatches.append({"quote": q, "matched": False})
                    continue
                if id_positions:
                    nearest = min(id_positions, key=lambda p: abs(p[0] - qm.start()))[1]
                    if nearest not in holders:
                        rep.attribution_warnings.append({
                            "quote": q[:30], "bound_to": nearest, "actually_in": holders[:3],
                            "note": "引文与就近 poem_id 归属不符"})
        elif RE_QUOTE.search(answer or ""):
            for qm in RE_QUOTE.finditer(answer):
                q = qm.group(1)
                if re.search(r"[㐀-鿿]{4,}", q):
                    rep.quote_mismatches.append({"quote": q, "matched": False,
                                                 "note": "无已核验 poem_id 支撑该引文"})
        return rep

    def annotate(self, answer: str, rep: CitationReport) -> str:
        lines = ["", "【证据核验】"]
        if rep.verified_ids and not rep.outside_evidence_ids:
            lines.append(f"✓ 已核验引用 {len(rep.verified_ids)} 处：{'、'.join(rep.verified_ids[:8])}")
        if rep.unsupported_ids:
            lines.append(f"✗ 语料中不存在的编号（疑似杜撰）：{'、'.join(rep.unsupported_ids)}")
        if rep.outside_evidence_ids:
            lines.append(f"⚠ 编号真实但非本轮取证所得（存在≠取证）：{'、'.join(rep.outside_evidence_ids)}")
        for m in rep.quote_mismatches[:3]:
            lines.append(f"✗ 引文未回源：「{m['quote'][:24]}…」")
        for w in rep.attribution_warnings[:3]:
            lines.append(f"⚠ 归属存疑：「{w['quote']}」标注为 {w['bound_to']}，实见于 {'、'.join(w['actually_in'])}")
        if not rep.has_any_citation:
            lines.append("⚠ 本回答未包含任何 poem_id 引用")
        return (answer or "") + "\n".join(lines)
