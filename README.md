# zhuhu-hit

把知乎热榜整理成可长期回溯的追踪档案:取当日热榜与回答 → 逐条归纳分析 → 对前 10 个话题做延伸检索 → 产出月度 Excel 与分页网页,并把当日的案例与话题累积进话题库。

## 这是什么

一套在本机运行的知乎热榜跟进流程。仓库里只有两部分内容:

- **流程规范**:[`skills/zhihu-hot-track/SKILL.md`](skills/zhihu-hot-track/SKILL.md) —— 步骤、约束、判据、脚本清单
- **通用脚本**:`skills/zhihu-hot-track/scripts/` —— 抓取、校验、生成,所有路径与日期通过参数传入

脚本负责取数据、校验与排版;**阅读与判断由 AI Agent 完成**(逐条四维分析、话题延伸检索)。

## 产出

每次运行会在工作根目录(下文记为 `ROOT`)生成:

| 产物 | 内容 |
|---|---|
| `跟进excel-YYYY-MM.xlsx` | 月度文件,每个抓取日期一个 sheet;包含问题行与回答行,附四维分析与情绪标签 |
| `知乎热榜跟进-YYYY-MM-DD.html` + 同名目录 | 入口页 → 索引页 → 每问题一页,回答折叠展示,附四维分析与前 10 话题延伸 |
| `raw/YYYY-MM-DD/` | 当日原始数据与中间结果:热榜、回答、分析、延伸、逐轮检索归档 |
| `话题库/` | 跨日期累积的案例索引:`index.json`(机读)+ `话题库.md`(人读),用于后续运行时查重 |

## 流程

| 步骤 | 做什么 | 执行者 |
|---|---|---|
| 0 体检 | 检查运行时、依赖、CLI 与凭证状态、工作根目录 | `doctor.py` |
| 1 取热榜与候选回答 | 取热榜前 20 条;对各问题做关键词搜索,汇成回答候选池 | `run.py` |
| 2 取高赞回答 | 按问题取回答列表并按赞同数保留前 N 条,与候选池取并集去重;同时记录该问题的回答总数与本次覆盖率 | `question_fetch.py` |
| 3 补全全文 | 为内容被截断的回答补齐正文,并标注该回答的获取状态 | `fulltext.py` |
| 4 逐条分析 | 阅读每条回答,归纳立场 / 解决思路 / 判断逻辑 / 情绪倾向,并给出情绪标签 | Agent |
| 5 话题延伸 | 前 10 个话题各由一个子任务独立检索:每轮发送一条查询,依据上一轮结果决定下一条,收敛即止 | Agent(子任务并行) |
| 6 汇总与收录 | 延伸结果经格式与约束校验后合并,并写入话题库 | `merge_extension.py`、`topic_lib.py` |
| 7 校验与产出 | 数据完整性校验 → 填表 → 生成网页 → 网页结构校验 | `check.py`、`fill_excel.py`、`gen_html.py`、`verify_html.py` |

## 快速开始

```bash
ROOT="<你的工作根目录>"
D="2026-09-12"

python scripts/doctor.py        --root "$ROOT"
python scripts/run.py           --root "$ROOT" --date "$D" --limit 20 --variants 6
python scripts/question_fetch.py --root "$ROOT" --date "$D" --top 5 --pages 3
python scripts/fulltext.py      --root "$ROOT" --date "$D"
# 第 4、5 步由 Agent 完成:写 raw/<D>/analysis.json、raw/<D>/extension.json
python scripts/merge_extension.py --root "$ROOT" --date "$D"
python scripts/topic_lib.py     update --root "$ROOT" --date "$D"
python scripts/check.py         --root "$ROOT" --date "$D"
python scripts/fill_excel.py    --root "$ROOT" --date "$D"
python scripts/gen_html.py      --root "$ROOT" --date "$D"
python scripts/verify_html.py   --root "$ROOT" --date "$D"
```

各脚本都支持 `--help`。流程规范、约束与判据见 [`skills/zhihu-hot-track/SKILL.md`](skills/zhihu-hot-track/SKILL.md)。

## 目录结构

```
skills/zhihu-hot-track/
├── SKILL.md            # 流程规范:步骤、约束、判据、脚本清单、经验记录
└── scripts/
    ├── contract.py         # 数据契约:文件名 / 字段 / 值域的单一定义处(其余脚本共用)
    ├── zhihu_env.py        # 环境解析:定位知乎 CLI、探测凭证状态(其余脚本共用)
    ├── doctor.py           # 环境与数据体检;--discover 自动发现工作根目录
    ├── run.py              # 取热榜 + 关键词搜索召回
    ├── question_fetch.py   # 按问题取高赞回答(与搜索候选取并集;写入覆盖率)
    ├── question_add.py     # 单问题追加追踪:把单独搜的问题并入当日交付物
    ├── fulltext.py         # 补全被截断的回答正文
    ├── search_many.py      # 延伸检索:按查询文件逐条执行并落盘
    ├── merge_extension.py  # 合并延伸结果(链式校验 + 按链展平)+ 事实性复核
    ├── verify_ext.py       # 信源门槛 / 多源印证 / 链接探活(通常由 merge 自动调用)
    ├── topic_lib.py        # 话题库维护:收录 / 查重 / 筛选 / 重建 / 清理
    ├── check.py            # 数据完整性校验 + 覆盖率报告
    ├── fill_excel.py       # 写入月度 Excel
    ├── gen_html.py         # 生成分页网页
    ├── verify_html.py      # 网页结构校验
    └── prompt_swarm.md     # 延伸检索 subagent 的提示词模板
```

## 依赖

- **Python 3.8+**(写入 Excel 需要 `openpyxl`)
- **知乎 CLI**:通过 `zhihu` skill 安装并配置 Access Secret。脚本按 `ZHIHU_CLI` → `ZHIHU_CLI_HOME` → 平台默认目录的顺序定位可执行文件,必要时向 `zhihu` skill 查询实际路径
- **playwright-cli**(npm 包 `@playwright/cli`,可选):用于自动提取网页登录 Cookie;不可用时可按规范手动复制
- **AI Agent**:负责第 4、5 步的阅读、归纳与检索

## 设计约定

- **样本范围透明**:每问题同时记录「本次收录 N 条 / 该问题的回答总数 M」,并在 Excel 备注、网页卡片与终端校验中呈现,便于判断样本覆盖范围。
- **截断如实标注**:正文被截断的回答会标注获取状态,不会以摘要冒充全文。
- **情绪标签由 Agent 判断产生**:脚本只校验取值是否属于 积极 / 中立 / 消极,不做语义判断。
- **延伸检索排除名词解释类查询**:查询词需含具体主体、时间、数字或事件名,只保留可核对的事实、案例与机制。
- **凭证处理**:网页登录 Cookie 保存在工作目录内,供后续运行复用;当接口返回 403 或出现大量截断时再刷新。需要清理时删除对应文件即可。
- **数据不进仓库**:`raw/`、`*.xlsx` 已在 `.gitignore` 中排除;仓库只包含脚本与文档。

## 许可

[Apache License 2.0](LICENSE)
