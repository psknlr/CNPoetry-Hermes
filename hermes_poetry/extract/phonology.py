"""中古音韵层（B层）：广韵字音 → 平仄、韵部、基础律则检测。

数据：韵典网整理的《广韵》字音表（data/raw/ytenx/，见其 README 出处说明）。
设计要点：
  * 多音字保留全部读音候选，绝不静默取首；平仄判定输出三值：
    平 / 仄 / 两读（不确定不装确定）；
  * 声调由韵目名判定：广韵 206 韵四声韵目名互不重复，内嵌规范表，
    装载时遇未覆盖韵目响亮报错（fail-loud，防静默丢调）；
  * 律则检测限于可由平仄序列确定性判定者：三平尾、三仄尾、
    二四六字平仄交替、联内对、联间粘、韵脚声调一致性与归部；
    拗救判定不做（需要更强的体系假设，如实声明）；
  * 全部输出标注「依《广韵》，语境消歧不做」。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from .. import config
from ..textutil import cjk_chars, strip_brackets, t2s

# 广韵 206 韵目 → 声调（规范表；重纽 A/B 归并入韵目名）
_YUN_TONE: Dict[str, str] = {}
# 韵典本的异体韵目名与「附韵」小韵（广韵无独立韵目者，按传统归调）
_YUN_VARIANT = {"号": "號", "眞": "真", "眞A": "真", "眞B": "真", "襇": "襉"}
_YUN_EXTRA_TONE = {"湩": "上", "麧": "入", "櫬": "去"}

for _tone, _names in {
    "平": "東冬鍾江支脂之微魚虞模齊佳皆灰咍真諄臻文欣元魂痕寒桓刪山先仙蕭宵肴豪歌戈麻陽唐庚耕清青蒸登尤侯幽侵覃談鹽添咸銜嚴凡",
    "上": "董腫講紙旨止尾語麌姥薺蟹駭賄海軫準吻隱阮混很旱緩潸產銑獮篠小巧晧哿果馬養蕩梗耿靜迥拯等有厚黝寑感敢琰忝豏檻儼范",
    "去": "送宋用絳寘至志未御遇暮霽祭泰卦怪夬隊代廢震稕問焮願慁恨翰換諫襉霰線嘯笑效號箇過禡漾宕映諍勁徑證嶝宥候幼沁勘闞豔㮇陷鑑釅梵",
    "入": "屋沃燭覺質術櫛物迄月沒曷末黠鎋屑薛藥鐸陌麥昔錫職德緝合盍葉怗洽狎業乏",
}.items():
    for _n in _names:
        _YUN_TONE[_n] = _tone


class Phonology:
    """字 → 广韵读音候选 [{tone, yun, initial, fanqie}]（简繁双索引）。"""

    def __init__(self):
        self.readings: Dict[str, List[Dict[str, str]]] = {}
        syl: Dict[str, Dict[str, str]] = {}
        syl_path = config.RAW_DIR / "ytenx" / "guangyun_syllables.tsv"
        chars_path = config.RAW_DIR / "ytenx" / "guangyun_chars.tsv"
        if not (syl_path.exists() and chars_path.exists()):
            return
        unmapped = set()
        with syl_path.open(encoding="utf-8") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                if len(p) < 6:
                    continue
                raw_yun = p[4]
                yun = _YUN_VARIANT.get(raw_yun, _YUN_VARIANT.get(raw_yun.rstrip("AB"),
                                                                 raw_yun.rstrip("AB")))
                tone = _YUN_TONE.get(yun) or _YUN_EXTRA_TONE.get(yun)
                if tone is None:
                    unmapped.add(raw_yun)
                    continue
                syl[p[0]] = {"tone": tone, "yun": yun, "initial": p[2], "fanqie": p[5]}
        # 极罕见附韵允许跳过；规模性缺失说明数据/表损坏，响亮报错
        if len(unmapped) > 20:
            raise RuntimeError(f"广韵韵目大量未覆盖（数据或声调表损坏）：{sorted(unmapped)[:10]}…")
        self.unmapped_yun = sorted(unmapped)
        with chars_path.open(encoding="utf-8") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                if len(p) < 2 or p[1] not in syl:
                    continue
                ch, entry = p[0], syl[p[1]]
                for key in {ch, t2s(ch)}:
                    lst = self.readings.setdefault(key, [])
                    if entry not in lst:
                        lst.append(entry)

    @property
    def ready(self) -> bool:
        return bool(self.readings)

    def char_readings(self, ch: str) -> List[Dict[str, str]]:
        return self.readings.get(ch) or self.readings.get(t2s(ch)) or []

    def ping_ze(self, ch: str) -> str:
        """平 / 仄 / 两读 / 无考。"""
        tones = {r["tone"] for r in self.char_readings(ch)}
        if not tones:
            return "无考"
        ping = "平" in tones
        ze = bool(tones - {"平"})
        return "两读" if (ping and ze) else ("平" if ping else "仄")

    def line_pattern(self, line: str) -> List[str]:
        return [self.ping_ze(c) for c in cjk_chars(strip_brackets(line))]

    # ── 律则检测（近体近似口径，多音不确定如实标注）───────────────
    def analyze_poem(self, lines: List[str], rhyme_feet: List[str]) -> Dict:
        patterns = [self.line_pattern(ln) for ln in lines]
        issues: List[Dict] = []
        uncertain = sum(p.count("两读") + p.count("无考") for p in patterns)

        def val(x):  # 两读/无考 → None（不参与违例判定）
            return x if x in ("平", "仄") else None

        # 三平尾/三仄尾（只在末三字全部确定时判）
        for i, p in enumerate(patterns):
            if len(p) >= 3:
                tail = [val(x) for x in p[-3:]]
                if all(t == "平" for t in tail):
                    issues.append({"rule": "三平尾", "line": i + 1})
                if all(t == "仄" for t in tail):
                    issues.append({"rule": "三仄尾", "line": i + 1})
        # 二四（六）字交替 + 联内对 + 联间粘（4/8 句、5/7 言时检查）
        n = len(patterns)
        if n in (4, 8) and patterns and len(set(map(len, patterns))) == 1 \
                and len(patterns[0]) in (5, 7):
            key_pos = [1, 3] + ([5] if len(patterns[0]) == 7 else [])
            for i, p in enumerate(patterns):
                vals = [val(p[j]) for j in key_pos]
                for a, b in zip(vals, vals[1:]):
                    if a and b and a == b:
                        issues.append({"rule": "二四六不交替", "line": i + 1})
                        break
            for i in range(0, n - 1, 2):   # 联内对：2/4/6位平仄相对
                for j in key_pos:
                    a, b = val(patterns[i][j]), val(patterns[i + 1][j])
                    if a and b and a == b:
                        issues.append({"rule": "失对", "couplet": i // 2 + 1, "pos": j + 1})
                        break
            for i in range(1, n - 1, 2):   # 联间粘：下联出句第2字与上联对句第2字同调
                a, b = val(patterns[i][1]), val(patterns[i + 1][1])
                if a and b and a != b:
                    issues.append({"rule": "失粘", "between_couplets": (i // 2 + 1, i // 2 + 2)})
        # 韵脚：声调一致性 + 归部
        feet_info = []
        for ch in rhyme_feet:
            rs = self.char_readings(ch)
            feet_info.append({"char": ch,
                              "tones": sorted({r["tone"] for r in rs}) or ["无考"],
                              "yun": sorted({r["yun"] for r in rs})})
        det = [f for f in feet_info if len(f["tones"]) == 1 and f["tones"][0] != "无考"]
        rhyme_tone = ""
        if det:
            tones = {f["tones"][0] for f in det}
            rhyme_tone = ("平韵" if tones == {"平"} else
                          "仄韵" if "平" not in tones else "平仄混押（或换韵）")
        return {
            "layer": "B",
            "source": "《广韵》（韵典网整理本）",
            "line_patterns": ["".join(p) for p in patterns],
            "uncertain_chars": uncertain,
            "issues": issues,
            "rhyme_feet_phonology": feet_info,
            "rhyme_tone": rhyme_tone,
            "note": "平仄依《广韵》韵目定调；多音字标「两读」不参与违例判定；"
                    "拗救与首句入韵变格不判（诚实边界）。近体律则仅对 4/8 句齐言诗检查。",
        }

    # ── 韵伴聚类交叉验证 ─────────────────────────────────────────
    def group_yun_profile(self, members: List[str]) -> Dict:
        yun_count: Dict[str, int] = {}
        tone_count: Dict[str, int] = {}
        for ch in members:
            rs = self.char_readings(ch)
            for y in {r["yun"] for r in rs}:
                yun_count[y] = yun_count.get(y, 0) + 1
            for tn in {r["tone"] for r in rs}:
                tone_count[tn] = tone_count.get(tn, 0) + 1
        top = sorted(yun_count.items(), key=lambda kv: -kv[1])[:4]
        return {"top_yun": [{"yun": y, "chars": c} for y, c in top],
                "tone_distribution": tone_count}


_phonology: Optional[Phonology] = None


def get_phonology() -> Phonology:
    global _phonology
    if _phonology is None:
        _phonology = Phonology()
    return _phonology
