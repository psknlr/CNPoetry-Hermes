# Hermes-CNPoetry（诗海赫尔墨斯）

**中华古典诗词自主规则挖掘与 Skill 生成系统** —— 把古典诗词语料转化为一个
可回源、可推理、可比较、可教学、可研究、可调用的规则系统与多智能体。

> 架构参照 [Shanghan-Hermes（伤寒-赫尔墨斯）](https://github.com/pariskang/Shanghan-Hermes)：
> 同一套「证据优先」设计理念，从《伤寒论》条文域完整移植到古典诗词域。

```text
chinese-poetry 原始语料 → 作品级归一化（简繁双轨）→ 格律计量层
→ 意象/情感/题材规则挖掘 → 自主审核闸门（逐字回源）→ 跨诗归纳
→（意象档案｜词牌定格｜诗人档案｜韵伴聚类｜互文检测）
→ Hermes Skill 编译 → 检索/荐诗/对比/教学/研究/多智能体合议多端调用
```

## 核心原则

> 无原文，不成论断。无篇目编号，不成证据。无证据链，不成回答。
> 意象规则必须逐字回源到具体诗句；回源失败直接进入 rejected/。
> 论断必须区分证据层级；韵伴聚类与词牌定格是语料归纳，不得冒称韵书词谱权威。
> 智能体不得杜撰诗句、不得张冠李戴、不得把生成内容伪托为古人作品。

这些不是口号，而是流水线中的硬性闸门：每条规则的 `evidence_span` 必须逐字
存在于对应作品（简繁异体折叠后判定）；证据回源失败的规则直接进入
`rejected/`；对抗性测试（`tests/test_review.py`）注入伪造证据、错误篇目、
否定语境情感、强度虚标与后世套语，并断言其被拒绝或修复降级。

## 证据分级（贯穿全系统）

| 层级 | 含义 | 来源 |
|---|---|---|
| **A 原文** | 语料原文直录 | chinese-poetry 各集子 |
| **B 计量** | 确定性算法可复算的形式事实 | 句式/体裁判定/韵脚位置/韵伴聚类 |
| **C 旁证** | 集内注释、作者小传、白话导读、字义训诂 | 花间集/南唐二主词 notes、全唐诗小传、水墨唐诗、说文解字/尔雅（gujilab） |
| **D 外部分析** | 外部数据集 LLM 生成（非本系统结论） | PoetryMTEB（DeepSeek-V3.1 分析层），3,084 首双向回源绑定 |
| **E 模型解释** | 本系统模型推理，全部过引用核验 | 可选接入的真实大模型 |

## 快速开始

纯 Python 标准库实现，**零第三方依赖**（Python ≥ 3.9），离线全功能可跑。

```bash
git clone <本仓库>
cd CNPoetry-Hermes

# 一键全量流水线（语料 → 计量 → 规则 → 审核 → 归纳 → Skill，约 40 秒）
python3 -m hermes_poetry pipeline

# 规则库统计 / 就绪探针
python3 -m hermes_poetry stats
python3 -m hermes_poetry readyz

# 原文检索（简繁皆可输入；BM25 + 结构化过滤 + 意象覆盖重排）
python3 -m hermes_poetry search "大漠孤烟直"
python3 -m hermes_poetry search "明月" --dynasty 宋 --expand
python3 -m hermes_poetry search "《静夜思》"

# 情境荐诗（心境 → 意象/题材/情感 → 证据计分）
python3 -m hermes_poetry match --mood "一个人在外地想家了"
python3 -m hermes_poetry match --imagery 月,雁 --themes 思乡羁旅

# 对比鉴赏（体裁/意象/题材/情感/互文逐轴）
python3 -m hermes_poetry differential "《静夜思》" "《月下独酌》"

# 作品全息（A原文/B计量/C旁证/D外部分析/互文）
python3 -m hermes_poetry poem "《春晓》"

# 教学（题材/体裁/意象/诗人）
python3 -m hermes_poetry teach 送别怀人
python3 -m hermes_poetry teach 七绝
python3 -m hermes_poetry teach 李白

# 意象档案 / 词牌定格 / 诗人档案 / 韵伴 / 互文 / 字义训诂
python3 -m hermes_poetry imagery 月
python3 -m hermes_poetry cipai 浣溪沙
python3 -m hermes_poetry author 杜甫
python3 -m hermes_poetry rhyme --char 天
python3 -m hermes_poetry intertext --text "月是故乡明"
python3 -m hermes_poetry gloss --chars 婵娟          # 说文解字/尔雅（C层）
python3 -m hermes_poetry gloss --poem "《静夜思》"    # 按作品高频字训诂

# 研究端（意象共现网络/朝代分布/情感×意象矩阵）
python3 -m hermes_poetry research

# 智能体问答（单体 ReAct + 引用核验）与多智能体合议
python3 -m hermes_poetry ask "明月在古诗里代表什么？" --answer-only
python3 -m hermes_poetry council "对比《静夜思》和《月下独酌》的异同" --answer-only

# 三大自监督评测（检索/体裁计量/引用落地）
python3 -m hermes_poetry evaluate

# 列出已编译 Skill
python3 -m hermes_poetry skills
```

## Web 控制台

```bash
python3 -m hermes_poetry serve        # 打开 http://127.0.0.1:8765/
# 非本机部署：设 HERMES_SERVER_TOKEN=… 开启 Bearer 鉴权（同时关闭开放 CORS）；
# 请求体上限 256KB，整数参数钳位，异常只回 trace_id 不回内部细节
```

纯标准库实现（`http.server` + 原生 JS 单页应用，无构建、无 CDN、离线可用，
移动端自适应）。16 个模块：总览 · 智能体 · **多智能体合议**（规划→取证→
意象/格律/题材/比较专家→批评→共识裁决→综合，可视化为时间线，每步附证据）·
原文检索 · 情境荐诗 · 对比鉴赏 · 教学 · 意象档案 · 词牌定格 · 诗人档案 ·
字义训诂 · 韵伴聚类 · 互文检测 · 研究端 · Skill 库 · 关于。
证据优先：答案中的 `poem_id` 一律可点击，展开**作品全息抽屉**（A/B/C/D 分层色标）。

## 多智能体合议

`Council.deliberate()` 把一次回答拆成可审计的流程：

1. **规划者**解析问题中的题名/意象/题材实体，决定派遣哪些专家；
2. **取证员**先行检索建立证据池；
3. **意象/格律/题材/比较专家**各自用自己的工具取证，产出结构化 judgment；
   接入真实大模型时每位专家附一句合议评述——评述只许引用自己证据内的
   poem_id，逐句过 CitationGuard，未过即弃用；
4. **批评者**清点无证据/报错的专家结论；
5. **共识裁决**按固定量表打分（直接证据/覆盖/广度/完整性−缺陷罚分），
   产出 `probable / needs_more_information / insufficient_evidence` 三级裁决；
6. **综合者**成稿，整稿再过 CitationGuard 并附【证据核验】落款。

### CitationGuard 三重核验

- **存在性**：被引 poem_id 必须在语料中，否则标记「疑似杜撰」；
- **引文**：引号内诗句必须逐字（简繁折叠后）存在于被引作品，并做就近归属
  检查——引文实际出自另一首被引诗时给出归属警告；
- **取证闭环**：本轮工具证据之外的真实编号同样违规（**存在≠取证**；
  传入空证据列表即 fail-closed，猜中的真实编号也不放行）。

## 接入真实大模型（可选）

```bash
pip install litellm
export ANTHROPIC_API_KEY=…             # 或 OPENAI_API_KEY / DEEPSEEK_API_KEY 等
export HERMES_LLM_MODEL=claude-sonnet-5
python3 -m hermes_poetry llm-status
```

无 key 时自动使用**确定性 local 后端**：与真实模型走完全相同的工具循环与
输出模式，全功能离线可跑、可测试、逐字节可复现；真实模型调用失败时优雅
回退并在文末标注。

## 数据源与落盘策略（三个数据源全部实质纳入）

- **① chinese-poetry（A 层核心语料 + C 层旁证，`data/raw/chinese_poetry/`，MIT）**：
  诗经 305 / 楚辞 65 / 唐诗三百首 / 千家诗 / 水墨唐诗（含白话导读）/
  全唐诗抽样 1 万 / 花间集 9 卷 + 南唐二主词（含注释）/ 全宋诗抽样 /
  宋词三百首 + 全宋词抽样 / 元曲全量 1.1 万 / 曹操诗集 / 纳兰词 /
  唐宋作者小传。
- **② PoetryMTEB/ChineseClassicalPoetryDatabase（D 层外部分析，
  `data/raw/hf_poetrymteb/`）**：按本语料 536 位作者定向抓取的分析行
  4,967 条（DeepSeek-V3.1 生成的题材/主题/意图/情感），经**双向回源**
  （作者一致 + 分析文本逐字含该诗首句）绑定 3,084 首，全部标注
  「外部 LLM 生成，非本系统结论」。
- **③ gujilab/chinese-classical-corpus（C 层训诂，`data/raw/gujilab/`，CC0）**：
  说文解字 9,829 条逐字条目（部首/反切/释文）+ 尔雅 298 组训释，
  驱动 `poetry_gloss` 字义工具与 Web 端「字义训诂」视图；简体查询
  自动命中繁体字头。
- 另：OpenCC `TSCharacters.txt`（简繁归一字表，Apache-2.0）。
- **生成产物（不入库）**：`data/poetry/` 与 `data/skills/` 由
  `pipeline` 零依赖确定性重建（约 40 秒），manifest 记录逐文件 sha256
  语料指纹；`readyz` 探针防「假健康」；BM25 索引扁平数组落盘缓存
  （指纹失效自动重建），CLI 冷启动端到端 12s → 2s。
- **扩充**：`python3 -m hermes_poetry fetch` 可下载全唐诗全量（5.7 万首）、
  全宋词全量等，见 `fetch --list`。

## 规则库规模（种子语料一次 pipeline 后）

| 资产 | 规模 |
|---|---|
| 归一化作品 | 26,720 首（跨集去重保留全本；异文版本并存；元曲支曲救回） |
| 初始规则（过闸门） | 48,370 条（拒绝 1,052 条，全量审计 ~29 万条） |
| 意象档案 | 50 个（如「月」，相反情感并存如实呈现，证据链跨朝代轮转采样） |
| 题材/词牌曲牌/诗人档案 | 9 / 578 / 487 个（元曲曲牌已入档；「失调名」占位符剔除） |
| 韵伴聚类 | 53 组（相邻韵脚连边归纳；平/入声零混杂，如「竹·宿」入声组、「年·天·烟」一先组） |
| 互文规则 | 14,037 条全量挖掘（重出互见/袭用/化用；科白体例已滤净） |
| D 层外部分析绑定 | 3,139 首（双向回源） |
| 编译 Skill | 828 个 |

## 评测（自监督，确定性可复现）

| 套件 | 口径 | 结果 |
|---|---|---|
| retrieval | 每首取最长一句作查询，命中原诗 | Top-1 94.0%，Top-5 98.7%，MRR 0.962 |
| metrics | 体裁计量 vs 语料金标签（唐诗三百首等 tags） | 一致率 97.7% |
| grounding | 自动问题库跑智能体，引用核验通过率 | 100%（local 后端） |

## 测试与对抗审核

```bash
python3 -m unittest discover -s tests    # 79 项，含两轮对抗性证据注入测试
```

`tests/test_review.py` 是「无原文，不成论断」的可执行契约：伪造证据跨度、
错误篇目编号、未见于证据句的意象、否定语境情感（「不愁」计为愁）、
强度虚标（邻句共现冒称同句）、后世鉴赏套语混入规则主体、D 层分析
未双向回源——逐项断言被拒绝或被修复降级。

`tests/test_adversarial_round2.py` 固化了一轮 84 智能体深度审核
（350 万 token，逐条对抗核验）实测击穿后修复的攻击面：简繁折叠丢字
致伪造跨度过闸、改一字引文经相似度兜底冒充已核验、LLM 回退答案污染
磁盘缓存、换韵古体把平/入声韵部焊进同一韵组、科白体例冒充文学化用、
词库映射伪造、语义硬失败规则高分发布等——修复回退即测试失败。

## 包结构

```
hermes_poetry/
├── corpus/       语料登记（fail-closed 白名单）/归一化/扩充下载
├── extract/      格律计量（B层）/意象情感题材标注/初始规则抽取
├── review/       自主审核闸门：schema→证据回源→语义→对抗批评→修复→共识→发布
├── induce/       跨诗归纳：意象/题材/词牌/诗人档案/韵伴聚类/互文/共现网络
├── rag/          BM25（字 unigram+bigram）/作品检索（过滤+覆盖重排+扩展）
├── skills/       Skill 编译（SKILL.md + rules.jsonl + examples.jsonl + manifest）
├── llm/          后端抽象（LiteLLM 可选 + 确定性 local + 磁盘缓存 + 优雅回退）
├── agent/        ToolRegistry（能力代理）/CitationGuard/单智能体/多智能体合议
├── apps/         领域引擎：荐诗/对比/教学/全息/研究
├── eval/         检索/计量/引用落地三大评测
├── server/       纯标准库 Web 控制台（16 模块单页应用）
└── cli.py        23 个子命令
```

## 许可

MIT。语料版权归各原始数据集（chinese-poetry MIT；OpenCC Apache-2.0；
PoetryMTEB 样本按其数据集条款；gujilab CC0）。
