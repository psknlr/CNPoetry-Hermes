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
    flags = []
    img = cand.get("image", "")
    if img not in IMAGERY:
        flags.append(f"unknown_image:{img}")
    elif img not in poem.imagery:
        flags.append(f"image_not_in_poem:{img}")
    spans = cand.get("support_spans") or []
    if not spans:
        flags.append("no_support_spans")
    for s in spans:
        if not contains_verbatim(poem.text, s):
            flags.append(f"span_not_verbatim:{s[:12]}")
    claim = cand.get("interpretive_claim", "")
    if claim and not spans:
        flags.append("claim_without_spans")
    return flags


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
        (rejected if flags else accepted).append(
            {**c, "verify_flags": flags} if flags else c)
    return {"poem_id": poem.poem_id, "layer": "E" if not degraded else "A",
            "backend": client.backend, "degraded": degraded,
            "accepted": accepted[:20], "rejected_count": len(rejected),
            "note": "候选须逐字回源（support_spans）方被接受；"
                    "local 后端为字面层退化输出，不代表理解能力。"}
