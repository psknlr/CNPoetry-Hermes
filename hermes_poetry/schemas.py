"""数据模式：作品、规则、审核、归纳产物的 dataclass 定义。

序列化统一走 JSONL（write_jsonl/read_jsonl）；所有记录可 to_dict/from_dict
往返，产物确定性生成（不带时间戳），同语料重跑逐字节可复现。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Iterable, List

# ── 枚举集合 ─────────────────────────────────────────────────────────

RULE_TYPES = frozenset({
    "imagery_emotion_rule",     # 意象-情感关联（逐首实例，A层证据）
    "theme_rule",               # 题材判定（A层证据）
    "form_metric_rule",         # 体裁句式计量（B层，确定性可复算）
    "rhyme_rule",               # 韵脚计量（B层）
    "annotation_rule",          # 集内注释绑定（C层）
    "external_analysis_rule",   # 外部LLM分析绑定（D层）
})

INDUCED_TYPES = frozenset({
    "imagery_profile_rule",     # 意象档案（跨诗归纳）
    "cipai_profile_rule",       # 词牌定格归纳
    "author_profile_rule",      # 诗人档案归纳
    "theme_profile_rule",       # 题材档案归纳
    "rhyme_partner_rule",       # 韵伴聚类归纳（语料归纳，非平水韵权威表）
    "intertext_rule",           # 互文/袭用/化用检测
})

EVIDENCE_TYPES = frozenset({
    "original_text",      # 诗文本身
    "annotation_text",    # 集内注释（notes）
    "appreciation_text",  # 白话导读（水墨唐诗 prologue）
    "external_analysis",  # 外部数据集 LLM 分析
})
# 注：作者小传（C层）经由 AuthorProfileRule.bio 呈现，不作为初始规则证据类型。

INTERPRETATION_LEVELS = frozenset({
    "literal",          # 原文直述
    "metric",           # 确定性计量
    "normalized",       # 术语归一
    "corpus_induction", # 语料归纳（跨诗统计）
    "external_llm",     # 外部LLM生成
    "model_inference",  # 本系统模型推理
})

RELEASE_LEVELS = frozenset({"gold", "silver", "bronze", "rejected"})

RELATION_TYPES = frozenset({
    "same_author", "same_cipai", "same_theme", "intertext", "shared_imagery",
})

RE_POEM_ID = re.compile(r"^CNP_[A-Z0-9]+_\d{5}$")
RE_INITIAL_RULE_ID = re.compile(r"^IR_CNP_[A-Z0-9]+_\d{5}_\d{3}$")


# ── 基类 ─────────────────────────────────────────────────────────────


class JsonRecord:
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)  # type: ignore[arg-type]

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        kwargs = {k: v for k, v in (data or {}).items() if k in names}
        obj = cls(**kwargs)  # type: ignore[call-arg]
        # 嵌套 dataclass 再水化
        if isinstance(getattr(obj, "autonomous_review", None), dict):
            obj.autonomous_review = AutonomousReview.from_dict(obj.autonomous_review)  # type: ignore[attr-defined]
        return obj


def write_jsonl(path: Path, records: Iterable) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            if isinstance(rec, JsonRecord):
                fh.write(rec.to_json() + "\n")
            else:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ── 作品（证据原子单位）───────────────────────────────────────────────


@dataclass
class Poem(JsonRecord):
    poem_id: str = ""
    source: str = ""              # 语料集 key（TANG300/QTS/...）
    book: str = ""                # 集名（唐诗三百首/全唐诗（抽样）/...）
    dynasty: str = ""
    author: str = ""
    title: str = ""
    cipai: str = ""               # 词牌（词/部分曲）
    section: str = ""             # 诗经国风/楚辞篇章等
    genre: str = ""               # 体裁标签（计量判定或语料标签）
    genre_source: str = ""        # tag | metric
    lines: List[str] = field(default_factory=list)   # 句（原文）
    text: str = ""                # 原文全文（换行连接段落）
    tags: List[str] = field(default_factory=list)    # 语料自带标签
    notes: List[str] = field(default_factory=list)   # C层：集内注释
    appreciation: str = ""        # C层：白话导读
    also_in: List[str] = field(default_factory=list) # 重出互见的其他集子
    layer: str = "A"
    sha256: str = ""
    # 抽取标注（流水线写回）
    imagery: List[str] = field(default_factory=list)
    emotions: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)  # B层计量


# ── 审核与初始规则 ────────────────────────────────────────────────────


@dataclass
class AutonomousReview(JsonRecord):
    evidence_verified: bool = False
    schema_valid: bool = False
    semantic_result: str = "pending"   # pass|warn|fail
    critic_result: str = "pending"     # pass|warn|fail
    critic_flags: List[str] = field(default_factory=list)
    repairs: List[str] = field(default_factory=list)
    consensus_score: float = 0.0
    release_level: str = "rejected"


@dataclass
class InitialRule(JsonRecord):
    """单首作品内的最小规则：证据跨度必须逐字存在于该作品对应层文本。"""
    initial_rule_id: str = ""
    poem_id: str = ""
    rule_type: str = "imagery_emotion_rule"
    if_conditions: Dict[str, Any] = field(default_factory=dict)
    then_conclusions: Dict[str, Any] = field(default_factory=dict)
    evidence_span: str = ""
    evidence_type: str = "original_text"
    strength: str = ""             # 显证（同句）| 邻证（邻句）| 弱证（同篇）
    interpretation: str = ""
    interpretation_level: str = "normalized"
    model_confidence: float = 0.0
    autonomous_review: AutonomousReview = field(default_factory=AutonomousReview)


@dataclass
class AuditRecord(JsonRecord):
    audit_id: str = ""
    target_id: str = ""
    target_kind: str = "initial_rule"
    stage: str = ""    # schema|evidence|semantic|critic|repair|consensus|release
    result: str = ""   # pass|warn|fail|repaired|gold|silver|bronze|rejected
    flags: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


# ── 归纳层规则（只引用下层 ID，附证据链，不改写下层）──────────────────


@dataclass
class ImageryProfileRule(JsonRecord):
    imagery_rule_id: str = ""
    imagery: str = ""
    surface_forms: List[str] = field(default_factory=list)
    emotion_associations: List[Dict[str, Any]] = field(default_factory=list)
    # [{emotion, support, strength_breakdown, example: {poem_id, quote}}]
    theme_associations: List[Dict[str, Any]] = field(default_factory=list)
    co_imagery: List[Dict[str, Any]] = field(default_factory=list)
    n_poems: int = 0
    dynasty_distribution: Dict[str, int] = field(default_factory=dict)
    supporting_initial_rules: List[str] = field(default_factory=list)
    evidence_chain: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)  # 相反情感并存，只呈现不裁决
    source_level: str = "corpus_induction"
    consensus_score: float = 0.0
    release_level: str = "silver"


@dataclass
class CipaiProfileRule(JsonRecord):
    cipai_rule_id: str = ""
    cipai: str = ""
    n_poems: int = 0
    line_count_mode: int = 0
    char_pattern: str = ""        # 众数句式（如 7-5-7-5）
    pattern_consistency: float = 0.0
    example_poems: List[Dict[str, str]] = field(default_factory=list)
    supporting_poems: List[str] = field(default_factory=list)
    source_level: str = "corpus_induction"
    release_level: str = "silver"
    note: str = "定格由语料归纳，非词谱权威表；一调多体时以众数为准。"


@dataclass
class AuthorProfileRule(JsonRecord):
    author_rule_id: str = ""
    author: str = ""
    dynasty: str = ""
    n_poems: int = 0
    top_imagery: List[Dict[str, Any]] = field(default_factory=list)
    top_themes: List[Dict[str, Any]] = field(default_factory=list)
    form_distribution: Dict[str, int] = field(default_factory=dict)
    bio: str = ""                 # C层：作者小传（原文）
    bio_source: str = ""
    representative_poems: List[Dict[str, str]] = field(default_factory=list)
    supporting_poems: List[str] = field(default_factory=list)
    source_level: str = "corpus_induction"
    release_level: str = "silver"


@dataclass
class ThemeProfileRule(JsonRecord):
    theme_rule_id: str = ""
    theme: str = ""
    definition: str = ""
    marker_terms: List[str] = field(default_factory=list)
    n_poems: int = 0
    dynasty_distribution: Dict[str, int] = field(default_factory=dict)
    top_imagery: List[Dict[str, Any]] = field(default_factory=list)
    example_evidence: List[Dict[str, str]] = field(default_factory=list)
    supporting_poems: List[str] = field(default_factory=list)
    source_level: str = "corpus_induction"
    release_level: str = "silver"


@dataclass
class RhymePartnerRule(JsonRecord):
    rhyme_rule_id: str = ""
    label: str = ""               # 高频成员前三字，如「天·年·前」
    members: List[str] = field(default_factory=list)
    n_poems: int = 0
    edge_examples: List[Dict[str, Any]] = field(default_factory=list)
    supporting_poems: List[str] = field(default_factory=list)
    yun_profile: Dict[str, Any] = field(default_factory=dict)  # 广韵交叉验证（韵目分布/声调纯度）
    source_level: str = "corpus_induction"
    release_level: str = "silver"
    note: str = "韵伴聚类由近体诗偶数句尾字共现归纳，非平水韵权威表。"


@dataclass
class IntertextRule(JsonRecord):
    intertext_rule_id: str = ""
    source_poem_id: str = ""
    target_poem_id: str = ""
    shared_span: str = ""
    span_len: int = 0
    similarity: float = 0.0
    mode: str = ""                # 重出互见|袭用|化用|存疑
    # 年代方向性：后出可化用先出，反向不成立；同代/无考不定向
    relation_direction: str = "undetermined"   # later_borrows_earlier|undetermined
    earlier_poem_id: str = ""
    source_dynasty: str = ""
    target_dynasty: str = ""
    possible_common_source: bool = False       # 疑共源（如诗经套语），非直接承继
    source_level: str = "corpus_induction"
    release_level: str = "silver"


@dataclass
class PoemRelation(JsonRecord):
    relation_id: str = ""
    source_poem_id: str = ""
    target_poem_id: str = ""
    relation_type: str = "shared_imagery"
    description: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
