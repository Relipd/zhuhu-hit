---
name: zhihu-hot-track
description: 知乎热榜每日跟进：抓热榜前20 → 多查询变体合并回答 → 逐条四维分析（立场/解决思路/判断逻辑/情绪倾向+情绪判断）→ 输出月度 Excel（按天分 sheet、最新在前）+ HTML 展示页。用户提到知乎热榜跟进、每日热榜记录、热榜分析 Excel/HTML、跟进表格、热榜回答分析时使用。
---

# 知乎热榜每日跟进

数据来源：知乎开放平台（[zhihu skill](../zhihu/SKILL.md)，CLI 在 `%LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe`）。
工作目录：任意目录（`--root` 指定，默认当前目录），存放 raw 数据存档 + 生成脚本 + Excel/HTML 交付物。

## 交付物

| 文件 | 说明 |
|---|---|
| `跟进excel-YYYY-MM.xlsx` | 月度 Excel：每个抓取日期一个 sheet（命名 `YYYY-MM-DD`），**最新日期 sheet 插到最前**；一级行=问题（本质信息），二级行=回答（最多 10 条） |
| `知乎热榜跟进-YYYY-MM-DD.html` + 同名目录 | 分页式展示：入口自动跳转 → 索引页（自适应网格卡片）→ 每问题一页（回答折叠扩展 + 四维分析 + 情绪着色 + 前10热点拓展） |
| `raw/YYYY-MM-DD/` | 原始 JSON 存档（hot/search/answers_summary/analysis），可溯源 |

Excel 列（16 列）：层级 / 问题序号 / 排名 / 问题标题 / 原问题URL / 问题点赞数 / 问题本质 / 回答序号 / 回答内容 / 回答点赞数 / 立场分析 / 解决思路 / 判断逻辑 / 情绪倾向 / 情绪判断（积极·中立·消极）/ 备注

## 流程（脚本全部在 skill 的 scripts/ 目录，参数化，可复用）

```text
ROOT=<你的工作根目录>            # 如 D:\data\zhihu-followup
D=2026-08-08                     # 抓取日期

1. 抓取:   python scripts/run.py --root %ROOT% --date %D% [--limit 20] [--variants 6]
            → raw/<D>/hot.json + search_<n>_v<k>.json + answers_summary.json
2. 补全:   python scripts/fulltext.py --root %ROOT% --date %D%   （全文补全 + 截断检测, 约束一）
3. 分析:   Agent 亲自读 answers_summary.json, 逐条写四维分析 → analysis.json（按 URL 对应！情绪判断必须自行阅读判断, 见约束二/三）
4. 拓展:   Agent 对热榜前 10 逐个"边读取边分析": 发散搜索(search_many.py) → extension.json（见"热点拓展板块"）
5. 校验:   python scripts/check.py --root %ROOT% --date %D%     （零缺失才继续）
6. 填表:   python scripts/fill_excel.py --root %ROOT% --date %D%
            → 跟进excel-YYYY-MM.xlsx（自动建模板；新日期 sheet 插最前；情绪列下拉 + 截断备注 + 热点拓展 sheet）
7. 出网页: python scripts/gen_html.py --root %ROOT% --date %D%
            → 知乎热榜跟进-<D>.html（原文状态标签 + 前10热点拓展块）

抓取可 --resume 断点续跑；--variants 2-6 控制查询变体数（建议 6）。
CLI 路径：环境变量 ZHIHU_CLI 优先，否则默认 %LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe。
```

## 查询变体规则（重要）

搜索接口每 query 只返回 2-3 条本问题回答，且**每次排序结果不同**。必须用 6 个变体查询合并去重才能接近 10 条上限：

- v1 完整标题 / v2 去疑问句尾 / v3 段0+段1 / v4 段1+段2 / v5 段0+段2 / v6 段0+段1截短
- 段落按 `[，,。；;：]` 切分，不足 3 段时用标题截断变体兜底
- 查询间隔 ≥8s，命中限流（`Data` 为 null / 错误码 30001）退避 15s 重试，最多 3 次

## 踩过的坑（勿重蹈）

1. **PS 5.1 管道换行 → AUTH_INVALID**：`"secret" | zhihu-cli auth set --secret-stdin` 会追加换行导致服务端校验失败（Secret 本身有效）。用 `cmd /c "echo|set /p=<secret>|<cli> auth set --secret-stdin"` 无换行传入。
2. **无 BOM UTF-8 ps1 在 PS 5.1 报语法错误**：官方脚本（run.ps1/setup.ps1）含中文注释，需转存为带 BOM 的 UTF-8 才能被 PS 5.1 解析。
3. **`python -c "..."` 在 PowerShell 传参引号被剥**：任何含引号/中文的 Python 代码都写成脚本文件再运行，不要用 `-c`。
4. **热榜接口无点赞数**：hot 只返回 Title/Url/Summary。问题点赞数列用「该问题最高赞回答的点赞数」近似，备注列注明。
5. **搜索接口无 Question 类型条目**：按问题 id/标题搜都拿不到问题本身的点赞数。
6. **回答排序随合并变化 → 分析必须按 URL 对齐**：6 变体合并后排序与 3 变体不同，按位置取分析会张冠李戴。升级/重建时以 `url.split("?")[0]` 为键匹配旧分析，新增条目单独补齐。
7. **重建脚本非幂等**：重建脚本不能读自己上次的输出（会被错位污染），从原始 v1-v3 文件推导旧顺序，或一次性写全映射。
8. **CLI 输出是带 BOM 的 UTF-8**：python `json.load` 用 `encoding="utf-8-sig"`，否则首行报错。
9. **月份补零**：`跟进excel-2026-8.xlsx` ≠ `跟进excel-2026-08.xlsx`，脚本里 `.zfill(2)`。
10. **次数成本**：1 天快照 = 20 热榜 + 120 搜索 ≈ 140 次调用（每日额度 5000+5000，无压力），耗时约 8 分钟，用后台任务跑。
11. **知乎网页反爬**：直连 www.zhihu.com 页面 403；curl 带默认特征请求 api/v4 返回 10003「请升级客户端」。**python urllib + UA 头直连 api/v4/answers/{id}?include=content 可用**（未登录）。
12. **全文需登录**：未登录时 api/v4 的长回答 content 截断，以 `content_need_truncated=true` 标记；开放平台 Access Secret 不适用于网页登录，截断回答只能如实标注「接口摘要」，不得静默使用。

## 分析要求

- **原文保留**：回答内容列必须完整摘取原文，不删改。
- **四维分析基于原文**：立场/解决思路/判断逻辑/情绪倾向逐条归纳，不编造；拿不到信息的回答如实标注。
- **情绪判断**：三选一 积极/中立/消极，与情绪倾向描述一致。
- **原始链接**：所有问题/回答保留原 URL（Excel 中为超链接）。
- **月度扩展**：新日期直接插入新 sheet 到最前；raw 数据按日期归档，随时可回溯。
- 问题本质列 = 对该问题的主题内容提炼（一句话），回答行该列留空。

## 约束一：回答内容完整性（截断检测与补全）

搜索接口的 `ContentText` 是**摘要（截断）**，不是全文。抓取后必须执行：

1. **补全**：`python scripts/fulltext.py --root <root> --date <D>` 用网页公开 API（api/v4/answers/{id}）尽力补全，写回 `content_status`：`full`（已补全）/ `truncated`（网页 API 也截断，全文需网页登录 Cookie，开放平台 Access Secret 不适用）/ `summary`（抓取失败，保留摘要）。
2. **禁止静默使用截断文本**：`content_status != full` 的回答，Excel 备注列自动标注「接口摘要，全文需登录网页查看」；HTML 原文折叠标题显示「接口摘要」标签；分析基于摘要时如实说明。
3. 完整回答判断：网页 API 返回含 `content_need_truncated=true` 即为截断；不得把「搜索摘要」当作「完整回答」写入交付物。

## 约束二：情绪分析只能由 Agent 亲自判断（禁止脚本判定）

- **立场/解决思路/判断逻辑/情绪倾向/情绪判断 必须由 Agent 阅读回答原文后自行推理归纳。**
- 禁止：任何脚本、py 程序、情感分析 API、词库/关键词统计、外部模型对情绪做判定。
- 脚本（check.py）只做**值域校验**（三值之一）和**格式校验**，不做任何语义判断。
- 情绪判断与情绪倾向描述必须一致（判断=倾向的量化标签），基于同一段原文推理。

## 热点拓展板块（仅热榜前 10）

对热榜前 10 名问题做**发散性思维扩展**，同步到 Excel「热点拓展」sheet 与 HTML 问题卡片内的「🧠 热点拓展思考」块。

- **发散维度**（每问题至少覆盖两个方向，随问题性质取舍）：
  - 以往类型案例：同类事件/争议的历史案例（如招聘舞弊、AED 事件、AI 幻觉报告）
  - 人物过去热点：核心人物过往经历/热点（如谢欣-飞书十年、王兴兴-宇树融资链）
  - 事件发展链路：事件从源头到当前的演进脉络（如厄尔尼诺监测-预报-影响传导、飞书定位变迁）
- **发散搜索**：`scripts/search_many.py <queries.json> <ext_search目录> [--db zhihu|global]`
  - queries.json：`[{"rank":1, "query":"...", "db":"zhihu|global", "search_db":"all|realtime|static", "filter":"...", "note":"发散维度"}, ...]`
  - 每个发散点保留：`type(案例/人物/链路)` + `content(提炼要点)` + `url(来源)` + `note(发散点)`
- **边读取边分析（强制）**：对 rank 1→10 逐个处理，**读一个问题的回答 → 立即凝练与四维分析 → 发散搜索 → 立即写入该 rank**，再进入下一个；禁止一次性读取全部回答后统一分析。只保留关键内容和思考过程，不堆砌原文。
- **输出** `raw/<day>/extension.json`：
  ```json
  {"1": {"rank":1, "title":"...", "url":"...",
         "items": [{"type":"案例", "content":"...", "url":"...", "note":"..."}],
         "thinking": "发散思考过程（该问题值得延伸的方向与关联）"}}
  ```
- Excel「热点拓展」sheet：日期 | 排名 | 问题标题 | 扩展类型（案例/人物/链路/思考过程）| 扩展内容 | 来源链接 | 备注；最新日期块在最上，跨日期自动累积。
- 范围硬约束：**只处理热榜前 10**，第 11-20 名不扩展（主流程四维分析照常覆盖全部 20）。

## 约束三：情绪标签化

- 情绪判断是三值标签：**积极 / 中立 / 消极**，每条回答且仅一值。
- Excel：情绪判断列（O 列）已加数据验证下拉（仅三值可选，非法输入报错提示）；值域由 check.py 校验。
- HTML：情绪判断以彩色标签展示（🟢积极/⚪中立/🔴消极）。
- 情绪倾向列为文字描述，情绪判断列为标签，两者并存不互相替代。

## 约束四：HTML 页面表现（固定规范，gen_html.py 必须遵守）

页面采用**分页式**「索引 + 每问题一页」结构，任何改动不得破坏：

**文件结构**
- `<root>/知乎热榜跟进-<date>.html` 根入口（meta refresh 自动跳转索引页）+ `<root>/知乎热榜跟进-<date>/` 目录（index.html + q01..q20.html，每问题一页）。
- 索引页：20 个卡片网格 `repeat(auto-fill, minmax(290px, 1fr))` 自适应（1→8 列随视口），每卡=整卡链接进详情页；卡内：排名/扩展标记/标题（2 行截断）/最高赞/回答数/情绪分布迷你条；悬停上浮。
- 详情页：吸顶导航（返回索引 + 上一题/下一题翻页，首末题禁用对应方向）+ 单列宽版（max-width 900px）；回答默认折叠为紧凑卡片（`<details>`），summary 含序号/作者/赞/情绪标签/立场摘要，点击展开四维分析表 + 原文；前 10 金色拓展卡片在回答之后。

**风格（anti-slop，源自全局 taste-skill）**
- 禁止 AI 默认审美：紫色渐变、玻璃拟态滥用、Inter+slate-900、三等分卡片。
- 配色：墨蓝渐变头部（#16283f→#1f3a5f）、暖纸底（#f5f3ee）、白色卡片 + 细边框（#e8e4da）、克制阴影（hover 微升）、金色点缀（#b08d2e）。
- 情绪色固定：积极 #2f7d4f / 中立 #8a8a8a / 消极 #c0493a。
- 字体：系统栈（PingFang SC / Microsoft YaHei），详情页正文 ≥13px，卡片标题 ≥14.5px，页面标题 23px。

**交互**
- 全部用原生 `<details>`（无 JS 依赖，可打印可复制）；≤720px 隐藏立场摘要列。
- 生成后必须校验：详情页数=热榜条数、每页回答折叠数=回答数、翻页链接 q 前后衔接、根入口跳转路径正确。

## 脚本清单（skill/scripts/，全流程通用）

| 脚本 | 职责 | 关键参数 |
|---|---|---|
| `run.py` | 热榜 + 变体搜索 + 合并去重（数据抓取全流程） | `--root --date --limit --variants --resume` |
| `fulltext.py` | 回答全文补全 + 截断检测（content_status 标注） | `--root --date --delay --force` |
| `search_many.py` | 批量发散搜索（热点拓展用，queries.json 驱动） | `queries.json outdir --db --delay --count` |
| `check.py` | 完整性校验（分析齐全/情绪值域/URL/内容/状态） | `--root --date` |
| `fill_excel.py` | 填月度 Excel（自动建模板、情绪列下拉、截断备注、热点拓展 sheet） | `--root --date --xlsx` |
| `gen_html.py` | 生成 HTML 展示页（原文状态标签、热点拓展块） | `--root --date --out` |

所有脚本路径全参数化（`--root` 默认当前目录），不写死任何绝对路径；日期目录 `raw/<D>/` 自动创建。分析步骤（analysis.json）由 Agent 完成，脚本负责抓取/校验/产出。
