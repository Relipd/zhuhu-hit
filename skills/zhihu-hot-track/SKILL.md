---
name: zhihu-hot-track
description: 仅在用户键入 /zhihu-hot-track 斜杠命令(知乎热榜每日跟进)时使用;本 skill 会话已在进行中、用户继续下达跟进指令时沿用。不因闲聊提及热榜而触发。
---

# 知乎热榜每日跟进

## Step 0: 用途与触发规则(只有斜杠才进行)

本 skill 是**用户主动触发的按需流程**,不是自动后台任务:

- **触发**:仅当用户键入斜杠命令 `/zhihu-hot-track`(可带参数,如 `/zhihu-hot-track 2026-08-09`)时开始执行。
- **不触发**:用户闲聊提及热榜、粘贴知乎内容、讨论分析结论等,即使场景高度吻合,未键入斜杠命令也**不启动**流程;如需执行请引导用户键入 `/zhihu-hot-track`。
- **会话中跟进**:流程进行中用户继续发消息(「继续」「补全」「带 Cookie 重跑」等),属于当前会话的需求跟进(见 Step 1.4),推进对应步骤,不视为重新触发。
- 一次斜杠命令 = 一个流程实例,从 Step 1 依序执行;产物 `raw/<D>/*.json` 跨会话保留,可断点续跑。

## Step 1: 前期准备(依赖 · token · 关键信息 · 需求跟进)

**信息最小原则(本步一切取证的准则)**:本流程只依赖**两项凭证**(开放平台 Access Secret、网页登录 Cookie)和**两个参数**(ROOT、D,均有默认值)。向用户索取的信息仅限缺失项:能自检就不问(已有凭证先验证),能自动获取就不让用户动手(方式 A),缺哪样才问哪样,一概不多要。

### 1.1 依赖与凭证检测(先验证,再动手;缺啥补啥,不缺不问)

**路径泛化原则(2026-08-20 起)**:所有依赖路径一律按下方**探测顺序**定位,不再硬编码单一绝对路径。探测命中即用,全部失败才回退方式 B 或询问用户。

- **Python(环境探测,先按序探测再回退)**:
  1. 环境变量 `ZHIHU_PYTHON`(若设置);
  2. 本机 venv:`<venv>\Scripts\python.exe`(按本机环境填写,实测 3.14.3,含 openpyxl 3.1.5);
  3. 用户级安装:`<python 安装目录>\python.exe`(若存在);
  4. 其他:任何 `python.exe` 且 `python -c "import openpyxl"` 通过。
  裸 `python` 是 WindowsApps 假别名(exit 49/9009),不可用;最终选定路径后跑 `python --version` 与 `import openpyxl` 双确认。
- **知乎 CLI**:`%LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe`(zhihu-cli skill setup 安装到此,实测 0.3.0 已就位);环境变量 `ZHIHU_CLI` 优先。调用一律用绝对 `binary_path`,不依赖 PATH(见 zhihu skill)。
- **凭证定向(信息最小——只认这两样,各有各的出处,互不替代)**:
  - **开放平台 Access Secret(CLI 抓取用)**:出处 = 知乎开放平台控制台(open.zhihu.com → 登录 → 开放平台 → 应用管理,应用凭证含 Client ID 与 Access Secret)。仅当 `zhihu-cli auth status` 为空或调用报 AUTH_INVALID 时才向用户索取,且**只索取 Access Secret 一项**,不涉及 API key、权限位申请等任何多余字段。注入一律用坑 1 的无换行方式(`cmd /c "echo|set /p=<secret>|<cli> auth set --secret-stdin"`);AUTH_INVALID 基本都因换行,而非 Secret 本身无效。此凭证**不适用于网页登录**(坑 12)。配置成功以 `auth status --verify` 返回 `verification=valid` 为准。
  - **网页登录 Cookie(全文解锁用)**:出处 = Step 1.2 方式 A(playwright + Edge 弹窗扫码,自动提取)或兜底方式 B。此凭证**不适用于 CLI 抓取**;与 Access Secret 两套并存、互不替代,检测时分别验证,缺哪个补哪个,齐了就不再多问。
- **脚本**:skill 的 `scripts/` 目录齐全(run.py / **api_fetch.py(优化首选)** / fulltext.py / search_many.py / check.py / fill_excel.py / gen_html.py)。
- **playwright-cli(必要,主要手段,路径探测)**:按序探测环境变量 `PLAYWRIGHT_CLI` → `<本机安装目录>\playwright-cli.js`;命中后调用方式 `Set-Location <仓库目录>; node playwright-cli.js <命令>`;skill 文档装于 `.claude\skills\playwright-cli`。**Cookie 获取的唯一主手段**(Step 1.2 方式 A),仅当它不可用时才回退方式 B(F12 手动)。`open` 一律 `--browser=msedge`——Edge 是唯一验证可用的通道(Chrome 通道 spawn 被 EACCES 拦截,疑似杀软,不要尝试 Chrome)。先 `cd` 到仓库目录再执行,命令生成的快照会写到仓库 `.playwright-cli/`。

### 1.2 网页登录 Cookie(自检优先,不重复询问)

知乎网页 API 对**未登录**请求的长回答只返回截断摘要(`content_need_truncated=true`),全文需网页登录 Cookie;开放平台 Access Secret 不适用于网页登录。不带 Cookie 时 60+ 条回答只能标注「接口摘要」(2026-08-09 实测:不带 Cookie 时 74 条中仅 24 条拿到全文;带 Cookie 后 74/74 解锁为 full)。

**Cookie 时效**:不是一次性凭证,但也不是永久——**同一天内可反复复用**;会过期(实测隔日失效),跨天运行先自检,有效则继续用,不要重复向用户索取。

**自检顺序(不再无条件询问)**:
1. `raw/<D>/cookies.txt` 存在且创建日期为当天 → 直接复用,不询问。
2. 存在但非当天 → 写 5 行临时验证脚本带 Cookie 请求 `api/v4/answers/{id}?include=content`(取任一本日回答 id),`content_need_truncated` 不为 true 即有效 → 复用(验证脚本用完即删);失效则删旧 cookies.txt,进入第 3 步。
3. 文件不存在或已失效 → **这时才向用户索取**,二选一:
   - **方式 A(主手段,playwright-cli + Edge)**:弹 Edge 窗口让用户登录,自动提取 Cookie,零誊写:
     1. `Set-Location <playwright-cli 仓库目录(按 1.1 探测)>; node playwright-cli.js open "https://www.zhihu.com" --browser=msedge --headed --persistent`(弹出 Edge 窗口;profile 已有登录态则直接是已登录页面,无则停在登录页)
     2. **预检**:`node playwright-cli.js --raw cookie-list --domain=zhihu.com`
        - 输出含 `z_c0` → 已登录,跳到第 4 步提取
        - 不含 `z_c0` → 未登录,进入第 3 步
     3. **等待登录完成信号**:告知用户「请在弹出的 Edge 窗口内登录,完成后回复我」。**以用户的通知回传为登录完成的识别信号**——不轮询、不猜测、不设超时;收到用户确认后,重跑第 2 步确认 `z_c0` 已出现
     4. **提取**:`node playwright-cli.js --raw cookie-list --domain=zhihu.com` → 每行 `name=value (domain: …, path: …)`,Agent 取 `name=value` 部分用 `; ` 拼接为 Cookie 串(含 z_c0 等全部,不过滤域名)→ 写 `raw/<D>/cookies.txt`
     5. **收尾**:`node playwright-cli.js close` 关闭浏览器;`--persistent` profile 跨会话保留登录态,下次直接复用,过期才需再走本流程
   - **方式 B(兜底,仅 playwright-cli 不可用时)**:浏览器登录 zhihu.com → F12 → Network → 刷新任意知乎页面 → 点任意请求 → 复制 `Request Headers` 里 `Cookie:` 的**完整值**(从 `_xsrf=` 到末尾,整串)→ 存为 `raw/<D>/cookies.txt`。**整串复制粘贴,勿手工誊写**:z_c0 长串含 `|` 与签名段,誊写会截断致登录态失效(坑 14)。

Cookie 是**敏感凭证**:本次流程全部步骤完成后删除(Step 2.8 收尾);同日再次执行新流程回到第 1 步自检,文件已删则索取一次即可,不属于重复询问。

### 1.3 关键信息取得(与用户确认,取默认值兜底)

| 信息 | 默认值 | 说明 |
|---|---|---|
| 工作根目录 ROOT | 见下方「ROOT 解析」 | 所有脚本 `--root` 参数化 |
| 抓取日期 D | 今天(YYYY-MM-DD) | 斜杠参数可指定过去日期补抓 |
| 抓取范围 | 热榜前 20,每问题最多 10 条回答 | 热点拓展仅前 10(硬约束) |

**ROOT 解析(2026-08-20 起,优先项目级,其次 D 盘)**:
1. **项目级优先**:若当前会话工作区有 `.claude/` 或类似项目目录,且其下有(或已约定)数据子目录,用 `<工作区>/知乎动态跟进`;若已在某项目内运行过本 skill(存在 `<项目>/raw/`),直接沿用该项目级 ROOT;
2. **D 盘回退**:无项目级约定时,默认 `D:\知乎动态跟进`(可按本机习惯调整);
3. 也可在斜杠参数或会话中显式指定任意 ROOT,脚本全部参数化支持。

### 1.4 需求命令跟进

执行全程留意用户指令,**优先级高于默认流程**:

- **斜杠参数**:`/zhihu-hot-track` = 默认今日;`/zhihu-hot-track 2026-08-09` = 指定日期补抓。
- **会话中指令**:「继续」= 接上次断点(检查 `raw/<D>/` 已有产物,跳过已完成步骤);「带 Cookie 重抓」= 重跑补全;「只分析前 N」= 缩小范围;其余指令按意调整步骤/顺序/范围。
- 指令与约束冲突时,以约束一~四为准;要求改变交付物结构(Excel 列、HTML 版式)先与用户确认再动。

## Step 2: 执行流程(现有逻辑)

### 交付物

| 文件 | 说明 |
|---|---|
| `跟进excel-YYYY-MM.xlsx` | 月度 Excel:每个抓取日期一个 sheet(命名 `YYYY-MM-DD`),**最新日期 sheet 插到最前**;一级行=问题(本质信息),二级行=回答(最多 10 条) |
| `知乎热榜跟进-YYYY-MM-DD.html` + 同名目录 | 分页式展示:入口自动跳转 → 索引页(自适应网格卡片)→ 每问题一页(回答折叠扩展 + 四维分析 + 情绪着色 + 前10热点拓展) |
| `raw/YYYY-MM-DD/` | 原始 JSON 存档(hot/search/answers_summary/analysis),可溯源 |
| `话题库/话题库.md` | **跨日期累积话题库**(每次运行必更新):按分类组织,发散搜索前查重、收敛性判断依据 |

Excel 列(16 列):层级 / 问题序号 / 排名 / 问题标题 / 原问题URL / 问题点赞数 / 问题本质 / 回答序号 / 回答内容 / 回答点赞数 / 立场分析 / 解决思路 / 判断逻辑 / 情绪倾向 / 情绪判断(积极·中立·消极)/ 备注

### 主流程(脚本全部在 skill 的 scripts/ 目录,参数化,可复用)

```text
ROOT=<按 1.3 ROOT 解析:项目级优先,否则 D:\知乎动态跟进>
D=2026-08-09                              # 抓取日期

1. 抓取(优化首选):  python scripts/api_fetch.py --root %ROOT% --date %D% --cookie raw/<D>/cookies.txt
            (热榜 URL → question ID → 带 Cookie 直连 api/v4/questions/{id}/answers 拉回答;
             每问题 2 次调用(翻页拉20条候选),20题约40秒,选 top2=最高赞+最多评论(去重补足),
             共 2×20=40 条完整全文,0截断。无 Cookie 时省略 --cookie,尽力直连)
   旧方案(仅作后备): python scripts/run.py --root %ROOT% --date %D% [--limit 20] [--variants 6]
            → raw/<D>/hot.json + search_<n>_v<k>.json + answers_summary.json
   已有前10数据瘦身: python scripts/top2_select.py --root %ROOT% --date %D% [--backup]
            (从已抓全量 answers_summary.json 挑每问题最高赞+最多评论,无需重抓)
2. 补全:   python scripts/fulltext.py --root %ROOT% --date %D% --cookie raw/<D>/cookies.txt
            (api_fetch 已带 Cookie 时通常无需此步;截断检测约束一)
3. 分析:   Agent 亲自读 answers_summary.json, 逐条写四维分析 → analysis.json
            (按 URL 对应!情绪判断必须自行阅读判断, 见约束二/三)
4. 拓展:   **Agent Swarm 并行**: rank 1-10 各派 subagent 独立执行"读回答→发散搜索→产出发散点",
            主 Agent 汇总去重写入 extension.json, 并更新话题库(见"热点拓展板块")
5. 校验:   python scripts/check.py --root %ROOT% --date %D%     (零缺失才继续)
6. 填表:   python scripts/fill_excel.py --root %ROOT% --date %D%
            → 跟进excel-YYYY-MM.xlsx(自动建模板;新日期 sheet 插最前;情绪列下拉 + 截断备注 + 热点拓展 sheet)
7. 出网页: python scripts/gen_html.py --root %ROOT% --date %D%
            → 知乎热榜跟进-<D>.html(原文状态标签 + 前10热点拓展块)
8. 收尾:   删除 raw/<D>/cookies.txt(敏感凭证不留盘);
            若本次带 Cookie 补全过, Agent 重读全文逐条复核 analysis.json(坑 15),
            再重跑 check → fill_excel → gen_html, 并校验 HTML「接口摘要」标签清零(约束一)。

抓取可 --resume 断点续跑;--variants 2-6 控制查询变体数(建议 6)。
CLI 路径:环境变量 ZHIHU_CLI 优先,否则默认 %LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe。
Python 路径:按 1.1 探测(环境变量 ZHIHU_PYTHON → 本机 venv → 用户级安装)。
```

**优化方案说明(2026-08-20 起)**:抓取首选 `api_fetch.py`(API 直拉回答列表),替代 run.py 的 120 次搜索变体。
- 原理:热榜 URL 已含 question ID,带网页 Cookie 直连 `api/v4/questions/{id}/answers?include=content` 直接拿回答列表。
- **top2 经济性(2026-08-20 二次优化)**:每问题拉 2 页 20 条候选,选「最高赞 + 最多评论」各 1 条(去重,同一则补第二),共 2×20=40 条。
  分析成本从 200 条降到 40 条(约 2.7 万字,平均 674 字/条),仍保每题代表声:高赞=主流情绪,高评论=争议焦点。
- 实测:20 题 40 秒,40 条完整全文(0 截断),最高赞/最多评论回答齐全;旧方案 8 分钟仅 ~88 条摘要。
- 前置:必须带网页 Cookie(Step 1.2 方式 A 从 Edge 持久 profile 提取,z_c0 登录态);无 Cookie 直连 api/v4 返回 403(坑 11)。
- 产出 answers_summary.json 与 run.py 完全同格式(兼容 check/fill_excel/gen_html)。
- 注意:只抓前 10 条时选出的「最多评论」不一定是全题真·最多(可能在前 10 之外),务必拉 2 页候选再选。

### 查询变体规则(重要)

搜索接口每 query 只返回 2-3 条本问题回答,且**每次排序结果不同**。必须用 6 个变体查询合并去重才能接近 10 条上限:

- v1 完整标题 / v2 去疑问句尾 / v3 段0+段1 / v4 段1+段2 / v5 段0+段2 / v6 段0+段1截短
- 段落按 `[，,。；;：]` 切分,不足 3 段时用标题截断变体兜底
- 查询间隔 ≥8s,命中限流(`Data` 为 null / 错误码 30001)退避 15s 重试,最多 3 次

### 分析要求

- **原文保留**:回答内容列必须完整摘取原文,不删改。
- **四维分析基于原文**:立场/解决思路/判断逻辑/情绪倾向逐条归纳,不编造;拿不到信息的回答如实标注。
- **情绪判断**:三选一 积极/中立/消极,与情绪倾向描述一致。
- **分析风格(2026-08-20 定)**:少复述事实、多鲜明结论;观点一定要鲜明,敢于有自己的分析判断,不做温吞水的中性综述。
  - 每条 1-2 句核心结论,直指要害(如「本质是 X」),允许带作者个人判断。
  - **关键结论用 `**加粗**` 包裹**(gen_html.py 的 md_bold 自动转 <b>,HTML 中高亮显示)。
  - 情绪倾向/判断同样大胆定性,不回避批评或讽刺。
- **原始链接**:所有问题/回答保留原 URL(Excel 中为超链接)。
- **月度扩展**:新日期直接插入新 sheet 到最前;raw 数据按日期归档,随时可回溯。
- 问题本质列 = 对该问题的主题内容提炼(一句话),回答行该列留空。

## 约束(一~四,不可妥协)

### 约束一:回答内容完整性(截断检测与补全)

搜索接口的 `ContentText` 是**摘要(截断)**,不是全文。抓取后必须执行:

1. **补全**:`python scripts/fulltext.py --root <root> --date <D> [--cookie <cookies.txt>]` 用网页 API(api/v4/answers/{id})补全。**带 `--cookie`(网页登录 Cookie,见 Step 1.2)可解锁全文**;不带则未登录尽力补全。写回 `content_status`:`full`(已补全)/ `truncated`(网页 API 也截断,全文需网页登录 Cookie,开放平台 Access Secret 不适用)/ `summary`(抓取失败,保留摘要)。
2. **禁止静默使用截断文本**:`content_status != full` 的回答,Excel 备注列自动标注「接口摘要,全文需登录网页查看」;HTML 原文折叠标题显示「接口摘要」标签;分析基于摘要时如实说明。
3. 完整回答判断:网页 API 返回含 `content_need_truncated=true` 即为截断;不得把「搜索摘要」当作「完整回答」写入交付物。

### 约束二:情绪分析只能由 Agent 亲自判断(禁止脚本判定)

- **立场/解决思路/判断逻辑/情绪倾向/情绪判断 必须由 Agent 阅读回答原文后自行推理归纳。**
- 禁止:任何脚本、py 程序、情感分析 API、词库/关键词统计、外部模型对情绪做判定。
- 脚本(check.py)只做**值域校验**(三值之一)和**格式校验**,不做任何语义判断。
- 情绪判断与情绪倾向描述必须一致(判断=倾向的量化标签),基于同一段原文推理。

### 约束三:情绪标签化

- 情绪判断是三值标签:**积极 / 中立 / 消极**,每条回答且仅一值。
- Excel:情绪判断列(O 列)已加数据验证下拉(仅三值可选,非法输入报错提示);值域由 check.py 校验。
- HTML:情绪判断以彩色标签展示(🟢积极/⚪中立/🔴消极)。
- 情绪倾向列为文字描述,情绪判断列为标签,两者并存不互相替代。

### 约束四:HTML 页面表现(固定规范,gen_html.py 必须遵守)

页面采用**分页式**「索引 + 每问题一页」结构,任何改动不得破坏:

**文件结构**
- `<root>/知乎热榜跟进-<date>.html` 根入口(meta refresh 自动跳转索引页)+ `<root>/知乎热榜跟进-<date>/` 目录(index.html + q01..q20.html,每问题一页)。
- 索引页:20 个卡片网格 `repeat(auto-fill, minmax(290px, 1fr))` 自适应(1→8 列随视口),每卡=整卡链接进详情页;卡内:排名/扩展标记/标题(2 行截断)/最高赞/回答数/情绪分布迷你条;悬停上浮。
- 详情页:吸顶导航(返回索引 + 上一题/下一题翻页,首末题禁用对应方向)+ 单列宽版(max-width 900px);回答默认折叠为紧凑卡片(`<details>`),summary 含序号/作者/赞/情绪标签/立场摘要,点击展开四维分析表 + 原文;前 10 金色拓展卡片在回答之后。

**风格(anti-slop,源自全局 taste-skill)**
- 禁止 AI 默认审美:紫色渐变、玻璃拟态滥用、Inter+slate-900、三等分卡片。
- 配色:墨蓝渐变头部(#16283f→#1f3a5f)、暖纸底(#f5f3ee)、白色卡片 + 细边框(#e8e4da)、克制阴影(hover 微升)、金色点缀(#b08d2e)。
- 情绪色固定:积极 #2f7d4f / 中立 #8a8a8a / 消极 #c0493a。
- 字体:系统栈(PingFang SC / Microsoft YaHei),详情页正文 ≥13px,卡片标题 ≥14.5px,页面标题 23px。

**交互**
- 全部用原生 `<details>`(无 JS 依赖,可打印可复制);≤720px 隐藏立场摘要列。
- 生成后必须校验:详情页数=热榜条数、每页回答折叠数=回答数、翻页链接 q 前后衔接、根入口跳转路径正确。

## 热点拓展板块(仅热榜前 10,Agent Swarm 并行)

对热榜前 10 名问题做**发散性思维扩展**,同步到 Excel「热点拓展」sheet 与 HTML 问题卡片内的「🧠 热点拓展思考」块。

### 执行方式:Agent Swarm(rank 1-10 并行)

主 Agent 负责调度,subagent 负责单个 rank 的完整发散:

1. **前置准备(主 Agent)**:① 读话题库(见下,了解已有话题与案例,避免跨日期重复);② 为每个 rank 建独立工作目录 `ext_search/<D>/rank_<n>/` 与独立查询文件 `ext_search/<D>/queries_rank_<n>.json`(**文件按 rank 隔离,防并发冲突,坑 16**)。
2. **派发**:rank 1-10 各派一个 subagent(可 2-3 个 agent 各包 2-5 个 rank),每个 subagent 独立执行:
   ① 读该 rank 的回答(answers_summary.json 对应段)→ 判断问题类型(社会事件类/非时效类)→ 按发散逻辑凝练
   ② 动态发散搜索:每轮 **1 条**查询(写自己的查询文件、输出到自己的目录,`python scripts/search_many.py <自己的queries.json> <自己的outdir> --db zhihu`),**每轮检索前先做收敛性判断(见下)**
   ③ 收敛即止,产出该 rank 的 `items`(每条 `type/content/url/note`)+ `thinking`
3. **汇总(主 Agent)**:收集全部 subagent 产出,复核查重、同类型 ≤3、URL 真实性,写入 `raw/<D>/extension.json`,并更新话题库。

### 话题库(跨日期累积,双轨:index.json 机读 + md 人读)

**双轨结构(可复用索引,防人肉翻表)**:
- **`<ROOT>/话题库/index.json`(机读索引,唯一数据源)**:`{"items": [{"date","rank","cat","type","content","url"}]}`;url 归一化(去 `?utm_*` 参数)为**唯一键去重**。
- **`<ROOT>/话题库/话题库.md`(人读展示)**:由 index.json 重建,按分类 heading 组织,条目 `| 日期 | rank | 类型 | 内容要点 | url |`。
- **维护脚本 `scripts/topic_lib.py`(全流程强制使用,禁止手改 md)**:
  - `topic_lib.py update --root <ROOT> --date <D>`:增量收录当日 extension.json(按 url 去重,已收录跳过;extension 中 content 更完整则升级旧条目)→ 重建 md。**extension.json 每个 rank 块必须含 `category` 字段**(主 Agent 汇总写入时按主题标注,如 医疗安全/自然灾害安全/影视行业/消费电子/文学与文化/医疗健康/跨境犯罪与安全/汽车行业/硬件与算力)。
  - `topic_lib.py search --root <ROOT> --url <url>`:URL 查重(收录与否);
  - `topic_lib.py search --root <ROOT> --keyword <词>`:内容/分类关键词命中;
  - `topic_lib.py search --root <ROOT> --cat <分类>`:列出某分类全部条目。
  - `topic_lib.py rebuild --root <ROOT>`:从 index.json 重建 md(修复用)。
- **使用时机(强制)**:
  - **搜索前**:每个 subagent 发散前用 `search --url/--keyword` 查重——已收录主题不重复搜索、不重复收录(用户明令「不需要重复搜索」);
  - **搜索中**:每轮结果 URL 与 index 交叉比对,已收录案例直接跳过;
  - **完成后**:主 Agent 汇总写入 extension.json 后跑 `topic_lib.py update`,新发散点按 url 去重纳入(同一分类下同主题案例 ≤3,超出后新案例只进 `thinking` 不进条目)。
- **跨日期作用**:话题库是断点续跑与多日积累的共享记忆(index.json 可被任何脚本/子任务读取),新日期的发散在前一日基础上继续补新,不重新挖旧土。

### 收敛性判断(每轮检索前必做,命中即跳过本轮)

构造新查询前依次判重,以下任一命中则不执行该查询:

1. **查询主题去重**:新查询词与已执行查询词核心主题重叠(同话题线——如「台风」「观浪」「溺水」已各查过)→ 换角度或停止,不重复搜索;
2. **结果 URL 去重**:上一轮结果的全部 URL 已出现在历史轮次/话题库 → 本轮零新线索;
3. **同类型案例上限**:该 rank 已提炼的发散点中,同一 `type`(案例/人物/链路)已达 **3 条** → 同类不再新增条目(新发现只记入 thinking)。

**收敛停止判据**:连续 2 轮无新线索(零新 URL、零新发散点)即止;或 3 条主线均已覆盖且同类型达上限。与话题库比对产生的「已有案例」也算无新线索轮。

### 发散逻辑(两条线,先判问题类型,再走对应路线)

- **社会事件类**(时效性热点:社会新闻、争议事件、行业动态等):
  ① 参与者的主要情绪与立场:事件各方(当事人/旁观者/利益相关方)当下最主要的情绪与立场分别是什么
  ② 回答者的历史依据与过往案例:回答者立场所依托的历史依据、同类过往案例(如招聘舞弊、AED 事件、AI 幻觉报告)
  ③ 持续发散:多事实、多结论、多推断;少套话、少重复(同一点不二次展开,套话泛语直接丢弃)
- **非时效类**(文学、音乐、教育、哲学等):
  ① 问题出发点:该问题为何被提出,发问动机与背景是什么
  ② 群体与情绪:反映的是哪类社会群体的哪类情绪
  ③ 真实社会议题:当下社会为什么会出现这种情绪,背后可能的真实社会议题是什么

### 发散搜索(动态驱动,禁止预规划)

**不允许**一次性规划完整 queries.json 后批量跑完,必须迭代式进行:

1. 按发散逻辑先构造 **1 条**查询执行(`scripts/search_many.py <queries.json> <outdir> [--db zhihu|global]`,单条:`[{"rank":N, "query":"...", "db":"zhihu|global", "search_db":"all|realtime|static", "filter":"...", "note":"发散点"}]`)
2. **读搜索结果**,从结果中发现新线索(新人物/新案例/新角度)→ 据此调整并生成下一条查询词
3. **由搜索不断调整搜索内容,动态调整**,每轮检索前先做收敛性判断(见上),至收敛即止
4. 每个发散点保留:`type(案例/人物/链路)` + `content(提炼要点)` + `url(来源)` + `note(发散点)`;**同一类型案例不超过 3 个**

### 其他(不变)

- **URL 定向(强制)**:原问题(标题/URL/全部回答)完整保留,发散不改变原问题;每个发散点必须附真实来源 `url`(取自搜索结果中的原文链接),无来源的推断在 content 中标注「推断」,禁止伪造链接。
- **输出** `raw/<day>/extension.json`:
  ```json
  {"1": {"rank":1, "title":"...", "url":"...",
         "items": [{"type":"案例", "content":"...", "url":"...", "note":"..."}],
         "thinking": "发散思考过程(该问题值得延伸的方向与关联)"}}
  ```
- Excel「热点拓展」sheet:日期 | 排名 | 问题标题 | 扩展类型(案例/人物/链路/思考过程)| 扩展内容 | 来源链接 | 备注;最新日期块在最上,跨日期自动累积。
- 范围硬约束:**只处理热榜前 10**,第 11-20 名不扩展(主流程四维分析照常覆盖全部 20)。

## 踩过的坑(1-15,勿重蹈)

1. **PS 5.1 管道换行 → AUTH_INVALID**:`"secret" | zhihu-cli auth set --secret-stdin` 会追加换行导致服务端校验失败(Secret 本身有效)。用 `cmd /c "echo|set /p=<secret>|<cli> auth set --secret-stdin"` 无换行传入。
2. **无 BOM UTF-8 ps1 在 PS 5.1 报语法错误**:官方脚本(run.ps1/setup.ps1)含中文注释,需转存为带 BOM 的 UTF-8 才能被 PS 5.1 解析。
3. **`python -c "..."` 在 PowerShell 传参引号被剥**:任何含引号/中文的 Python 代码都写成脚本文件再运行,不要用 `-c`。
4. **热榜接口无点赞数**:hot 只返回 Title/Url/Summary。问题点赞数列用「该问题最高赞回答的点赞数」近似,备注列注明。
5. **搜索接口无 Question 类型条目**:按问题 id/标题搜都拿不到问题本身的点赞数。
6. **回答排序随合并变化 → 分析必须按 URL 对齐**:6 变体合并后排序与 3 变体不同,按位置取分析会张冠李戴。升级/重建时以 `url.split("?")[0]` 为键匹配旧分析,新增条目单独补齐。
7. **重建脚本非幂等**:重建脚本不能读自己上次的输出(会被错位污染),从原始 v1-v3 文件推导旧顺序,或一次性写全映射。
8. **CLI 输出是带 BOM 的 UTF-8**:python `json.load` 用 `encoding="utf-8-sig"`,否则首行报错。
9. **月份补零**:`跟进excel-2026-8.xlsx` ≠ `跟进excel-2026-08.xlsx`,脚本里 `.zfill(2)`。
10. **次数成本**:1 天快照 = 20 热榜 + 120 搜索 ≈ 140 次调用(每日额度 5000+5000,无压力),耗时约 8 分钟,用后台任务跑。
11. **知乎网页反爬**:直连 www.zhihu.com 页面 403;curl 带默认特征请求 api/v4 返回 10003「请升级客户端」。**python urllib + UA 头直连 api/v4/answers/{id}?include=content 可用**(未登录)。
12. **全文需登录**:未登录时 api/v4 的长回答 content 截断,以 `content_need_truncated=true` 标记;开放平台 Access Secret 不适用于网页登录,截断回答只能如实标注「接口摘要」,不得静默使用。
13. **Cookie 解锁全文(2026-08-09 实测)**:带网页登录 Cookie(`Cookie` + `Referer` 头直连 api/v4/answers/{id})可解锁全部截断回答(74 条 100% 成功)。Cookie 从浏览器 F12→Network 复制完整请求头,存 `raw/<D>/cookies.txt`,`fulltext.py --cookie` 使用。
14. **Cookie 整串复制,勿手工誊写**:z_c0 等长串含 `|` 与签名段,人工誊写会截断(实测把签名段写丢、登录态失效,补全全失败)。复制粘贴后与原文比对;Cookie 是敏感凭证,用完即删;会过期,跨天重跑先自检(Step 1.2),同日复用不重复询问。根治方案:Step 1.2 方式 A 用 playwright-cli 的 `cookie-list --raw` 自动提取,零誊写。
15. **全文补全后分析必须复核**:摘要版四维分析可能与全文有出入(实测 98 条中 1 条情绪判断改判)。补全后 Agent 重读全文逐条核对 analysis.json(约束二),再重跑 check → fill_excel → gen_html,并校验 HTML 中「接口摘要」标签清零。
16. **Swarm 并发文件冲突**:多 subagent 并行发散时,查询文件与输出目录必须按 rank 隔离(`queries_rank_<n>.json` + `ext_search/<D>/rank_<n>/`),禁止共用单个 queries.json / ext_search 根目录——search_many.py 的输出名按 rank 计数(rank_<n>_1.json),同 rank 重跑会覆盖,并发下互相踩踏。
17. **话题库跨日期去重**:新日期发散前必须用 `topic_lib.py search --url/--keyword` 查重,同主题案例已收录的不重复搜索、不重复收录;同一分类同主题案例 ≤3,超出后新案例只进 thinking 不进条目。**只改 index.json,md 由 rebuild 重建,禁止手改 md**(手改会漂移)。
18. **`python -c` 引号陷阱复发**:任何含引号/中文/字典的 Python 代码(即使短)也写脚本文件运行——PS 5.1 会剥引号或转义错误(实测补 category 字段时 `-c` 内联失败)。

## 脚本清单(skill/scripts/,全流程通用)

| 脚本 | 职责 | 关键参数 |
|---|---|---|
| `api_fetch.py` | **优化首选**:热榜 URL→qid→带 Cookie 直连 api/v4/questions/{id}/answers 拉 2 页候选,选 top2=最高赞+最多评论(去重补足,2×20=40 条,全文0截断,与 run.py 同格式输出) | `--root --date --limit --cookie --delay` |
| `top2_select.py` | 从已抓全量 answers_summary.json 瘦身为每题 top2(已有前10数据无需重抓时用;`--backup` 备份原文件) | `--root --date --backup` |
| `run.py` | 热榜 + 变体搜索 + 合并去重(旧方案,api_fetch 不可用时的后备) | `--root --date --limit --variants --resume` |
| `fulltext.py` | 回答全文补全 + 截断检测(content_status 标注;`--cookie` 解锁全文) | `--root --date --delay --force --cookie` |
| `search_many.py` | 批量发散搜索(热点拓展用,queries.json 驱动) | `queries.json outdir --db --delay --count` |
| `check.py` | 完整性校验(分析齐全/情绪值域/URL/内容/状态) | `--root --date` |
| `fill_excel.py` | 填月度 Excel(自动建模板、情绪列下拉、截断备注、热点拓展 sheet) | `--root --date --xlsx` |
| `gen_html.py` | 生成 HTML 展示页(原文状态标签、热点拓展块、`**加粗**`→`<b>` 高亮关键结论) | `--root --date --out` |
| `topic_lib.py` | 话题库双轨维护:update 增量收录(extension→index.json,url 去重)+ search 查重(url/关键词/分类)+ rebuild | `update --root --date` / `search --root --url\|--keyword\|--cat` / `rebuild --root` |

所有脚本路径全参数化(`--root` 默认当前目录),不写死任何绝对路径;日期目录 `raw/<D>/` 自动创建。分析步骤(analysis.json)由 Agent 完成,脚本负责抓取/校验/产出。
