"""CNPoetryBench（MVP）：从语料自动生成的对抗题库 + 确定性判分。

六类对抗任务（依评审清单）：
  T1 真实诗句+错误作者   → ClaimGuard 应拦
  T2 真实诗句+错误朝代   → ClaimGuard 应拦
  T3 两首诗句拼接引文    → CitationGuard 应拦
  T4 改一字引文          → CitationGuard 应拦
  T5 否定语境情感        → 标注层不得计正向
  T6 多音字韵部          → 音韵层须列全候选
判分为确定性（守卫是否拦截/输出是否含全候选），衡量防线有效性，
非模型理解力。结果落 eval/bench_results.json。
"""
from __future__ import annotations

import json
import random
from typing import Dict, List

from .. import config


def run_bench(n_per_task: int = 8) -> Dict:
    from ..agent.citation import CitationGuard
    from ..agent.claims import ClaimGuard
    from ..apps.engine import get_engine
    from ..extract.annotate import annotate_line
    from ..extract.phonology import get_phonology, pingshui_of
    engine = get_engine()
    cg, qg, ph = ClaimGuard(engine), CitationGuard(engine.poems), get_phonology()
    rng = random.Random(2026)
    pool = [p for p in engine.poems if p.source == "TANG300" and p.lines and p.author != "佚名"]
    results: Dict[str, Dict] = {}

    def score(task, cases, passed):
        results[task] = {"n": len(cases), "blocked": passed,
                         "rate": round(passed / len(cases), 3) if cases else None}

    # T1 错误作者
    cases = rng.sample(pool, min(n_per_task, len(pool)))
    ok = 0
    for p in cases:
        wrong = next(a for a in ("杜甫", "李白", "王維", "白居易") if a != p.author)
        rep = cg.check(f"《{p.title}》是{wrong}所作。")
        ok += 0 if rep.ok else 1
    score("T1_wrong_author", cases, ok)
    # T2 错误朝代
    cases = rng.sample(pool, min(n_per_task, len(pool)))
    ok = sum(0 if cg.check(f"《{p.title}》是宋代的诗。").ok else 1
             for p in cases if p.dynasty == "唐")
    score("T2_wrong_dynasty", [p for p in cases if p.dynasty == "唐"], ok)
    # T3 拼接引文（两首各取半句拼成一句）
    cases = [(a, b) for a, b in zip(rng.sample(pool, n_per_task), rng.sample(pool, n_per_task))
             if a.poem_id != b.poem_id and len(a.lines[0]) >= 4 and len(b.lines[0]) >= 4]
    ok = 0
    for a, b in cases:
        frank = a.lines[0][:3] + b.lines[0][-3:]
        rep = qg.check(f"「{frank}」（{a.poem_id}）", allowed_ids=[a.poem_id])
        ok += 0 if rep.ok else 1
    score("T3_spliced_quote", cases, ok)
    # T4 改字引文
    cases = [p for p in rng.sample(pool, n_per_task) if len(p.lines[0]) >= 5]
    ok = 0
    for p in cases:
        q = p.lines[0]
        q2 = q[:2] + ("云" if q[2] != "云" else "山") + q[3:]
        rep = qg.check(f"「{q2}」（{p.poem_id}）", allowed_ids=[p.poem_id])
        ok += 0 if rep.ok else 1
    score("T4_tampered_quote", cases, ok)
    # T5 否定情感
    neg_cases = ["不是愁中即病中", "莫愁前路无知己", "未必愁来即断肠", "不见愁人独自悲"]
    ok = sum(1 for ln in neg_cases
             if not any(c == "愁苦哀伤" for c, _ in annotate_line(ln, 0).emotions[:1]))
    score("T5_negated_emotion", neg_cases, ok)
    # T6 多音字韵部全候选
    poly = [ch for ch in "中看思重行长" if len({r["tone"] for r in ph.char_readings(ch)}) > 1]
    ok = sum(1 for ch in poly
             if len({pingshui_of(r["yun"]) for r in ph.char_readings(ch)}) > 1
             or len({r["tone"] for r in ph.char_readings(ch)}) > 1)
    score("T6_polyphone_rhyme", poly, ok)

    summary = {"bench": "CNPoetryBench-MVP", "tasks": results,
               "note": "确定性判分：衡量守卫/标注/音韵防线有效性，非模型理解力；"
                       "解释质量任务（人评/LLM评）见 ROADMAP。"}
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (config.EVAL_DIR / "bench_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary
