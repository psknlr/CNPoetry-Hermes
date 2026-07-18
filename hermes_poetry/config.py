"""全局配置：路径解析、语料登记、发布阈值。

环境变量：
  HERMES_POETRY_ROOT   仓库根目录覆盖（默认 config.py 上两级）
  HERMES_POETRY_DATA   数据根目录覆盖（默认 <root>/data；pip 安装部署时使用）
  HERMES_LLM_MODEL 等  见 llm/config.py
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("HERMES_POETRY_ROOT", Path(__file__).resolve().parent.parent))
DATA_DIR = Path(os.environ.get("HERMES_POETRY_DATA", str(REPO_ROOT / "data")))

RAW_DIR = DATA_DIR / "raw"
CHINESE_POETRY_RAW = RAW_DIR / "chinese_poetry"
CHARMAP_FILE = RAW_DIR / "charmap" / "TSCharacters.txt"
HF_ANALYSIS_FILE = RAW_DIR / "hf_poetrymteb" / "analysis_sample.jsonl"

POETRY_DIR = DATA_DIR / "poetry"
MANIFEST_DIR = POETRY_DIR / "manifest"
POEM_DIR = POETRY_DIR / "poems"
RELATION_DIR = POETRY_DIR / "relations"
RULES_INITIAL_DIR = POETRY_DIR / "rules_initial"
RULES_IMAGERY_DIR = POETRY_DIR / "rules_imagery"
RULES_THEME_DIR = POETRY_DIR / "rules_theme"
RULES_CIPAI_DIR = POETRY_DIR / "rules_cipai"
RULES_AUTHOR_DIR = POETRY_DIR / "rules_author"
RULES_RHYME_DIR = POETRY_DIR / "rules_rhyme"
RULES_INTERTEXT_DIR = POETRY_DIR / "rules_intertext"
REJECTED_DIR = POETRY_DIR / "rejected"
AUDIT_DIR = POETRY_DIR / "audit"
NETWORK_DIR = POETRY_DIR / "network"
EVAL_DIR = POETRY_DIR / "eval"
MEMORY_DIR = POETRY_DIR / "memory"
INDEX_DIR = POETRY_DIR / "index"          # 运行期缓存（gitignore）
LLM_CACHE_DIR = POETRY_DIR / "llm_cache"  # 运行期缓存（gitignore）
SKILLS_DIR = DATA_DIR / "skills" / "cnpoetry"

ALL_OUTPUT_DIRS = [
    MANIFEST_DIR, POEM_DIR, RELATION_DIR, RULES_INITIAL_DIR, RULES_IMAGERY_DIR,
    RULES_THEME_DIR, RULES_CIPAI_DIR, RULES_AUTHOR_DIR, RULES_RHYME_DIR,
    RULES_INTERTEXT_DIR, REJECTED_DIR, AUDIT_DIR, NETWORK_DIR, EVAL_DIR,
    MEMORY_DIR, INDEX_DIR, SKILLS_DIR,
]


def ensure_dirs() -> None:
    for d in ALL_OUTPUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)


# ── 证据层级 ──────────────────────────────────────────────────────────
LAYER_LABEL = {
    "A": "A 原文直录（语料原文）",
    "B": "B 计量事实（确定性算法可复算）",
    "C": "C 旁证（集内注释/作者小传/白话导读）",
    "D": "D 外部分析（外部数据集 LLM 生成，非本系统结论）",
    "E": "E 模型解释（本系统模型推理，须过引用核验）",
}

# ── 发布闸门阈值（与伤寒-赫尔墨斯一致）─────────────────────────────────
RELEASE_GOLD = 0.90
RELEASE_SILVER = 0.78
RELEASE_BRONZE = 0.62

# ── ID 前缀 ──────────────────────────────────────────────────────────
POEM_ID_PREFIX = "CNP"

# 朝代排序（研究端时间轴）
DYNASTY_ORDER = ["先秦", "汉", "汉魏", "魏晋", "南北朝", "隋", "唐", "五代", "宋", "辽金", "元", "明", "清", "近现代", "未知"]
