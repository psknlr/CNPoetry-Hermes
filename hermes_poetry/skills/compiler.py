"""Skill 编译：把规则库编译为可被任意智能体运行时装载的技能树。

每个 Skill 是一个目录：SKILL.md（YAML frontmatter + 文档）+
rules.jsonl（机器可读规则）+ examples.jsonl（问答路由示例）。
skills_manifest.json 记录家族计数。技能是纯数据。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

from .. import config
from ..schemas import JsonRecord

CORE_PRINCIPLES = """
## 核心原则（全体 Skill 共享）

> 无原文，不成论断。无篇目编号，不成证据。无证据链，不成回答。

- 引用诗句必须逐字回源到 poem_id 对应原文；回源失败的内容不得输出。
- 论断须标注证据层级：A 原文 / B 计量 / C 旁证 / D 外部分析 / E 模型解释。
- 韵伴聚类与词牌定格为语料归纳，非韵书/词谱权威表，表述时不得冒称权威。
- 后世鉴赏套语（借景抒情/情景交融等）只能作为解释层，不得写成语料事实。
""".strip()


def _frontmatter(name: str, description: str, **extra) -> str:
    lines = ["---", f"name: {name}", f"description: {description}"]
    for k, v in extra.items():
        lines.append(f"{k}: {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}")
    lines += ["---", ""]
    return "\n".join(lines)


def _write_skill(skill_dir: Path, skill_md: str, rules: List, examples: List[Dict]) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_md + "\n\n" + CORE_PRINCIPLES + "\n", encoding="utf-8")
    with (skill_dir / "rules.jsonl").open("w", encoding="utf-8") as fh:
        for r in rules:
            fh.write((r.to_json() if isinstance(r, JsonRecord) else json.dumps(r, ensure_ascii=False)) + "\n")
    with (skill_dir / "examples.jsonl").open("w", encoding="utf-8") as fh:
        for e in examples:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


class SkillCompiler:
    def __init__(self, imagery_rules, theme_rules, cipai_rules, author_rules,
                 rhyme_rules, stats: Dict):
        self.imagery_rules = imagery_rules
        self.theme_rules = theme_rules
        self.cipai_rules = cipai_rules
        self.author_rules = author_rules
        self.rhyme_rules = rhyme_rules
        self.stats = stats

    def build_all(self) -> Dict[str, int]:
        root = config.SKILLS_DIR
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)
        counts = {
            "catalog": self._catalog(root),
            "imagery": self._imagery(root),
            "themes": self._themes(root),
            "cipai": self._cipai(root),
            "authors": self._authors(root),
            "rhyme": self._rhyme(root),
            "gloss": self._gloss(root),
        }
        manifest = {
            "tree": "hermes.cnpoetry",
            "root": str(root.relative_to(config.DATA_DIR)),
            "families": counts,
            "total_skills": sum(counts.values()),
        }
        (root / "skills_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        return counts

    def _catalog(self, root: Path) -> int:
        md = _frontmatter("hermes.cnpoetry.catalog", "诗海赫尔墨斯技能总目：规则库统计与路由指引") + \
            "# 技能总目\n\n" + \
            f"- 作品数：{self.stats.get('poems', 0)}\n" + \
            f"- 通过初始规则：{self.stats.get('accepted', 0)}（拒绝 {self.stats.get('rejected', 0)}）\n" + \
            f"- 意象档案：{len(self.imagery_rules)}；题材档案：{len(self.theme_rules)}；" \
            f"词牌定格：{len(self.cipai_rules)}；诗人档案：{len(self.author_rules)}；韵组：{len(self.rhyme_rules)}\n"
        examples = [
            {"query": "明月在诗里代表什么", "route": "imagery", "args": {"imagery": "月"}},
            {"query": "水调歌头的定格", "route": "cipai", "args": {"cipai": "水调歌头"}},
            {"query": "推荐表达思乡的诗", "route": "match", "args": {"mood": "思乡"}},
        ]
        _write_skill(root / "hermes.cnpoetry.catalog", md, [], examples)
        return 1

    def _imagery(self, root: Path) -> int:
        n = 0
        for r in self.imagery_rules:
            if r.n_poems < 3:
                continue
            top = "、".join(f"{a['emotion']}({a['support']})" for a in r.emotion_associations[:3])
            md = _frontmatter(f"hermes.cnpoetry.imagery.{r.imagery}",
                              f"意象「{r.imagery}」档案：{r.n_poems} 首支撑，主要情感关联 {top}",
                              imagery=r.imagery, release_level=r.release_level) + \
                f"# 意象档案：{r.imagery}\n\n表面形式：{'、'.join(r.surface_forms[:10])}\n\n" + \
                "## 情感关联（跨诗归纳，逐条带证据）\n\n" + "\n".join(
                    f"- **{a['emotion']}**（支撑 {a['support']} 例）：如《{a['example'].get('title','')}》"
                    f"「{a['example']['quote']}」（{a['example']['poem_id']}）"
                    for a in r.emotion_associations[:6])
            examples = [{"query": f"{r.imagery}的意象含义", "route": "imagery", "args": {"imagery": r.imagery}}]
            _write_skill(root / "hermes.cnpoetry.imagery" / r.imagery, md, [r], examples)
            n += 1
        return n

    def _themes(self, root: Path) -> int:
        n = 0
        for r in self.theme_rules:
            md = _frontmatter(f"hermes.cnpoetry.theme.{r.theme}",
                              f"题材「{r.theme}」档案：{r.n_poems} 首，{r.definition}",
                              theme=r.theme) + \
                f"# 题材档案：{r.theme}\n\n{r.definition}\n\n标记词：{'、'.join(r.marker_terms[:12])}\n\n" + \
                "## 例证\n\n" + "\n".join(
                    f"- 《{e['title']}》「{e['quote']}」（{e['poem_id']}）" for e in r.example_evidence[:6])
            _write_skill(root / "hermes.cnpoetry.theme" / r.theme, md, [r],
                         [{"query": f"{r.theme}的诗", "route": "teach", "args": {"topic": r.theme}}])
            n += 1
        return n

    def _cipai(self, root: Path) -> int:
        n = 0
        for r in self.cipai_rules:
            if r.n_poems < 3:
                continue
            md = _frontmatter(f"hermes.cnpoetry.cipai.{r.cipai}",
                              f"词牌「{r.cipai}」定格（语料归纳）：{r.n_poems} 首，众数句式 {r.char_pattern}",
                              cipai=r.cipai) + \
                f"# 词牌定格：{r.cipai}\n\n- 语料样本：{r.n_poems} 首\n- 众数句式：{r.char_pattern}" \
                f"（一致率 {r.pattern_consistency:.0%}）\n- 众数句数：{r.line_count_mode}\n\n> {r.note}\n"
            _write_skill(root / "hermes.cnpoetry.cipai" / r.cipai, md, [r],
                         [{"query": f"{r.cipai}的格式", "route": "cipai", "args": {"cipai": r.cipai}}])
            n += 1
        return n

    def _authors(self, root: Path) -> int:
        n = 0
        for r in self.author_rules:
            if r.n_poems < 8:
                continue
            md = _frontmatter(f"hermes.cnpoetry.author.{r.author}",
                              f"诗人档案：{r.author}（{r.dynasty}），语料 {r.n_poems} 首",
                              author=r.author) + \
                f"# 诗人档案：{r.author}（{r.dynasty}）\n\n高频意象：" + \
                "、".join(f"{x['imagery']}({x['count']})" for x in r.top_imagery[:6]) + \
                ("\n\n## 小传（C层旁证）\n\n" + r.bio[:400] if r.bio else "")
            _write_skill(root / "hermes.cnpoetry.author" / r.author, md, [r],
                         [{"query": f"{r.author}的诗风", "route": "author", "args": {"author": r.author}}])
            n += 1
        return n

    def _gloss(self, root: Path) -> int:
        md = _frontmatter("hermes.cnpoetry.gloss",
                          "字义训诂（C层）：说文解字逐字条目与尔雅训释组（gujilab，CC0）") + \
            "# 字义训诂\n\n以《说文解字》9,829 条逐字条目（部首/反切/释文）与《尔雅》训释组\n" \
            "回答单字本义。诗中用义可能引申，本层为 C 层旁证，不作诗义定论。\n"
        _write_skill(root / "hermes.cnpoetry.gloss", md, [],
                     [{"query": "婵字的本义", "route": "gloss", "args": {"chars": "婵"}},
                      {"query": "说文解字怎么解释天", "route": "gloss", "args": {"chars": "天"}}])
        return 1

    def _rhyme(self, root: Path) -> int:
        md = _frontmatter("hermes.cnpoetry.rhyme", f"韵伴聚类（语料归纳）：{len(self.rhyme_rules)} 组") + \
            "# 韵伴聚类\n\n" + "\n".join(
                f"- 【{r.label}】{len(r.members)} 字，支撑 {r.n_poems} 首：{''.join(r.members[:20])}…"
                for r in self.rhyme_rules[:30]) + \
            "\n\n> 由近体诗偶数句尾字共现归纳，非平水韵权威表。\n"
        _write_skill(config.SKILLS_DIR / "hermes.cnpoetry.rhyme", md, self.rhyme_rules,
                     [{"query": "天字和什么字押韵", "route": "rhyme", "args": {"char": "天"}}])
        return 1
