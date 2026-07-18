"""流水线编排：语料 → 作品 → 计量 → 规则 → 审核 → 归纳 → Skill → 研究资产。

八阶段，全部确定性；同语料重跑逐字节可复现。
"""
from __future__ import annotations

import time
from typing import Dict

from . import config
from .corpus import normalize, sources
from .extract.initial_rules import InitialRuleExtractor, link_external_analysis
from .extract.metrics import apply_metrics, form_distribution
from .induce.intertext import IntertextMiner, persist_intertext
from .induce.network import build_all as build_network_assets
from .induce.profiles import (AuthorInducer, CipaiInducer, ImageryInducer,
                              ThemeInducer, persist_profiles)
from .induce.rhyme import RhymeInducer, persist_rhyme
from .review.gates import PoemStore, ReviewPipeline
from .skills.compiler import SkillCompiler


def run_pipeline(verbose: bool = True) -> Dict:
    t0 = time.time()
    log = print if verbose else (lambda *a, **k: None)
    config.ensure_dirs()

    log("[1/8] 语料归一化…")
    poems, manifest = normalize.build_poems(verbose=verbose)
    if not poems:
        raise RuntimeError("语料为空：data/raw/chinese_poetry 缺失或损坏，已中止以免覆盖现有规则库。")

    log("[2/8] 格律计量层（B层）…")
    for p in poems:
        apply_metrics(p)

    log("[3/8] 初始规则抽取…")
    extractor = InitialRuleExtractor()
    rules = []
    for p in poems:
        rules.extend(extractor.extract(p))
    # D层外部分析绑定
    external = sources.load_external_analysis()
    ext_by_author: Dict[str, list] = {}
    from .textutil import t2s
    for e in external:
        ext_by_author.setdefault(t2s((e.get("author") or "").strip()), []).append(e)
    n_ext = 0
    for p in poems:
        for e in ext_by_author.get(t2s(p.author), []):
            r = link_external_analysis(p, e, seq=900 + n_ext % 90)
            if r:
                rules.append(r)
                n_ext += 1
                break
    log(f"  初始规则 {len(rules)} 条（含 D层绑定 {n_ext} 条）")

    log("[4/8] 自主审核（schema→证据回源→语义→批评→修复→共识→发布）…")
    store = PoemStore(poems, external)
    review = ReviewPipeline(store)
    accepted, rejected = review.run(rules)
    review.persist(accepted, rejected)
    # D层绑定表单独落盘（Engine 直读，免于全量扫描规则库）
    from .schemas import write_jsonl as _write_jsonl
    _write_jsonl(config.RULES_INITIAL_DIR / "external_bindings.jsonl", [
        {"poem_id": r.poem_id, "external_id": str(r.if_conditions.get("external_id", ""))}
        for r in accepted if r.rule_type == "external_analysis_rule"
    ])
    log(f"  通过 {len(accepted)} 条，拒绝 {len(rejected)} 条，审计 {len(review.audits)} 条")

    log("[5/8] 语料落盘（poems + manifest）…")
    manifest["form_distribution"] = form_distribution(poems)
    manifest["rules"] = {"accepted": len(accepted), "rejected": len(rejected)}
    normalize.persist(poems, manifest)

    log("[6/8] 跨诗归纳（意象/题材/词牌/诗人/韵伴/互文）…")
    imagery_rules = ImageryInducer(poems, accepted).run()
    theme_rules = ThemeInducer(poems, accepted).run()
    cipai_rules = CipaiInducer(poems).run()
    author_rules = AuthorInducer(poems, sources.load_author_bios()).run()
    persist_profiles(imagery_rules, theme_rules, cipai_rules, author_rules)
    rhyme_rules = RhymeInducer(poems).run()
    persist_rhyme(rhyme_rules)
    intertext_rules = IntertextMiner(poems).run()
    persist_intertext(intertext_rules)
    log(f"  意象 {len(imagery_rules)}｜题材 {len(theme_rules)}｜词牌 {len(cipai_rules)}"
        f"｜诗人 {len(author_rules)}｜韵组 {len(rhyme_rules)}｜互文 {len(intertext_rules)}")

    log("[7/8] 研究资产（意象网络/朝代分布/情感矩阵）…")
    net_stats = build_network_assets(poems)

    log("[8/8] Skill 编译…")
    stats = {
        "poems": len(poems),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "audits": len(review.audits),
        "imagery_profiles": len(imagery_rules),
        "theme_profiles": len(theme_rules),
        "cipai_profiles": len(cipai_rules),
        "author_profiles": len(author_rules),
        "rhyme_groups": len(rhyme_rules),
        "intertext_rules": len(intertext_rules),
        **net_stats,
    }
    skill_counts = SkillCompiler(imagery_rules, theme_rules, cipai_rules,
                                 author_rules, rhyme_rules, stats).build_all()
    stats["skills"] = sum(skill_counts.values())
    stats["elapsed_sec"] = round(time.time() - t0, 1)
    log(f"完成：{stats['poems']} 首 → {stats['accepted']} 规则 → {stats['skills']} Skill"
        f"（{stats['elapsed_sec']}s）")
    return stats
