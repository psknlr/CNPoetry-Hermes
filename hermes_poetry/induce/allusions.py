"""典故种子图谱（第二阶段 MVP）：精选典故 → 出处 → 语料用例。

诚实口径：种子表为编辑精选（curated_seed，非穷举）；出处标注典籍篇名，
出处原文回源接入 gujilab 十三经语料（已入库者）与后续 classics 层；
检测=表面形式逐字命中（T5 语义层面典故留待知识图谱扩展）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..textutil import t2s

# 典故 → {surfaces, source(出处), source_text(典源梗概), implies(常用义)}
ALLUSION_SEEDS: Dict[str, Dict] = {
    "折柳": {"surfaces": ["折柳", "折杨柳"], "source": "汉乐府《折杨柳》/灞桥送别俗",
             "implies": "送别惜别"},
    "阳关": {"surfaces": ["阳关"], "source": "王维《送元二使安西》后成送别曲《阳关三叠》",
             "implies": "送别"},
    "楼兰": {"surfaces": ["楼兰", "斩楼兰"], "source": "《汉书·傅介子传》斩楼兰王",
             "implies": "破敌立功"},
    "燕然": {"surfaces": ["燕然", "勒燕然"], "source": "《后汉书·窦宪传》燕然勒石",
             "implies": "边功未成/建功"},
    "庄周梦蝶": {"surfaces": ["庄生晓梦", "梦蝶", "蝴蝶梦"], "source": "《庄子·齐物论》",
                 "implies": "人生如梦/物我两忘"},
    "望帝杜鹃": {"surfaces": ["望帝", "杜鹃啼血", "啼鹃"], "source": "《华阳国志》望帝化鹃",
                 "implies": "冤魂哀思"},
    "青鸟": {"surfaces": ["青鸟"], "source": "《山海经》西王母信使",
             "implies": "音信/信使"},
    "蓬山": {"surfaces": ["蓬山", "蓬莱"], "source": "《山海经》海上仙山",
             "implies": "可望难即之地"},
    "牛女": {"surfaces": ["牵牛织女", "鹊桥", "银汉迢迢"], "source": "《古诗十九首》/七夕传说",
             "implies": "隔绝相思"},
    "嫦娥": {"surfaces": ["嫦娥", "姮娥"], "source": "《淮南子》奔月",
             "implies": "孤寂悔恨"},
    "王孙": {"surfaces": ["王孙归", "王孙游"], "source": "《楚辞·招隐士》王孙游兮不归",
             "implies": "游子不归"},
    "采薇": {"surfaces": ["采薇"], "source": "《诗经·小雅·采薇》/伯夷叔齐首阳采薇",
             "implies": "戍役之苦/隐逸守节"},
    "东篱": {"surfaces": ["东篱"], "source": "陶渊明《饮酒》采菊东篱下",
             "implies": "隐逸闲适"},
    "五柳": {"surfaces": ["五柳"], "source": "陶渊明《五柳先生传》",
             "implies": "隐士自况"},
    "桃源": {"surfaces": ["桃源", "武陵人", "桃花源"], "source": "陶渊明《桃花源记》",
             "implies": "避世理想乡"},
    "知音": {"surfaces": ["知音", "伯牙", "钟期"], "source": "《吕氏春秋》伯牙鼓琴钟子期",
             "implies": "知己难遇"},
    "王谢": {"surfaces": ["王谢"], "source": "《世说新语》东晋王谢门第",
             "implies": "盛衰兴亡"},
    "后庭花": {"surfaces": ["后庭花"], "source": "陈后主《玉树后庭花》",
               "implies": "亡国之音"},
    "廉颇": {"surfaces": ["廉颇"], "source": "《史记·廉颇蔺相如列传》",
             "implies": "老将壮心"},
    "封侯": {"surfaces": ["觅封侯", "万户侯"], "source": "《后汉书·班超传》投笔觅封侯",
             "implies": "功名之志"},
    "精卫": {"surfaces": ["精卫"], "source": "《山海经》精卫填海",
             "implies": "抱憾不屈"},
    "湘妃": {"surfaces": ["湘妃", "斑竹", "湘泪"], "source": "《博物志》舜妃泪染斑竹",
             "implies": "悲悼之泪"},
    "沧海桑田": {"surfaces": ["沧海桑田", "桑田碧海"], "source": "《神仙传》麻姑语",
                 "implies": "世事巨变"},
    "长门": {"surfaces": ["长门"], "source": "司马相如《长门赋》陈皇后失宠",
             "implies": "失宠幽怨"},
    "金屋": {"surfaces": ["金屋"], "source": "《汉武故事》金屋藏娇",
             "implies": "宠爱"},
    "乌衣巷": {"surfaces": ["乌衣巷"], "source": "金陵王谢故居",
               "implies": "繁华成空"},
    "闻笛": {"surfaces": ["山阳笛", "闻笛赋"], "source": "向秀《思旧赋》闻邻笛悼嵇康",
             "implies": "悼亡怀旧"},
    "烂柯": {"surfaces": ["烂柯"], "source": "《述异记》王质观棋斧柯烂",
             "implies": "岁月恍隔"},
}

_SURFACE_INDEX: List = sorted(
    ((t2s(s), name) for name, spec in ALLUSION_SEEDS.items() for s in spec["surfaces"]),
    key=lambda kv: -len(kv[0]))


def detect_allusions(text: str) -> List[Dict]:
    folded = t2s(text)
    hits, seen = [], set()
    for surface, name in _SURFACE_INDEX:
        if surface in folded and name not in seen:
            seen.add(name)
            spec = ALLUSION_SEEDS[name]
            hits.append({"allusion": name, "surface": surface,
                         "source": spec["source"], "implies": spec["implies"],
                         "source_level": "curated_seed",
                         "note": "编辑精选种子（非穷举）；表面命中，典故语义层留待图谱扩展"})
    return hits
