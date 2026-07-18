"""词谱权威层：龙榆生《唐宋词格律》结构化装载。

数据源：longyusheng.org 整理本 XML（153 调：平韵格/仄韵格/转换格/通叶格/
错叶格），含调名异名、调下说明与定格/变格符号谱。原书为词学通行权威；
本模块只做符号转写与结构化，不改动谱面内容。

符号转写（原文 → 通行记法）：
    －(平)→○   ＋(可平可仄)→⊙   │(仄)→●   ％(平韵)→△   ＊(仄韵)→▲
    保留：＃可选增韵 、豆 ！仄领格 ～平领格 ˇ衬字 ｛｝对偶 ［］叠韵 （）可省

用法：
    python3 -m hermes_poetry.corpus.cipu <唐宋词格律.xml>   # 重新生成 JSONL
    from hermes_poetry.corpus.cipu import load_cipu, cipu_index
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from .. import config

CIPU_DIR = config.RAW_DIR / "longyusheng"
CIPU_JSONL = CIPU_DIR / "cipu.jsonl"

SOURCE = "龙榆生《唐宋词格律》（longyusheng.org 整理本）"
LEGEND = ("○平 ●仄 ⊙可平可仄 △平韵 ▲仄韵 ＃可选增韵 、豆 "
          "！仄声领格字 ～平声领格字 ˇ衬字 ｛｝对偶句 ［］叠韵句 （）可省略")

_TRANS = str.maketrans({"－": "○", "＋": "⊙", "│": "●", "％": "△", "＊": "▲"})


def _plain(el: Optional[ET.Element]) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def convert_xml(xml_path: Path, out_path: Path = CIPU_JSONL) -> int:
    """XML → JSONL（每调一行）。返回条数。"""
    raw = xml_path.read_bytes()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8")
    root = ET.fromstring(text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for cat in root.findall("类别"):
            cat_name = cat.findtext("名称") or ""
            for pai in cat.findall("词牌"):
                names = [x.text.strip() for x in pai.findall("名称") if x.text and x.text.strip()]
                if not names:
                    continue
                forms = []
                for zw in pai.findall("正文"):
                    for g in zw.findall("格律"):
                        pat = (g.text or "").strip()
                        if pat:
                            forms.append({"label": g.get("说明") or "定格",
                                          "pattern": pat.translate(_TRANS)})
                rec = {"cipai": names[0], "aliases": names[1:], "category": cat_name,
                       "intro": _plain(pai.find("说明")),
                       "forms": forms, "source": SOURCE, "legend": LEGEND,
                       "source_level": "词谱权威（龙榆生）"}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    return n


def load_cipu() -> List[Dict]:
    if not CIPU_JSONL.exists():
        return []
    return [json.loads(ln) for ln in
            CIPU_JSONL.read_text(encoding="utf-8").splitlines() if ln.strip()]


def cipu_index(records: Optional[List[Dict]] = None) -> Dict[str, Dict]:
    """正名+异名（简体折叠）→ 记录 的查询索引。"""
    from ..textutil import t2s
    idx: Dict[str, Dict] = {}
    for r in records if records is not None else load_cipu():
        for name in [r["cipai"]] + list(r.get("aliases") or []):
            idx.setdefault(t2s(name), r)
    return idx


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("用法：python3 -m hermes_poetry.corpus.cipu <唐宋词格律.xml>")
    n = convert_xml(Path(sys.argv[1]))
    print(f"已生成 {CIPU_JSONL}（{n} 调）")
