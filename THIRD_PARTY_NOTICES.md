# 第三方数据与许可声明（THIRD PARTY NOTICES）

本项目代码以 MIT 许可发布。项目内置/引用的数据资产版权与许可归各原始来源，
分项声明如下。若任何来源方对本项目的使用方式提出异议，请提 issue，我们将
及时调整或移除相应数据。

## 1. chinese-poetry（`data/raw/chinese_poetry/`）

- 来源：https://github.com/chinese-poetry/chinese-poetry
- 许可：MIT
- 用途：A 层原文语料（诗经/楚辞/唐诗/宋诗/宋词/五代词/元曲/纳兰/曹操等
  26,720 首）与 C 层作者旁证（`authors/`）。
- 处理：仅做编码归一/繁简折叠登记，不改动文本内容；逐源 fail-closed
  白名单登记于 `hermes_poetry/corpus/`。

## 2. gujilab/chinese-classical-corpus（`data/raw/gujilab/`）

- 来源：https://huggingface.co/datasets/gujilab/chinese-classical-corpus
- 许可：以该数据集卡片声明为准（抽取时标注为 CC0；《说文解字》《尔雅》
  原典属公有领域）。
- 用途：C 层训诂旁证（说文 9,000+ 字头、尔雅 250+ 义组），支撑
  `poetry_gloss` 字义工具。

## 3. PoetryMTEB/ChineseClassicalPoetryDatabase（`data/raw/hf_poetrymteb/`）

- 来源：https://huggingface.co/datasets/PoetryMTEB/ChineseClassicalPoetryDatabase
- 许可：以该数据集条款为准；本仓库仅保留经 datasets-server API 对齐后的
  分析样本（`analysis_sample.jsonl`，3,139 条）。
- 用途：D 层外部分析绑定（external_analysis_rule）。所有 D 层规则经双向
  回源核验后才进入规则库，且 `interpretation_level` 恒为 `external_llm`、
  UI/回答中恒标注「外部分析，非本系统结论」。

## 4. 韵典网《广韵》整理数据（`data/raw/ytenx/`）

- 来源：https://github.com/BYVoid/ytenx （ytenx.org 数据文件）
- 许可：《广韵》（1008）原典属公有领域；本抽取仅含音韵结构字段
  （字→小韵、声母/韵目/反切），不含释义文本；整理本的使用以
  BYVoid/ytenx 仓库条款为准。
- 用途：B 层中古音韵计量（平仄/韵部/律则检测）；平水韵 106 部与词林正韵
  19 部由内嵌规范并表推导（见 `hermes_poetry/extract/phonology.py`）。

## 4a. 龙榆生《唐宋词格律》整理数据（`data/raw/longyusheng/`）

- 来源：longyusheng.org 站点开源仓库（数字化工程以 AGPL-3.0 发布）；
  《唐宋词格律》原书为龙榆生（1902–1966）词学著作。
- 内容：153 调词谱（调名/异名/类别/说明/定格与变格符号谱）之结构化转写，
  谱面内容未改动；本仓库保留该目录数据的原始许可归属，详见目录内 README。
- 用途：创作实验室与词牌定格的「词谱权威层」，与语料归纳定格并列展示；
  输出恒标 `source_level: 词谱权威（龙榆生）`。

## 5. OpenCC 繁简对照表（`data/raw/charmap/TSCharacters.txt`）

- 来源：https://github.com/BYVoid/OpenCC
- 许可：Apache License 2.0
- 用途：繁→简折叠（t2s），仅用于证据回源比对（`contains_verbatim`），
  展示层保留原字形。

## 6. 典故种子表（`data/raw/allusions/allusion_seeds.jsonl`）

- 来源：本项目编辑自撰（梗概文字为编辑撰写；出处指向公有领域典籍）。
- 许可：CC0。
- 性质：编辑精选种子而非穷举；表面命中仅产生「候选」状态，须语境确认。

## 7. 内嵌规范表（代码内数据）

- 广韵 206 韵目四声表、平水韵 106 部并表、词林正韵 19 部并表、四起式
  标准谱（王力《诗词格律》通行约定的结构化转写）：韵书分部与格律谱系
  属公域学术常识，结构化转写由本项目完成，随代码以 MIT 发布；构建时对
  未覆盖韵目响亮报错（fail-loud），不静默兜底。
