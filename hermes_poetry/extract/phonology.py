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

    # ── 近体标准谱匹配（四起式）───────────────────────────────────
    # 基础句式（王力《诗词格律》通行口径）：
    # 五言 A仄仄平平仄 B平平仄仄平 C平平平仄仄 D仄仄仄平平；七言前加相反二字
    _BASE5 = {"A": "仄仄平平仄", "B": "平平仄仄平", "C": "平平平仄仄", "D": "仄仄仄平平"}
    _QISHI = {  # 起式 → 绝句四句的句式序列（律诗 = 重复两遍）
        "仄起不入韵": "ABCD", "仄起入韵": "DBCD",
        "平起不入韵": "CDAB", "平起入韵": "BDAB",
    }

    @classmethod
    def _template_lines(cls, qishi: str, char_n: int, n_lines: int) -> List[str]:
        seq = cls._QISHI[qishi] * (2 if n_lines == 8 else 1)
        out = []
        for key in seq:
            base = cls._BASE5[key]
            if char_n == 7:
                head = {"平": "仄仄", "仄": "平平"}[base[0]]
                base = head + base
            out.append(base)
        return out

    def match_template(self, patterns: List[List[str]]) -> Dict:
        """与四种起式标准谱比对：严格位（二四六与句脚）计违例，
        宽位（一三五）不计；两读/无考按通配处理。拗救不判（诚实边界）。"""
        n = len(patterns)
        if n not in (4, 8) or not patterns or len(set(map(len, patterns))) != 1 \
                or len(patterns[0]) not in (5, 7):
            return {}
        char_n = len(patterns[0])
        strict = [1, 3] + ([5] if char_n == 7 else []) + [char_n - 1]
        results = []
        for qishi in self._QISHI:
            tmpl = self._template_lines(qishi, char_n, n)
            dev = []
            for i, (p, t) in enumerate(zip(patterns, tmpl)):
                for j in strict:
                    if p[j] in ("平", "仄") and p[j] != t[j]:
                        dev.append({"line": i + 1, "pos": j + 1,
                                    "expected": t[j], "got": p[j]})
            results.append({"qishi": qishi, "deviations": len(dev),
                            "detail": dev[:6]})
        results.sort(key=lambda r: r["deviations"])
        best = results[0]
        return {"best_fit": best["qishi"], "deviations": best["deviations"],
                "deviation_detail": best["detail"],
                "all_fits": [{"qishi": r["qishi"], "deviations": r["deviations"]}
                             for r in results],
                "note": "标准谱四起式比对（严格位=二四六与句脚，宽位一三五不计）；"
                        "偏差≠不合律：拗救与变格未判，仅作初筛。"}

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
            gys = sorted({r["yun"] for r in rs})
            pss = sorted({pingshui_of(y) for y in gys if pingshui_of(y)})
            feet_info.append({"char": ch,
                              "tones": sorted({r["tone"] for r in rs}) or ["无考"],
                              "yun": gys, "pingshui": pss,
                              "cilin": sorted({b for p in pss for b in cilin_of(p)})})
        det = [f for f in feet_info if len(f["tones"]) == 1 and f["tones"][0] != "无考"]
        rhyme_tone = ""
        if det:
            tones = {f["tones"][0] for f in det}
            rhyme_tone = ("平韵" if tones == {"平"} else
                          "仄韵" if "平" not in tones else "平仄混押（或换韵）")
        # 韵脚一致性反推消歧：确定韵脚同声调时，两读韵脚按押韵约束取该调
        # （决策附依据并标 requires_review，绝不静默裁决）
        if det and len({f["tones"][0] for f in det}) == 1:
            target = det[0]["tones"][0]
            for f in feet_info:
                if len(f["tones"]) > 1 and target in f["tones"]:
                    f["decision"] = target
                    f["basis"] = ["同诗其余韵脚均为" + target + "声（押韵一致性反推）"]
                    f["requires_review"] = True
        return {
            "layer": "B",
            "phonology_system": "Guangyun-derived",
            "target_period": "Middle Chinese approximation",
            "historical_fit": "approximate",
            "source": "《广韵》（韵典网整理本）",
            "line_patterns": ["".join(p) for p in patterns],
            "uncertain_chars": uncertain,
            "issues": issues,
            "template_match": self.match_template(patterns),
            "rhyme_feet_phonology": feet_info,
            "rhyme_tone": rhyme_tone,
            "note": "平仄依《广韵》推导（成书1008年，为唐宋作诗音系的近似而非实录）；"
                    "多音字标「两读」不参与违例判定；拗救与变格不判（诚实边界）。"
                    "近体律则仅对 4/8 句齐言诗检查，失对/失粘为初筛非定谳。",
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


# ── 平水韵（106 韵）：广韵 206 韵的规范合并（文献学经典合并表）──────
_PINGSHUI_MERGE = {
    # 平声三十韵
    "东": "東", "冬": "冬鍾", "江": "江", "支": "支脂之", "微": "微",
    "鱼": "魚", "虞": "虞模", "齐": "齊", "佳": "佳皆", "灰": "灰咍",
    "真": "真諄臻", "文": "文欣", "元": "元魂痕", "寒": "寒桓", "删": "刪山",
    "先": "先仙", "萧": "蕭宵", "肴": "肴", "豪": "豪", "歌": "歌戈",
    "麻": "麻", "阳": "陽唐", "庚": "庚耕清", "青": "青", "蒸": "蒸登",
    "尤": "尤侯幽", "侵": "侵", "覃": "覃談", "盐": "鹽添嚴", "咸": "咸銜凡",
    # 上声二十九韵
    "董": "董", "肿": "腫", "讲": "講", "纸": "紙旨止", "尾": "尾",
    "语": "語", "麌": "麌姥", "荠": "薺", "蟹": "蟹駭", "贿": "賄海",
    "轸": "軫準", "吻": "吻隱", "阮": "阮混很", "旱": "旱緩", "潸": "潸產",
    "铣": "銑獮", "筱": "篠小", "巧": "巧", "皓": "晧", "哿": "哿果",
    "马": "馬", "养": "養蕩", "梗": "梗耿靜", "迥": "迥拯等", "有": "有厚黝",
    "寝": "寑", "感": "感敢", "俭": "琰忝儼", "豏": "豏檻范",
    # 去声三十韵
    "送": "送", "宋": "宋用", "绛": "絳", "寘": "寘至志", "未": "未",
    "御": "御", "遇": "遇暮", "霁": "霽祭", "泰": "泰", "卦": "卦怪夬",
    "队": "隊代廢", "震": "震稕", "问": "問焮", "愿": "願慁恨", "翰": "翰換",
    "谏": "諫襉", "霰": "霰線", "啸": "嘯笑", "效": "效", "号": "號",
    "个": "箇過", "祃": "禡", "漾": "漾宕", "敬": "映諍勁", "径": "徑證嶝",
    "宥": "宥候幼", "沁": "沁", "勘": "勘闞", "艳": "豔㮇釅", "陷": "陷鑑梵",
    # 入声十七韵
    "屋": "屋", "沃": "沃燭", "觉": "覺", "质": "質術櫛", "物": "物迄",
    "月": "月沒", "曷": "曷末", "黠": "黠鎋", "屑": "屑薛", "药": "藥鐸",
    "陌": "陌麥昔", "锡": "錫", "职": "職德", "缉": "緝", "合": "合盍",
    "叶": "葉怗", "洽": "洽狎業乏",
}
GY_TO_PINGSHUI: Dict[str, str] = {}
for _ps, _gys in _PINGSHUI_MERGE.items():
    for _gy in _gys:
        GY_TO_PINGSHUI[_gy] = _ps

# ── 词林正韵（19 部）：平水韵的再合并；歧属韵如实并列多候选 ────────
_CILIN = {
    "第一部": "东冬董肿送宋", "第二部": "江阳讲养绛漾", "第三部": "支微齐纸尾荠寘未霁",
    "第四部": "鱼虞语麌御遇", "第五部": "佳蟹卦泰灰贿队", "第六部": "真文轸吻震问",
    "第七部": "寒删先元旱潸铣阮翰谏霰愿", "第八部": "萧肴豪筱巧皓啸效号",
    "第九部": "歌哿个", "第十部": "麻马祃", "第十一部": "庚青蒸梗迥敬径",
    "第十二部": "尤有宥", "第十三部": "侵寝沁", "第十四部": "覃盐咸感俭豏勘艳陷",
    "第十五部": "屋沃", "第十六部": "觉药", "第十七部": "质陌锡职缉",
    "第十八部": "物月曷黠屑叶", "第十九部": "合洽",
}
PS_TO_CILIN: Dict[str, List[str]] = {}
for _bu, _pss in _CILIN.items():
    for _ps in _pss:
        PS_TO_CILIN.setdefault(_ps, []).append(_bu)
# 歧属说明（灰/佳/泰/卦/队/元/阮/愿 等在词林正韵中分属两部，按字分派，
# 本表整韵并列候选——与多音字「两读」同一诚实口径）
CILIN_NOTE = "词林正韵按平水韵整韵映射；歧属韵（如元/灰/佳）并列全部候选部，不按字裁决。"


def pingshui_of(gy_yun: str) -> str:
    return GY_TO_PINGSHUI.get(gy_yun, "")


def cilin_of(ps_yun: str) -> List[str]:
    return PS_TO_CILIN.get(ps_yun, [])
