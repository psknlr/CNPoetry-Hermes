"""五层诗义标注器（第二阶段框架）：字面→句法→场景→诗学→解释。

设计（依外部评审建议）：大模型不直接输出结论，只输出结构化候选
（image/literal_role/discourse_role/affective_trigger/interpretive_claim/
support_spans/confidence/counter_readings）；随后确定性核验：
  * support_spans 必须逐字存在于诗文本；
  * image 必须在意象词库且见于诗中；
  * 未过核验的候选整条拒绝（rejected 计数如实报告）。
local 后端下产出「字面层退化候选」（仅由既有确定性标注组装，
interpretive_claim 留空并声明），保证离线可跑不冒充理解。
"""
from __future__ import annotations

import json
from typing import Dict, List

from ..lexicon import IMAGERY
from ..schemas import Poem
from ..textutil import contains_verbatim

CANDIDATE_SCHEMA = {
    "image": "意象规范名", "literal_role": "字面层角色（如 夜间景物）",
    "discourse_role": "语篇角色（如 凝视对象）",
    "affective_trigger": "情感触发（如 乡土联想）",
    "interpretive_claim": "解释性论断（须绑定 support_spans）",
    "support_spans": ["逐字证据句"], "confidence": 0.0,
    "counter_readings": ["替代解读"],
}

_PROMPT = """对下面这首诗做五层诗义标注。只输出 JSON 数组，每个元素严格遵循此 schema：
%s
规则：support_spans 必须逐字抄自原文；不确定处写入 counter_readings；
不得输出 schema 之外的结论。诗：
%s"""


def _verify(cand: Dict, poem: Poem) -> List[str]:
    """分层验证：SpanExistence（硬）→ SpanRelevance（硬）→ 意象身份（软）。

    词库外意象不再一票否决——原文逐字可证的新物象标记为 candidate
    （开放发现，供人工审核后入库）；只有原文无据的意象才拒绝。
    """
    flags = []
    img = cand.get("image", "")
    spans = cand.get("support_spans") or []
    # SpanExistence（硬闸门）
    if not spans:
        flags.append("no_support_spans")
    for s in spans:
        if not contains_verbatim(poem.text, s):
            flags.append(f"span_not_verbatim:{s[:12]}")
    # 意象身份：known / candidate / rejected
    if img in IMAGERY:
        cand["image_status"] = "known"
    elif img and any(contains_verbatim(s, img) for s in spans):
        cand["image_status"] = "candidate"
        cand["novelty_reason"] = "词库未注册，但物象逐字见于证据句（待人工审核入库）"
    else:
        cand["image_status"] = "rejected"
        flags.append(f"image_unsupported:{img}")
    # SpanRelevance（硬闸门）：证据句必须真的含该意象——
    # 「跨度真实」不等于「跨度支持论断」
    if img and spans and not flags:
        from ..textutil import t2s as _t2s
        surfaces = [img] + list(IMAGERY.get(img, []))
        if not any(_t2s(sf) in _t2s(s) for s in spans for sf in surfaces):
            flags.append(f"span_irrelevant_to_image:{img}")
    claim = cand.get("interpretive_claim", "")
    if claim and not spans:
        flags.append("claim_without_spans")
    return flags


def _calibrate(cand: Dict, poem: Poem) -> None:
    """最终置信度 = 模型自评 × 证据覆盖 × 意象确定性（封顶 0.95）。
    模型裸值不直接采信；校准依据落盘可审计。"""
    model_conf = min(max(float(cand.get("confidence") or 0.5), 0.0), 1.0)
    spans = cand.get("support_spans") or []
    coverage = min(1.0, len(spans) / 2.0) if spans else 0.0
    identity = 1.0 if cand.get("image_status") == "known" else 0.8
    has_counter = 1.0 if cand.get("counter_readings") else 0.9  # 无替代解读小幅折减
    final = round(min(0.95, model_conf * (0.5 + 0.5 * coverage) * identity * has_counter), 3)
    cand["confidence_raw"] = model_conf
    cand["confidence"] = final
    cand["calibration"] = {"coverage": coverage, "identity": identity,
                           "counter_reading_factor": has_counter,
                           "note": "模型自评×证据覆盖×意象确定性，封顶0.95；专家一致性/文献支持度校准见路线图"}


def annotate_semantic(poem: Poem, client=None) -> Dict:
    from ..llm import get_client
    client = client or get_client()
    candidates: List[Dict] = []
    degraded = not client.available
    if client.available:
        res = client.chat(
            [{"role": "user", "content": _PROMPT % (
                json.dumps(CANDIDATE_SCHEMA, ensure_ascii=False), poem.text)}],
            json_mode=True, task="semantic_layers")
        try:
            raw = json.loads(res.content)
            candidates = raw if isinstance(raw, list) else raw.get("candidates", [])
        except (json.JSONDecodeError, AttributeError):
            candidates, degraded = [], True
    if degraded:
        # 字面层退化候选：只组装既有确定性标注，不冒充解释
        from .annotate import annotate_poem
        hits = annotate_poem(poem)
        for h in hits:
            for canon, surface in h.imagery:
                candidates.append({
                    "image": canon, "literal_role": "句中物象（字面层）",
                    "discourse_role": "", "affective_trigger": "",
                    "interpretive_claim": "",
                    "support_spans": [h.line], "confidence": 0.5,
                    "counter_readings": ["local 后端仅提供字面层，语篇/诗学层需接入真实大模型"],
                })
    accepted, rejected = [], []
    for c in candidates:
        flags = _verify(c, poem)
        if flags:
            rejected.append({**c, "verify_flags": flags})
        else:
            _calibrate(c, poem)
            accepted.append(c)
    mode_notice = ("当前为离线基础模式：仅识别物象及其原文位置，"
                   "未执行句法、诗境与深层解释分析。" if degraded else
                   "解释层候选已过逐字回源与相关性核验；置信度为校准值非模型裸值。")
    return {"poem_id": poem.poem_id, "layer": "E" if not degraded else "A",
            "backend": client.backend, "degraded": degraded,
            "mode_notice": mode_notice,
            "accepted": accepted[:20], "rejected_count": len(rejected),
            "candidate_images": [c["image"] for c in accepted
                                 if c.get("image_status") == "candidate"],
            "note": "验证链：SpanExistence→SpanRelevance→意象身份（known/candidate）；"
                    "词库外新物象标 candidate 待人工审核入库。"}
