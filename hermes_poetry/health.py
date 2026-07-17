"""就绪探针：livez / readyz / assert_ready（假健康防护）。

pip 安装的 wheel 只含代码不含语料，进程可以启动但规则库为空——
危险的「假健康」。因此健康检查分离：livez 只报进程存活；readyz 逐项
检查数据资产；assert_ready 在 ToolRegistry 构建前响亮拦截。
"""
from __future__ import annotations

import json
import os
from typing import Dict

from . import config


class MissingAssetsError(RuntimeError):
    pass


def livez() -> Dict:
    return {"ok": True, "pid": os.getpid()}


def _check_jsonl(path, min_rows: int = 1):
    if not path.exists():
        return False, f"missing:{path.name}"
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
            if n >= min_rows:
                break
    return n >= min_rows, f"rows>={min_rows}:{n >= min_rows}"


def readyz() -> Dict:
    checks = []

    manifest_path = config.MANIFEST_DIR / "corpus_manifest.json"
    ok = manifest_path.exists()
    detail = ""
    expected = 0
    if ok:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected = int(manifest.get("poem_count", 0))
            ok = expected > 0
            detail = f"poem_count={expected}"
        except (OSError, json.JSONDecodeError):
            ok, detail = False, "manifest_unreadable"
    checks.append({"check": "manifest", "ok": ok, "detail": detail})

    poems_path = config.POEM_DIR / "poems.jsonl"
    if poems_path.exists() and expected:
        with poems_path.open(encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        checks.append({"check": "poems", "ok": n == expected,
                       "detail": f"rows={n} expected={expected}"})
    else:
        checks.append({"check": "poems", "ok": False, "detail": "missing_or_no_manifest"})

    for name, path in [
        ("initial_rules", config.RULES_INITIAL_DIR / "initial_rules.jsonl"),
        ("imagery_profiles", config.RULES_IMAGERY_DIR / "imagery_profiles.jsonl"),
    ]:
        ok, detail = _check_jsonl(path)
        checks.append({"check": name, "ok": ok, "detail": detail})

    skills_manifest = config.SKILLS_DIR / "skills_manifest.json"
    checks.append({"check": "skills", "ok": skills_manifest.exists(),
                   "detail": skills_manifest.name})

    ready = all(c["ok"] for c in checks)
    return {
        "ready": ready,
        "checks": checks,
        "data_dir": str(config.DATA_DIR),
        "hint": "" if ready else
                "git clone 本仓库后运行 `python3 -m hermes_poetry pipeline`，"
                "或设 HERMES_POETRY_DATA 指向已生成的数据目录。",
    }


def assert_ready(context: str = "") -> None:
    if os.environ.get("HERMES_ALLOW_DEGRADED") == "1":
        return
    missing = [str(p) for p in [
        config.POEM_DIR / "poems.jsonl",
        config.RULES_INITIAL_DIR / "initial_rules.jsonl",
    ] if not p.exists()]
    if missing:
        raise MissingAssetsError(
            f"{context or '系统'}数据资产缺失：{missing}。"
            f"请运行 `python3 -m hermes_poetry pipeline` 或设 HERMES_POETRY_DATA"
            f"（当前 DATA_DIR={config.DATA_DIR}；HERMES_ALLOW_DEGRADED=1 可显式跳过）。")
