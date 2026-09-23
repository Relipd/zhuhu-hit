# zhuhu-hit

把知乎热榜整理成可长期回溯的追踪档案:取当日热榜与回答 → 逐条归纳分析 → **两阶段发布闸门**(预筛 + 增量复核)只对过闸话题做延伸检索 → 按平台高赞写法成文 → 产出月度 Excel 与分页网页,并把当日的案例、话题与书写规范累积下来。
！！后续发布别做，会被封号，后续会调整

## 这是什么

一套在本机运行的知乎热榜跟进流程。仓库里只有两部分内容:

- **流程规范**:[`skills/zhihu-hot-track/SKILL.md`](skills/zhihu-hot-track/SKILL.md) —— 步骤、约束、判据、脚本清单、踩过的坑
- **通用脚本**:`skills/zhihu-hot-track/scripts/` —— 抓取、校验、生成、提示词模板,所有路径与日期通过参数传入

脚本负责取数据、校验与排版;**阅读与判断由 AI Agent 完成**(四维分析、话题延伸、情绪标注、成文)。

**先读这两份**:

| 文档 | 回答什么问题 |
|---|---|
| [`ARCHITECTURE.md`](skills/zhihu-hot-track/ARCHITECTURE.md) | 这套流程**由什么组成**、哪些部分与知乎无关**可以直接搬到别的平台**(四层结构 + 29 件组件逐件标注) |
| [`writing_method.md`](skills/zhihu-hot-track/writing_method.md) | **书写能力怎么复用** —— 唯一被单独抽成通用方法的一块:三段分工、奥卡姆剃刀、必须提防的"数据假象" |

## 产出

每次运行会在工作根目录(下文记为 `ROOT`)生成:

| 产物 | 内容 |
|---|---|
| `跟进excel-YYYY-MM.xlsx` | 月度文件,每个抓取日期一个 sheet;问题行 + 回答行,附四维分析与**多元化情绪三列**(标签 / 强度 / 指向);另有热点拓展、拟答参考两个累积 sheet |
| `知乎热榜跟进-YYYY-MM-DD.html` + 同名目录 | 入口页 → 索引页 → 每问题一页;回答折叠展示,附四维分析、情绪 chips、全部 20 条的热点拓展、✍️拟答参考 |
| `raw/YYYY-MM-DD/` | 当日原始数据与中间结果:热榜、回答、分析、延伸、事实性复核、发布台账 |
| `ext_search/YYYY-MM-DD/` | 子任务工作区:每 rank 的链证据与拟答稿、发散检索归档、情绪片段、书写逻辑片段 |
| `话题库/` | 跨日期累积的案例索引:`index.json`(机读)+ `话题库.md`(人读),用于后续运行时查重 |
| `书写skill/书写skill.md` | 跨日期累积的**书写规范**:从高赞回答里学到的"怎么写"(不含写了什么),越用越准 |

## 流程

| 步骤 | 做什么 | 执行者 |
|---|---|---|
| 0 体检 | 检查运行时、依赖、CLI 与凭证状态、工作根目录 | `doctor.py` |
| 1 取热榜与候选回答 | 取热榜前 20 条;对各问题做关键词搜索,汇成回答候选池 | `run.py` |
| 2 取高赞回答 | 按问题取回答列表并按赞同数保留前 N 条,与候选池取并集去重;同时记录该问题的回答总数与本次覆盖率 | `question_fetch.py` |
| 3 补全全文 | 为内容被截断的回答补齐正文,并标注该回答的获取状态 | `fulltext.py` |
| 4 逐条分析 | 阅读每条回答,归纳立场 / 解决思路 / 判断逻辑 / 情绪倾向 | Agent |
| 5 情绪标注 | 按词表判**情绪标签(≤3)+ 强度(1–5)+ 指向(6 类)**,必填理由;分批下放子任务,主 Agent 只复核分歧 | Agent(子任务并行) |
| 6 发布预闸门 | 检索前先粗筛:明显非时政的题**不进延伸检索**(实测省 75–80% 检索费);判"是"的从宽放行,留给步骤 8 复核兜底 | `gen_prompts.py --gate --stage0` |
| 7 话题延伸 | **仅过预闸的话题**各由一个子任务独立检索:每轮发送一条查询,依据上一轮结果决定下一条,同类触顶或 3 轮硬停 | Agent(子任务并行) |
| 8 汇总与闸门 | 延伸结果合并 + 事实性复核(信源门槛 + 多源印证 + 链接探活)后,**精确复核双关:①是否时政 ②有无回答区没有的增量**——过闸才进写稿,预闸从宽判"是"的在这里被证据打回 | `merge_extension.py`、`verify_ext.py`、`gen_prompts.py --gate` |
| 9 书写自学 | ① 从高赞回答里提炼"书写逻辑"(只提怎么写)→ ② 主 Agent 按奥卡姆剃刀汇编成 `书写skill.md` → ③ 据此成文 | Agent(子任务并行) |
| 10 校验与产出 | 数据完整性校验 → 填表 → 生成网页 → 网页结构校验(一键脚本逐关把关) | `run_pipeline.py` |
| 11 发布 | **人工发布**:过闸稿生成待发帖列(每日上限 3 条,可以少不可以多,附推荐/备选与入列依据);主 Agent 犀利度复核(`--sharp`)后,人在知乎页面粘贴发布,回填 `--mark "<rank>=<回答链接>"`(归属校验,贴错行拒绝) | `publish_queue.py` |

## 快速开始

```bash
ROOT="<你的工作根目录>"
D="2026-09-13"

python scripts/doctor.py --root "$ROOT" --date "$D"

# 抓取(不花 token)
python scripts/run.py            --root "$ROOT" --date "$D" --limit 20 --variants 6
python scripts/question_fetch.py --root "$ROOT" --date "$D" --top 5 --pages 3
python scripts/fulltext.py       --root "$ROOT" --date "$D"

# 生成子任务提示词(交给 Agent 并行执行;各阶段分别生成)
python scripts/gen_prompts.py --root "$ROOT" --date "$D" --combo          # 情绪+书写标注   → ext_search/<D>/{emotion,style}/
python scripts/gen_prompts.py --root "$ROOT" --date "$D" --gate --stage0  # 发布预闸门(检索前) → raw/<D>/publish_verdicts_pre.json
python scripts/gen_prompts.py --root "$ROOT" --date "$D"                  # 话题延伸(仅过预闸) → ext_search/<D>/rank_<n>/
python scripts/gen_prompts.py --root "$ROOT" --date "$D" --gate           # 发布闸门(时政+增量) → raw/<D>/publish_verdicts.json
python scripts/gen_prompts.py --root "$ROOT" --date "$D" --write          # 按书写规范成文  → ext_search/<D>/rank_<n>/draft_<n>.md
# 第 5 步(四维分析)与第 9 步的①(汇编书写规范)由主 Agent 完成

python scripts/merge_emotion.py --root "$ROOT" --date "$D" --compare   # 先看分歧
python scripts/merge_emotion.py --root "$ROOT" --date "$D" --write
python scripts/merge_style.py   --root "$ROOT" --date "$D" --write     # 候选池 → 供奥卡姆取舍
python scripts/merge_extension.py --root "$ROOT" --date "$D"           # 延伸合并 + 事实性复核

# 发布治理:过闸稿 → 待发帖列(人工粘贴发布后回填链接)
python scripts/publish_queue.py --root "$ROOT" --date "$D" --sharp "<rank>=<是否中庸>:<复核依据>"
python scripts/publish_queue.py --root "$ROOT" --date "$D" --mark "<rank>=<回答链接>"

# 交付链:一条命令跑完并逐关校验
python scripts/run_pipeline.py --root "$ROOT" --date "$D" --merge --emotion

# 回归:临时根重跑当日流程,与既有产物逐字节比对(改脚本后跑)
python scripts/regress_pipeline.py --root "$ROOT" --date "$D"
```

各脚本都支持 `--help`。约束、判据与代价最高的坑见 [`skills/zhihu-hot-track/SKILL.md`](skills/zhihu-hot-track/SKILL.md)。

## 目录结构

```
skills/zhihu-hot-track/
├── SKILL.md              # 流程规范:步骤、约束、判据、脚本清单、经验记录
├── ARCHITECTURE.md       # 组成与泛用性分层:29 件组件各属哪层、怎么复用
├── writing_method.md     # 书写方法(通用件):三段分工、剃刀四条、数据假象清单
├── references/           # scripts.md(脚本说明) / pitfalls.md(踩坑清单,全部实测)
└── scripts/
    ├── contract.py          # 数据契约:文件名 / 字段 / 值域 / 结构标记的单一定义处(其余脚本共用)
    ├── zhihu_env.py         # 环境解析:定位知乎 CLI、探测凭证状态(其余脚本共用)
    ├── doctor.py            # 环境与数据体检;--discover 自动发现工作根目录
    ├── check_docs.py        # 组成清单守卫:磁盘组件 ↔ 分层清单 ↔ 脚本表 三方比对(只读)
    ├── run.py               # 取热榜 + 关键词搜索召回
    ├── question_fetch.py    # 按问题取高赞回答(与搜索候选取并集;写入覆盖率;cookie 预检)
    ├── question_add.py      # 单问题追加追踪:把单独搜的问题并入当日交付物
    ├── fulltext.py          # 补全被截断的回答正文
    ├── extract_cookie.py    # 从 playwright storageState 提取单行 Cookie(cookie 失效自愈)
    ├── search_many.py       # 延伸检索:按查询文件逐条执行并落盘
    ├── merge_extension.py   # 合并延伸结果(链式校验 + source 对账)+ 触发事实性复核
    ├── verify_ext.py        # 信源门槛 / 多源印证 / 链接探活(通常由 merge 自动调用)
    ├── fix_chain_source.py  # 机械修复:chains[].source 与原答错配时反查回填
    ├── topic_lib.py         # 话题库维护:收录 / 查重 / 筛选 / 重建 / 清理
    ├── check.py             # 数据完整性校验 + 覆盖率报告
    ├── fill_excel.py        # 写入月度 Excel
    ├── gen_html.py          # 生成分页网页
    ├── verify_html.py       # 网页结构校验(约束四的 13 条断言)
    ├── run_pipeline.py      # 交付链编排:check → Excel → HTML → 校验,失败即停
    ├── regress_pipeline.py  # 回归:临时根重跑当日流程,新 sheet 逐字节比对
    ├── gen_prompts.py       # 生成各类子任务提示词(平台参数在此注入;--combo/--gate/--write)
    ├── merge_emotion.py     # 情绪片段合并 + 与既有判定逐条对账(只暴露分歧)
    ├── merge_style.py       # 书写逻辑候选池:近义折叠 + 维度归类 + 跨批频次
    ├── publish_queue.py     # 发布治理:两阶段闸门 → 待发帖列(每日上限 3);--sharp 复核、--mark 回填
    ├── unfollow_question.py # 可选后续:发布后取消问题关注(幂等)
    ├── prompt_swarm.md      # 话题延伸子任务模板
    ├── prompt_emotion.md    # 情绪标注子任务模板(词表 / 判据 / 边界裁决 / 标定样例)
    ├── prompt_style.md      # 书写逻辑提取子任务模板(铁律 + 改写测试)
    ├── prompt_gate.md       # 发布闸门子任务模板(时政 + 增量双关,检索后精确复核)
    ├── prompt_gate_pre.md   # 发布预闸门子任务模板(检索前粗筛,从宽判是)
    └── prompt_write.md      # 成文子任务模板(不检索,只读规范 + 素材)
```

## 设计约定

- **约定只有一个定义处**:文件名、字段名、值域、网页结构标记全部集中在 `contract.py`,生成方与校验方共用同一常量,避免两侧漂移。
- **样本范围透明**:每问题同时记录「本次收录 N 条 / 该问题的回答总数 M」,并在 Excel 备注、网页卡片与终端校验中呈现。
- **截断如实标注**:正文被截断的回答会标注获取状态,不会以摘要冒充全文。
- **情绪是多元的,且由 Agent 判断**:脚本只校验取值是否属于词表(标签 ≤3 / 强度 1–5 / 指向 6 类),不做语义判断。判据、边界裁决与标定样例写在 `prompt_emotion.md`;子任务标注后与既有判定逐条对账,**只由人复核分歧项**。
- **延伸检索排除名词解释类查询**:查询词需含具体主体、时间、数字或事件名,只保留可核对的事实、案例与机制。
- **文档也有守卫**:`check_docs.py` 只读比对"磁盘组件 ↔ 分层清单 ↔ 脚本表",并扫出"主流程改了、别处旧表述没改"的矛盾。改流程或增删脚本后跑一次。
- **凭证处理**:网页登录 Cookie 保存在工作目录内(`raw/<D>/cookies.txt`),供后续运行复用;当接口返回 403 或出现大量截断时再刷新。需要清理时删除对应文件即可。
- **数据不进仓库**:`raw/`、`ext_search/`、`*.xlsx`、`话题库/`、`书写skill/` 属于运行产物,已在 `.gitignore` 中排除;仓库只包含脚本与文档。
- **对外动作默认关闭**:自动发帖三件套已删(2026-09-21 起,实测存在封号风险,见页首警告);发布 = 人在知乎页面**手动粘贴**待发帖列里的稿子,再用 `publish_queue.py --mark` 回填链接。每日上限写进契约常量 `PUBLISH_MAX_PER_DAY`(=3,可以少不可以多),超限稿自动归入备选位。

## 依赖

- **Python 3.8+**(写入 Excel 需要 `openpyxl`)
- **知乎 CLI**:通过 `zhihu` skill 安装并配置 Access Secret。脚本按 `ZHIHU_CLI` → `ZHIHU_CLI_HOME` → 平台默认目录的顺序定位可执行文件,必要时向 `zhihu` skill 查询实际路径
- **playwright-cli**(npm 包 `@playwright/cli`,可选):用于自动提取网页登录 Cookie(方式 A 零誊写);不可用时按规范 F12 手动复制 Cookie
- **AI Agent**:负责四维分析、话题延伸、情绪标注、书写规范汇编与成文

## 许可

[Apache License 2.0](LICENSE)
