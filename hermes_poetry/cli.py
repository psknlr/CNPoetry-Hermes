"""命令行入口：hermes-cnpoetry / python3 -m hermes_poetry。"""
from __future__ import annotations

import argparse
import json
import sys

from . import config
from .safety import ROLES


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def _need_pipeline() -> None:
    if not (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists():
        print("规则库未生成：请先运行 `python3 -m hermes_poetry pipeline`", file=sys.stderr)
        raise SystemExit(2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hermes-cnpoetry",
                                 description="诗海赫尔墨斯：古典诗词规则挖掘与证据优先智能体")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pipeline", help="一键全量流水线（语料→规则→审核→归纳→Skill）") \
       .add_argument("--quiet", action="store_true")
    sub.add_parser("stats", help="规则库统计")
    sub.add_parser("readyz", help="就绪探针（exit 2 = 未就绪）")
    sub.add_parser("llm-status", help="LLM 后端状态")
    sub.add_parser("skills", help="列出已编译 Skill")

    p = sub.add_parser("search", help="原文检索（BM25+过滤+意象扩展）")
    p.add_argument("query")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--dynasty", default="")
    p.add_argument("--author", default="")
    p.add_argument("--genre", default="")
    p.add_argument("--cipai", default="")
    p.add_argument("--expand", action="store_true")

    p = sub.add_parser("poem", help="作品全息（A原文/B计量/C旁证/D外部分析/互文）")
    p.add_argument("ref", help="poem_id 或《题名》")

    p = sub.add_parser("match", help="情境荐诗")
    p.add_argument("--mood", default="", help="心境/场景描述")
    p.add_argument("--imagery", default="", help="意象（逗号分隔）")
    p.add_argument("--themes", default="", help="题材（逗号分隔）")
    p.add_argument("--top-k", type=int, default=6)

    p = sub.add_parser("differential", help="多首作品对比鉴赏")
    p.add_argument("refs", nargs="+", help="poem_id 或《题名》")

    p = sub.add_parser("teach", help="教学（题材/体裁/意象/诗人）")
    p.add_argument("topic")

    p = sub.add_parser("imagery", help="意象档案")
    p.add_argument("name")

    p = sub.add_parser("metrics", help="格律计量（B层）")
    p.add_argument("ref")

    p = sub.add_parser("cipai", help="词牌定格（语料归纳）")
    p.add_argument("name")

    p = sub.add_parser("author", help="诗人档案")
    p.add_argument("name")

    p = sub.add_parser("rhyme", help="韵伴查询（语料归纳）")
    p.add_argument("--char", default="")
    p.add_argument("--poem", default="")

    p = sub.add_parser("intertext", help="互文检测（袭用/化用/重出互见）")
    p.add_argument("--poem", default="")
    p.add_argument("--text", default="")

    p = sub.add_parser("scene", help="诗境：逐句多层注解+情感曲线+对仗")
    p.add_argument("ref")

    p = sub.add_parser("allusion", help="典故检测（种子图谱）")
    p.add_argument("--text", default="")
    p.add_argument("--poem", default="")

    p = sub.add_parser("compose", help="创作实验室（今人拟作辅助）")
    p.add_argument("--genre", default="七绝")
    p.add_argument("--rhyme-char", default="")
    p.add_argument("--mood", default="")
    p.add_argument("--avoid", default="", help="排除意象（逗号分隔）")

    p = sub.add_parser("bench", help="CNPoetryBench 对抗题库")
    p.add_argument("--n", type=int, default=8)

    p = sub.add_parser("gloss", help="字义训诂（C层：说文解字/尔雅）")
    p.add_argument("--chars", default="", help="1-8 个汉字")
    p.add_argument("--poem", default="", help="按作品取高频字训诂")

    p = sub.add_parser("research", help="研究端（意象网络/朝代分布/情感矩阵）")
    p.add_argument("topic", nargs="?", default="")

    p = sub.add_parser("ask", help="单智能体问答（证据优先）")
    p.add_argument("question")
    p.add_argument("--role", choices=list(ROLES), default="")
    p.add_argument("--answer-only", action="store_true")

    p = sub.add_parser("council", help="多智能体合议")
    p.add_argument("question")
    p.add_argument("--role", choices=list(ROLES), default="")
    p.add_argument("--answer-only", action="store_true")

    p = sub.add_parser("evaluate", help="评测（retrieval/grounding/metrics/all）")
    p.add_argument("--suite", default="all")
    p.add_argument("--limit", type=int, default=200)

    p = sub.add_parser("serve", help="Web 控制台")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)

    p = sub.add_parser("fetch", help="下载/扩充语料（chinese-poetry 全量等）")
    p.add_argument("--list", action="store_true", help="仅列出可扩充来源")

    args = ap.parse_args(argv)

    if args.cmd == "pipeline":
        from .orchestrator import run_pipeline
        stats = run_pipeline(verbose=not args.quiet)
        _print(stats)
        return 0

    if args.cmd == "readyz":
        from .health import readyz
        r = readyz()
        _print(r)
        return 0 if r["ready"] else 2

    if args.cmd == "llm-status":
        from .llm import get_client
        c = get_client()
        _print({"backend": c.backend, "model": c.settings.model,
                "available": c.available,
                "hint": "设 ANTHROPIC_API_KEY / OPENAI_API_KEY 等并安装 litellm 可接入真实大模型；"
                        "无 key 时使用确定性 local 后端，全功能离线可跑。"})
        return 0

    if args.cmd == "fetch":
        from .corpus.fetch import fetch_main
        return fetch_main(list_only=getattr(args, "list", False))

    _need_pipeline()

    if args.cmd == "stats":
        from .apps.engine import get_engine
        _print(get_engine().stats())
        return 0

    if args.cmd == "skills":
        manifest = config.SKILLS_DIR / "skills_manifest.json"
        if manifest.exists():
            _print(json.loads(manifest.read_text(encoding="utf-8")))
        else:
            print("Skill 未编译，请运行 pipeline", file=sys.stderr)
            return 2
        return 0

    from .apps.engine import get_engine
    engine = get_engine()

    if args.cmd == "search":
        _print(engine.rag.search(args.query, top_k=args.top_k, dynasty=args.dynasty,
                                 author=args.author, genre=args.genre, cipai=args.cipai,
                                 expand=args.expand))
    elif args.cmd == "poem":
        _print(engine.explain_poem(args.ref))
    elif args.cmd == "match":
        imagery = [x for x in args.imagery.replace("，", ",").split(",") if x]
        themes = [x for x in args.themes.replace("，", ",").split(",") if x]
        _print(engine.match(args.mood, imagery, themes, args.top_k))
    elif args.cmd == "differential":
        _print(engine.differential(args.refs))
    elif args.cmd == "teach":
        _print(engine.teach(args.topic))
    elif args.cmd == "imagery":
        prof = engine.imagery_profiles.get(args.name)
        _print(prof or {"error": f"无意象档案「{args.name}」",
                        "available": list(engine.imagery_profiles)})
    elif args.cmd == "metrics":
        p = engine.resolve_poem(args.ref)
        from .extract.metrics import describe
        _print(describe(p) if p else {"error": f"无法解析「{args.ref}」"})
    elif args.cmd == "cipai":
        from .textutil import t2s
        _print(engine.cipai_profiles.get(t2s(args.name)) or {"error": f"无词牌档案「{args.name}」"})
    elif args.cmd == "author":
        from .textutil import t2s
        _print(engine.author_profiles.get(t2s(args.name)) or {"error": f"无诗人档案「{args.name}」"})
    elif args.cmd == "rhyme":
        _print(engine.rhyme_query(args.char, args.poem))
    elif args.cmd == "intertext":
        _print(engine.intertext_query(args.poem, args.text))
    elif args.cmd == "scene":
        _print(engine.scene(args.ref))
    elif args.cmd == "allusion":
        from .induce.allusions import detect_allusions
        if args.poem:
            p2 = engine.resolve_poem(args.poem)
            _print({"allusions": detect_allusions(p2.text)} if p2 else {"error": "未解析"})
        else:
            _print({"allusions": detect_allusions(args.text)})
    elif args.cmd == "compose":
        from .apps.compose import compose_helper
        avoid = [x for x in args.avoid.replace("，", ",").split(",") if x]
        _print(compose_helper(args.genre, args.rhyme_char, args.mood, avoid, engine))
    elif args.cmd == "bench":
        from .eval.bench import run_bench
        _print(run_bench(args.n))
    elif args.cmd == "gloss":
        _print(engine.gloss_query(args.chars, args.poem))
    elif args.cmd == "research":
        _print(engine.research(args.topic))
    elif args.cmd == "ask":
        from .agent.agent import PoetryAgent
        res = PoetryAgent().ask(args.question, role=args.role)
        print(res["answer"]) if args.answer_only else _print(res)
    elif args.cmd == "council":
        from .agent.council import Council
        res = Council().deliberate(args.question, role=args.role)
        print(res["answer"]) if args.answer_only else _print(res)
    elif args.cmd == "evaluate":
        from .eval.suites import run_suites
        _print(run_suites(args.suite, limit=args.limit))
    elif args.cmd == "serve":
        from .server.http_server import serve
        serve(host=args.host, port=args.port)
    return 0
