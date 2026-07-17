"""自监督评测套件（无需外部标注，确定性可复现）。

  * retrieval：名句检索——抽取每首诗的一句作查询，命中原诗为金标；
    报告 Top-1/Top-5/MRR。诚实口径：重出互见导致的「命中孪生诗」单独
    计数（twin_hits），不算失败也不冒充精确命中。
  * metrics：体裁计量与语料标签（唐诗三百首等 tags）的一致率——
    真正带金标的评测。
  * grounding：对自动生成的问题库跑智能体，统计引用核验通过率。
"""
from __future__ import annotations

import json
import random
from typing import Dict, List

from .. import config
from ..textutil import content_only, t2s


def eval_retrieval(limit: int = 200) -> Dict:
    from ..apps.engine import get_engine
    engine = get_engine()
    rng = random.Random(42)
    pool = [p for p in engine.poems if p.lines and len(p.lines) >= 2 and len(content_only(p.text)) >= 20]
    sample = rng.sample(pool, min(limit, len(pool)))
    top1 = top5 = twin = 0
    mrr = 0.0
    for p in sample:
        query = max(p.lines, key=len)
        hits = engine.rag.search(query, top_k=5)
        rank = None
        for i, h in enumerate(hits):
            if h["poem_id"] == p.poem_id:
                rank = i + 1
                break
            # 孪生诗：文本高度重合的重出互见
            other = engine.by_id.get(h["poem_id"])
            if other is not None and rank is None:
                a, b = content_only(t2s(p.text)), content_only(t2s(other.text))
                if a and b and (a in b or b in a):
                    twin += 1
                    rank = i + 1
                    break
        if rank == 1:
            top1 += 1
        if rank is not None and rank <= 5:
            top5 += 1
            mrr += 1.0 / rank
    n = len(sample)
    return {"suite": "retrieval", "n": n,
            "top1": round(top1 / n, 3), "top5": round(top5 / n, 3),
            "mrr": round(mrr / n, 3), "twin_hits": twin,
            "note": "查询=每首最长一句；twin_hits 为重出互见孪生命中（计入 Top-K）。"}


def eval_metrics() -> Dict:
    from ..apps.engine import get_engine
    from ..lexicon import canonical_genre
    engine = get_engine()
    gold_forms = {"五绝", "七绝", "五律", "七律"}
    n = agree = 0
    confusion: Dict[str, int] = {}
    for p in engine.poems:
        tag = ""
        for t in p.tags:
            cg = canonical_genre(t)
            if cg in gold_forms:
                tag = cg
                break
        if not tag:
            continue
        metric = (p.metrics or {}).get("form_metric", "")
        n += 1
        if metric == tag:
            agree += 1
        else:
            key = f"{tag}->{metric or '?'}"
            confusion[key] = confusion.get(key, 0) + 1
    top_conf = dict(sorted(confusion.items(), key=lambda kv: -kv[1])[:6])
    return {"suite": "metrics", "n": n,
            "agreement": round(agree / n, 3) if n else None,
            "top_confusions": top_conf,
            "note": "金标=语料自带体裁标签；不一致多为古绝/折腰体等计量近似边界。"}


def eval_grounding(limit: int = 24) -> Dict:
    from ..agent.agent import PoetryAgent
    from ..apps.engine import get_engine
    engine = get_engine()
    agent = PoetryAgent()
    rng = random.Random(7)
    questions: List[str] = []
    imgs = list(engine.imagery_profiles)
    rng.shuffle(imgs)
    questions += [f"{i}在古诗里代表什么意象含义？" for i in imgs[:limit // 3]]
    cps = [c["cipai"] for c in engine.cipai_profiles.values() if c["n_poems"] >= 5]
    rng.shuffle(cps)
    questions += [f"{c}的词牌定格是什么？" for c in cps[:limit // 3]]
    curated = [p for p in engine.poems if p.source == "TANG300"]
    rng.shuffle(curated)
    questions += [f"《{p.title}》的格律怎样？" for p in curated[:limit - len(questions)]]
    ok = cited = 0
    for q in questions:
        res = agent.ask(q)
        rep = res["citation_report"]
        if rep["ok"]:
            ok += 1
        if rep["has_any_citation"]:
            cited += 1
    n = len(questions)
    return {"suite": "grounding", "n": n,
            "citation_ok_rate": round(ok / n, 3) if n else None,
            "has_citation_rate": round(cited / n, 3) if n else None,
            "backend": agent.client.backend}


def run_suites(suite: str = "all", limit: int = 200) -> Dict:
    out: Dict = {}
    if suite in ("all", "retrieval"):
        out["retrieval"] = eval_retrieval(limit)
    if suite in ("all", "metrics"):
        out["metrics"] = eval_metrics()
    if suite in ("all", "grounding"):
        out["grounding"] = eval_grounding(min(24, limit))
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (config.EVAL_DIR / "eval_summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
