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

## Step 0.5: 本 skill 的组成(能力从哪来 · 哪些能搬走)

本 skill 不是一块铁板,而是**一层套一层的四层结构**;判断"某个东西能不能复用到别的平台"看层次,不看文件。
完整清单(25 个脚本 + 4 个提示词模板 = 29 件,逐个标注所属层与复用方式)见 **[`ARCHITECTURE.md`](ARCHITECTURE.md)**;
其中**书写能力(自我学习 loop)是唯一被单独抽成通用方法文档的一块**,见 **[`writing_method.md`](writing_method.md)**。

| 层 | 内容 | 换平台时的改动量 |
|---|---|---|
| **L1 通用方法论** | 契约层 `contract.py`、编排 `run_pipeline.py`、校验 `check.py` / `verify_html.py` / `verify_ext.py`、学习 loop(3c/3d/4c + `merge_style.py` + `prompt_style/write.md` + `writing_method.md`)、累积库 `topic_lib.py`、发布纪律 `publish_batch.py`、委派的三条纪律 | **0 改动**(校验/编排/学习/委派的方法与平台无关) |
| **L2 平台适配** | `zhihu_env.py`、`run.py` / `question_fetch.py` / `fulltext.py` / `search_many.py` / `question_add.py`、浏览器自动化发布(`publish_draft.py` / `unfollow_question.py` 的选择器)、`prompt_swarm.md` | 只改这一层:换榜单/内容/检索接口与 DOM 选择器 |
| **L3 交付** | `fill_excel.py` / `gen_html.py`(Excel + 分页 HTML 两个载体) | 换载体时替换这两个 |
| **L4 数据产物** | `<ROOT>/raw/<D>/`、`ext_search/<D>/`、`话题库/`、`书写skill/` | 不随代码走,**跨日期累积** |

**四块泛用性最强、优先复用的**(细节见 `ARCHITECTURE.md` §三):

1. **学习 loop** —— 提取(subagent 分批)→ 奥卡姆汇编(主 Agent)→ 应用(subagent 不检索)。
   换任何"要产出风格化文本"的场景都能整套搬走,只改 `{platform}` / `{unit}` / `{platform_notes}` 三个变量
   (由 `gen_prompts.py` 顶部的 `PLATFORM` / `UNIT` / `PLATFORM_NOTES` 注入,模板里不留平台硬编码)。
2. **证据纪律** —— 信源门槛(A/B/C/D, 锚点=数值+制度性)+ 论证链(claim → evidence[relation] → takeaway)。
3. **委派纪律** —— 给权威只读校验器(`--lint`)、不信自述、判定任务必须给评分细则 + 标定样例 + 必填 `why` + 分歧复核。
4. **对外动作纪律** —— 台账为唯一事实源、逐条可验证、"点了"不等于"发出去了"、先小批试水、配额写进契约常量。

> **书写 skill 在本表中的位置**:它既是 **L4 产物**(`<ROOT>/书写skill/书写skill.md`,跨日期累积),
> 也是 **L1 通用件**(方法论文档 `writing_method.md` + 三个脚本/模板)。**规范是数据,方法是代码** ——
> 搬平台时带方法(代码与文档),不带规范(规范在新平台重新学一遍)。

> **清单会腐坏, 所以有守卫**:新增/删除脚本、或改动范围口径(如"拓展从 10 条扩到 20 条")之后,
> **跑一次 `python scripts/check_docs.py`** —— 它只读比对"磁盘组件 ↔ ARCHITECTURE 分层清单 ↔ 本文脚本表",
> 并扫出"主流程改了、别处旧表述没改"的矛盾(2026-09-13 实测: 范围扩到 20 后文档里还留着 6 处"只做前 10",
> 外加 2 个组件从未登记进脚本表)。退出码 1 = 不一致, 逐条打印位置。

## 基础技术栈:与 `zhihu` skill 的依赖与适配

本 skill 的**全部抓取能力**来自基础技术栈 `zhihu` skill(知乎开放平台官方封装):它负责 CLI 的安装、升级与鉴权,并对外暴露统一入口。hot-track 不重复实现、也不修改其内部逻辑,只消费公开约定:

| 消费的基础栈能力 | 基础栈提供的形式 | hot-track 侧用法 |
|---|---|---|
| CLI 定位 | `ZHIHU_CLI` / `ZHIHU_CLI_HOME` / 平台默认目录 / setup 输出的绝对 `binary_path` | 统一由 `scripts/zhihu_env.py` 解析,业务脚本不硬编码路径 |
| 安装与修复 | `scripts/setup.ps1`(Windows)/ `setup.sh`(macOS) | CLI 缺失时,Step 1.1 经用户同意后调用 |
| 状态与鉴权 | `scripts/run.ps1\|run.sh status`(JSON) | `zhihu_env.skill_status()` **宽容读取**:字段缺失降级为 None,不因基础栈演进报错 |
| 业务命令 | `search zhihu\|global`、`hot`、`answer`、`me` | `run.py` / `search_many.py` 经解析出的绝对路径调用 |

**适配原则(基础栈升级时不被连带打断)**:

1. **单一接入点**:所有路径与凭证解析集中在 `scripts/zhihu_env.py`;业务脚本只调 `require_cli()`。基础栈改了目录规则,只改这一处。
2. **路径规则与基础栈严格一致**:`ZHIHU_CLI_HOME` 语义与基础栈完全相同(实测:故意设错该变量时,两侧**一致**判定 CLI 不可用)——修掉了此前"基础栈认为没装、hot-track 却以为装了"的分叉。
3. **对 status 字段宽容**:不假设 `auth.keychain_present` 等字段存在(一律 `.get()` + 降级)。该字段是可选增强,**不是依赖**。
4. **凭证探测双向兜底**:`zhihu_env.keychain_present()` 自行探测系统凭证库(Windows `cmdkey` / macOS `security`)。即使基础栈升级后不再报告凭证状态,仍能判断「装好 CLI 即可复用、无需重新申请 Secret」。
5. **基础栈的本地改动会随升级丢失**:若你曾修补 `zhihu` skill(如加入凭证状态字段),升级会覆盖它。因此 hot-track 的关键判断**不依赖**该修补;升级后先跑 `doctor.py` 确认前提取证仍成立。

**自检命令**:`python scripts/doctor.py [--root <ROOT>] [--date <D>]` 一次性检查运行时、脚本完整性、基础栈(CLI 路径/版本/凭证/skill 版本)、ROOT 与当日数据;`--discover` 自动发现候选 ROOT;`--json` 供机读。

## 脚本间契约:`scripts/contract.py`(改约定的唯一入口)

十余个脚本靠**约定好的文件名与字段**接力(`hot.json` → `answers_summary.json` → `analysis.json` → `extension.json` → Excel/HTML)。这些约定曾以字面量散落在各脚本里(`"hot.json"` 出现在 6 个脚本、情绪三值出现在 4 个、HTML 结构标记出现在 2 个),改一处要改多个文件,漏改**不报错**、只在运行期表现为「文件找不到」或「校验莫名失败」。

现在约定收敛到 `scripts/contract.py`——**唯一定义处**,只放常量与路径函数,无业务逻辑:

| 契约内容 | 常量/函数 | 谁在用 |
|---|---|---|
| 当日产物文件名 | `FILE_HOT/FILE_ANSWERS/FILE_ANALYSIS/FILE_EXTENSION/FILE_COOKIE`、`path_hot/path_answers/path_analysis/path_extension/path_cookie`、`day_dir` | 全部脚本 |
| 榜单结构 | `HOT_ITEMS_PATH`(`hot.json` 里条目数组的位置) | run / check / doctor / question_fetch / verify_html |
| 回答与分析字段 | `ANS_FIELDS`、`ANS_META_FIELDS`、`CONTENT_STATUS`、`ANALYSIS_FIELDS` | check / fill_excel / gen_html |
| 情绪值域 | `EMOTIONS`、`EMOTION_CSS_CLASS` | check(值域校验)/ fill_excel(下拉)/ gen_html(统计与配色) |
| 拓展契约 | `EXT_TYPES`、`EXT_MAX_PER_TYPE`、`EXT_REQUIRED`、`EXT_CONTENT_LEN` | merge_extension / topic_lib |
| 交付物命名 | `REPORT_TITLE`、`XLSX_PREFIX`、`report_name/report_entry/report_pages_dir`、`page_name/page_path`、`xlsx_name/xlsx_path/xlsx_glob`、`lib_dir/lib_index/lib_md` | gen_html / verify_html / fill_excel / topic_lib / doctor |
| HTML 结构标记 | `HTML_ANSWER_DETAIL_CLASS`、`HTML_TEXT_DETAIL_CLASS`、`HTML_SUMMARY_TAG`、`HTML_EXT_MARK` | gen_html(生成)↔ verify_html(校验) |

**两条硬规则**:

1. **新增脚本不得再写上述字面量**,一律 `import contract` 取用(脚本与 `contract.py` 同目录,`import contract` 直接可用;带 `sys.path` 适配层的脚本把 import 放在 `zhihu_env` 旁)。
2. **`raw/<日期>/` 下的文件名不许改**:历史数据依赖 `hot.json` / `answers_summary.json` / `analysis.json` / `extension.json` / `cookies.txt`,改名等于放弃向后兼容,须另写迁移脚本。契约层让改名**只需改一处**,但不代表可以随意改。

**换主题/换平台时改哪里**:换交付物命名或字段约定 → 只改 `contract.py`;换采集平台(不再用知乎开放平台)→ 改 `zhihu_env.py` + `run.py`/`question_fetch.py`/`fulltext.py`,其余脚本(check / fill_excel / gen_html / verify_html / merge_extension / topic_lib)只处理「榜单条目 + 回答 + 分析 + 拓展」这套与平台无关的结构,**不受影响**。

**回归方式(改任何脚本后照此验证)**:在临时 ROOT 里复制 `raw/<D>/` 与 `话题库/` 重跑全链路(`check` → `gen_html` → `verify_html` → `fill_excel` → `topic_lib`),把产出与既有交付物**逐字节比对**(根入口 / 各详情页 / `话题库.md` / Excel 单元格);仅当差异来自数据本身(如既有 HTML 早于 `extension.json` 最后一次写入)才算通过。

## Step 1: 前期准备(依赖 · token · 关键信息 · 需求跟进)

**信息最小原则(本步一切取证的准则)**:本流程只依赖**两项凭证**(开放平台 Access Secret、网页登录 Cookie)和**两个参数**(ROOT、D,均有默认值)。向用户索取的信息仅限缺失项:能自检就不问(已有凭证先验证),能自动获取就不让用户动手(方式 A),缺哪样才问哪样,一概不多要。

### 1.1 依赖与凭证检测(先验证,再动手;缺啥补啥,不缺不问)

**首选自检**:`python scripts/doctor.py` —— 一条命令给出 Python/openpyxl、CLI 路径与版本、凭证可复用性、`zhihu` skill 版本与更新、脚本完整性,并直接附带缺失项的修复命令;确认无 FAIL 再往下走。

- **Python**:一律用 `D:\claude code\python\python.exe`(3.12.8,含 openpyxl)。裸 `python` 是 WindowsApps 假别名(exit 49/9009),不可用。
- **知乎 CLI**:`%LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe`;环境变量 `ZHIHU_CLI` 优先。**先 `Test-Path` 验证文件存在**,不存在时不要硬闯:
  1. 跑 `zhihu` skill 的 `scripts/run.ps1 status`。若返回 `installed:false` 但 `auth.keychain_present:true`,说明**系统凭证库里的 Access Secret 仍然有效**(CLI 二进制与凭证库是两套独立存储),安装后直接复用,**不要向用户索要新 Secret**;
  2. 经用户同意后运行 `zhihu` skill 的 `scripts/setup.ps1` 安装,记下 stdout JSON 里的 `binary_path`;
  3. 安装后 `auth status --verify` 确认 `verification=valid`(坑 19)。
- **凭证定向(信息最小——只认这两样,各有各的出处,互不替代)**:
  - **开放平台 Access Secret(CLI 抓取用)**:出处 = 知乎开放平台控制台(open.zhihu.com → 登录 → 开放平台 → 应用管理,应用凭证含 Client ID 与 Access Secret)。仅当 `zhihu-cli auth list` 为空或调用报 AUTH_INVALID 时才向用户索取,且**只索取 Access Secret 一项**,不涉及 API key、权限位申请等任何多余字段。注入一律用坑 1 的无换行方式(`cmd /c "echo|set /p=<secret>|<cli> auth set --secret-stdin"`);AUTH_INVALID 基本都因换行,而非 Secret 本身无效。此凭证**不适用于网页登录**(坑 12)。
  - **网页登录 Cookie(全文解锁用)**:出处 = Step 1.2 方式 A(playwright + Edge 弹窗扫码,自动提取)或兜底方式 B。此凭证**不适用于 CLI 抓取**;与 Access Secret 两套并存、互不替代,检测时分别验证,缺哪个补哪个,齐了就不再多问。
- **脚本**:skill 的 `scripts/` 目录齐全(contract.py / run.py / fulltext.py / search_many.py / check.py / merge_extension.py / verify_html.py / fill_excel.py / gen_html.py / topic_lib.py / question_fetch.py / doctor.py / zhihu_env.py)。
- **playwright-cli(必要,主要手段)**:仓库在 `D:\claude code\playwright-cli`,调用方式 `Set-Location D:\claude code\playwright-cli; node playwright-cli.js <命令>`;skill 文档已装于 `.claude\skills\playwright-cli`。**Cookie 获取的唯一主手段**(Step 1.2 方式 A),仅当它不可用时才回退方式 B(F12 手动)。`open` 一律 `--browser=msedge`——Edge 是唯一验证可用的通道(本机 Chrome 通道 spawn 被 EACCES 拦截,疑似杀软,不要尝试 Chrome)。先 `cd` 到仓库目录再执行,命令生成的快照会写到仓库 `.playwright-cli/`。

### 1.2 网页登录 Cookie(懒加载:默认复用,失败才获取)

知乎网页 API 对**未登录**请求的长回答只返回截断摘要(`content_need_truncated=true`),全文需网页登录 Cookie;开放平台 Access Secret 不适用于网页登录。不带 Cookie 时大量回答只能标注「接口摘要」(2026-08-09 实测:74 条中仅 24 条拿到全文;带 Cookie 后 74/74 全量解锁)。

**处理策略(用户 2026-09-11 明确指示:不反复测试、不每次删除——只在真正失败后才动它)**:

1. **有 `raw/<D>/cookies.txt` → 直接复用,不验证、不删除、不询问。** 跨天/跨会话续跑也一样:先用起来,让流程自己暴露问题。不验证的代价可控——失效时会显式表现为下面第 3 步的失败信号。
2. **没有 cookies.txt → 先按"无 Cookie"正常跑**(抓取与补全照常执行)。这不是错误状态,只是拿不到全文。
3. **只有出现失败信号才去获取/刷新 Cookie**,判定标准(任一命中):
   - `fulltext.py` 报告的 `truncated + summary` 占比 **> 20%**(大部分回答退化);
   - 任何网页接口返回 **403 / 要求登录**;
   - 用户明确要求「带 Cookie 重抓」。
   获取成功后**只重跑失败的那一步**(通常就是 `fulltext.py`),不必重跑抓取。
4. **获取后长期保留**。下次运行乃至跨天都优先复用同一份;只有确认失效才覆盖刷新。
   - 清理方式(**仅在用户明确要求时**执行):`Remove-Item raw/<D>/cookies.txt`。

**方式 A(主手段,playwright-cli + Edge —— 零誊写)**:`--persistent` profile 通常已保留登录态(实测 2026-09-11:打开即为已登录页,预检直接通过、用户零操作):
1. `Set-Location D:\claude code\playwright-cli; node playwright-cli.js open "https://www.zhihu.com" --browser=msedge --headed --persistent`
2. **预检**:`node playwright-cli.js --raw cookie-list --domain=zhihu.com` → 含 `z_c0` 即已登录,直接跳到第 4 步
3. **未登录时**:告知用户「请在 Edge 窗口内登录,完成后回复我」——**以用户回传为信号**,不轮询、不猜测、不设超时;收到确认后重跑第 2 步
4. **提取**:把输出每行取 `name=value` 用 `; ` 拼接(**含 z_c0 等全部,不过滤域名**)→ 写 `raw/<D>/cookies.txt`
5. **收尾**:`node playwright-cli.js close`

**方式 B(兜底,仅 playwright-cli 不可用时)**:浏览器登录 zhihu.com → F12 → Network → 刷新任意页面 → 复制 `Request Headers` 里 `Cookie:` 的**完整值**(从 `_xsrf=` 到末尾)→ 存为 `raw/<D>/cookies.txt`。**整串复制粘贴,勿手工誊写**(z_c0 含 `|` 与签名段,誊写会截断致登录态失效,坑 14)。

**写入注意事项**:文件必须是 **UTF-8 无 BOM**。PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写入 BOM,使 Cookie 串首字符变成 `\ufeff`,放进 HTTP header 时报 latin-1 编码错(坑 25);读取端一律用 `encoding="utf-8-sig"` 兼容。

**风险提示**:Cookie 长期留在 `raw/<D>/cookies.txt`,属敏感凭证。在共享设备、或需要把目录交付他人时,按第 4 步的清理命令显式删除。

### 1.3 关键信息取得(每次执行都重新确认,不依赖会话记忆)

**三条强制动作(跨天续接的会话里旧记忆会整体失效,见坑 23)**:

1. **重新取当前日期**:`Get-Date -Format "yyyy-MM-dd"`(Windows)或 `date +%F`。**不要沿用会话早些时候得到的日期**。
2. **ROOT 自动发现**(按优先级):① 用户在本次消息里给的路径 → ② 运行 `python scripts/doctor.py --discover`,它扫描含 `话题库/index.json` 或 `跟进excel-*.xlsx` 的目录并列出候选(可用环境变量 `ZHIHU_TRACK_ROOTS` 限定搜索范围,分号分隔)→ ③ 都没找到才用兜底默认值。**发现多个候选时必须向用户确认**,不要自行挑选。
3. **检查 `raw/<D>/` 是否已存在**:存在则先报告已有产物(hot.json / answers_summary.json / analysis.json / extension.json)并询问「补抓 / 覆盖 / 复用断点」,不要静默覆盖。

| 信息 | 默认值 | 说明 |
|---|---|---|
| 工作根目录 ROOT | 自动发现(兜底 `D:\claude code\知乎动态跟进`) | 任意目录均可,所有脚本 `--root` 参数化 |
| 抓取日期 D | **重新取当前日期** | 斜杠参数可指定过去日期补抓 |
| 抓取范围 | 热榜前 20,每问题最多 10 条回答 | 接口上限:热榜 `--limit` ≤30、`search zhihu --count` ≤10;20 即当前上限(拓展与分析都做全部 20 条),要更大分析面可用 30 |

### 1.4 需求命令跟进

执行全程留意用户指令,**优先级高于默认流程**:

- **斜杠参数**:`/zhihu-hot-track` = 默认今日;`/zhihu-hot-track 2026-08-09` = 指定日期补抓。
- **会话中指令**:「继续」= 接上次断点(检查 `raw/<D>/` 已有产物,跳过已完成步骤);「带 Cookie 重抓」= 重跑补全;「只分析前 N」= 缩小范围;其余指令按意调整步骤/顺序/范围。
- 指令与约束冲突时,以约束一~四为准;要求改变交付物结构(Excel 列、HTML 版式)先与用户确认再动。

### 1.5 需求变更的成本透明(强制,用户 2026-09-12 要求)

用户提出任何新需求(优化/新增/改流程/补字段)时,**先报增量成本,再动手**。不要"边做边报",也不要只报总数。固定四段:

| 项 | 说明 | 估算锚点(实测) |
|---|---|---|
| 一次性·实现 | 写代码 + 改文档 | 中文脚本约 **20–25 token/行**;实测 430 行脚本 ≈ 9k token;读 68k 字符渲染文本 ≈ 30k token |
| 一次性·数据回填 | 给**已产出**数据补字段(不重跑 Swarm 时的人工判定) | 读一条目(content+note+url 摘要)≈ 50 token,判定并写一行 JSON ≈ 25 token |
| 每次运行·长期增量 | 每天新增的固定/线性成本 | 脚本输出每 ~10 行 ≈ 300 token;subagent 每条证据多一个字段 ≈ 20 token |
| 相对基线占比 | 分母 = 当日全量运行(上次实测 **≈39 万 token**:含 Agent 逐条四维分析 + Swarm;2026-09-13 起范围从 10 扩到 20 条、并新增书写 loop,**当前全量约 50–62 万 token**) | |

**三个最大成本杠杆(按大小排序,报增量时必须分别回答)**:

1. **是否重跑 Swarm(拓展)** —— 单 rank 约 **1.5–2.5 万 token**(读 5 条回答 + 3–6 轮检索 + 写链);
   **20 rank 全量 = 30–50 万 token**。若可人工回填就不要重跑,写明「不重跑,改人工回填」与差额。
2. **是否重跑书写 loop(3c/3d/4c)** —— 提取端 4 批 ≈ **4.8 万 token**;书写端 20 个 subagent ≈ **10 万 token**;
   合计 **≈+12.4 万/天**(其中约 2.4 万是从拓展端省下的——写稿职责已移出拓展 subagent)。
   **规范一旦稳定,提取端不必每天全跑**(可隔日/换语域时再跑),这是最容易省的一块。
3. **是否重跑抓取/补全(带 Cookie)** —— 不花 token(HTTP),但会触发后续分析与校验重跑。

**报告示例(2026-09-12 实测口径)**:
> 一次性实现 7k + 数据回填 5k = **约 13k token**;此后每天 +2.5k(占基线 0.6%)。**不重跑 Swarm**(重跑需 +30–50 万)。

## Step 2: 执行流程(现有逻辑)

### 交付物

| 文件 | 说明 |
|---|---|
| `跟进excel-YYYY-MM.xlsx` | 月度 Excel:每个抓取日期一个 sheet(命名 `YYYY-MM-DD`),**最新日期 sheet 插到最前**;一级行=问题(本质信息),二级行=回答(最多 10 条) |
| `知乎热榜跟进-YYYY-MM-DD.html` + 同名目录 | 分页式展示:入口自动跳转 → 索引页(自适应网格卡片)→ 每问题一页(回答折叠扩展 + 四维分析 + 多元化情绪 + 全部条目的热点拓展 + ✍️拟答参考) |
| `raw/YYYY-MM-DD/` | 原始 JSON 存档(hot/search/answers_summary/analysis/extension),可溯源 |
| `raw/YYYY-MM-DD/answers_web_preview.json` | (可选)问题维度抓取的对比预览,用于核对覆盖率变化;不影响交付物一致性 |
| `ext_search/YYYY-MM-DD/rank_<n>/draft_<n>.md` | **拟答参考稿**(2026-09-13 起由**独立书写 subagent** 产出):≤500 字、无链接、纯路人视角、观点鲜明的成文回答;同步进 Excel「拟答参考」sheet 与 HTML 每问页底部 |
| `书写skill/书写skill.md` | **书写 skill(自我学习 loop 的产物, 跨日期累积)**:由提取 subagent 从高赞回答里提炼"书写逻辑与语言习惯"(**不含具体内容**), 主 Agent 按奥卡姆剃刀汇编。书写 subagent 按它成文;越用越准。原始提取片段留档在 `ext_search/<D>/style/style_batch_*.json`, 候选池 `ext_search/<D>/style_merge.json` |
| `话题库/话题库.md` | **跨日期累积话题库**(每次运行必更新):按分类组织,发散搜索前查重、收敛性判断依据 |

Excel 列(18 列,2026-09-13 起):层级 / 问题序号 / 排名 / 问题标题 / 原问题URL / 问题点赞数 / 问题本质 / 回答序号 / 回答内容 / 回答点赞数 / 立场分析 / 解决思路 / 判断逻辑 / 情绪倾向 / **情绪标签** / **情绪强度** / **情绪指向** / 备注
(旧日期 sheet 仍是 16 列、以「情绪判断(积极·中立·消极)」占 1 列 —— **每天一个 sheet、各自表头,故新旧列数并存不冲突**;
历史 sheet 不回改。)

### 主流程(脚本全部在 skill 的 scripts/ 目录,参数化,可复用)

```text
ROOT=D:\claude code\知乎动态跟进          # 工作根目录(任意目录均可)
D=2026-08-09                              # 抓取日期

0. 体检:   python scripts/doctor.py --root %ROOT% --date %D%    (前置条件一条命令看清; 有 FAIL 先修再跑)
1. 抓取:   python scripts/run.py --root %ROOT% --date %D% [--limit 20] [--variants 6]
            → raw/<D>/hot.json + search_<n>_v<k>.json + answers_summary.json(关键词搜索召回, 作兜底)
1b.问题维度: python scripts/question_fetch.py --root %ROOT% --date %D% --top 5 --pages 3
            → 重写 answers_summary.json: 每问题取「问题维度网页接口(按赞) ∪ 上一步搜索召回」**并集**前 5,
              并写入 total_answers / coverage / source(覆盖率标注的依据)
            (需 Cookie; 无 Cookie 时自动降级为搜索数据, 标 source=search_fallback)
2. 补全:   python scripts/fulltext.py --root %ROOT% --date %D% [--cookie raw/<D>/cookies.txt]
            (约束一。有 cookies.txt 就带上, 不必先验证其有效性; 没有就先不带跑,
             若 truncated+summary 占比 >20% 再按 Step 1.2 获取 Cookie 并只重跑本步)
3. 分析:   四维主体(立场/解决思路/判断逻辑/情绪倾向)由 **Agent 亲自**读 answers_summary.json 逐条写 → analysis.json
            (四维主体按 URL 对应, 见约束二)
3b.情绪(2026-09-13 起下放): python scripts/gen_prompts.py --root %ROOT% --date %D% --ranks 1-20 --emotion --per 5
            → 每批 5 个 rank 派一个 subagent(模板 scripts/prompt_emotion.md: 词表/判据/四条边界裁决/标定样例/必填 why)
            → subagent 写 ext_search/<D>/emotion/emotion_batch_<tag>.json
            → python scripts/merge_emotion.py --root %ROOT% --date %D% --compare   (先看分歧)
            → **主 Agent 只复核分歧项**(实测与主 Agent 完全一致率仅 20%, 分歧集中在 讽刺vs调侃/强度/指向/失望·无奈·忧虑)
            → python scripts/merge_emotion.py --root %ROOT% --date %D% --write     (确认后写入)
3c.书写逻辑提取(2026-09-13 新增, **自我学习 loop 的学习端**):
            python scripts/gen_prompts.py --root %ROOT% --date %D% --ranks 1-20 --style --per 5
            → 每批 5 个 rank 派一个 subagent(模板 scripts/prompt_style.md)
            → **只提炼"怎么写", 完全不涉及"写了什么"**: 开头方式/结构推进/句长节奏/人称口吻/情绪表达/
              论证顺序/结尾方式/标点格式/词汇习惯/避免的写法(10 个固定维度, 见 contract.STYLE_DIMS)
            → 每条规律必须能套到无关话题上(改写测试), 空话(\"语言生动\")不算, 要可操作的写法特征
            → subagent 写 ext_search/<D>/style/style_batch_<tag>.json
3d.汇编书写 skill(主 Agent, **奥卡姆剃刀**):
            python scripts/merge_style.py --root %ROOT% --date %D% --write
            → 折叠近义重复(同维度相似度≥0.62 合一条)、按维度归类、给出跨批频次
            → 主 Agent 依频次取舍: **保留普遍做法与约束力最强的"避免"项, 删掉低频同义与空泛项**,
              汇编成 <ROOT>/书写skill/书写skill.md(**跨日期累积**, 与话题库同构: 越用越准)
4. 拓展:   **Agent Swarm 并行**: **rank 1-20 全部**各派 subagent: python scripts/gen_prompts.py --ranks 1-20
            → 每个 subagent 读回答 → 迭代发散搜索 → **只产出 chains/dropped/thinking**(不再顺带写稿, 见 Step 4c)
            (schema 见"热点拓展板块"; 收尾必须跑 merge_extension.py --ranks <n> --lint)
4b.汇总+复核: python scripts/merge_extension.py --root %ROOT% --date %D%
            → ① 链式强校验(claim/evidence/takeaway + relation 值域 + type 值域 + 同类型≤3 + URL + entities
               + **chains[].source 与原答对账**)
              并按链展平 items → 写 raw/<D>/extension.json
            → ② **紧接着自动做事实性复核**(--no-verify 跳过; --no-links 不联网):
              信源门槛兜底(A事实性/B待定/C不采信/D观点, 锚点=数值+制度性) + 多源印证(归档池 + 同源折叠)
              + 链接探活(5xx/超时退避重试) + 归档核对; 结果写回 extension.json 并另出 raw/<D>/ext_verify.json
            (复核已与汇总合并, 不需要单独跑; verify_ext.py 仍保留, 供单独补跑/机读)
4c.回答书写(2026-09-13 新增, **学习端的用武之地**): python scripts/gen_prompts.py --ranks 1-20 --write
            → 每个 rank 派一个**书写 subagent**(模板 scripts/prompt_write.md): **不检索**,
              读 <ROOT>/书写skill/书写skill.md + 本 rank 的 rank_<n>.json → 写 draft_<n>.md
            (≤500 字 / 正文零链接 / 纯路人视角不立人设 / 允许暴论 / 讲清楚优先于精简 / 例子≤2-3 个)
5. 出交付: python scripts/run_pipeline.py --root %ROOT% --date %D% [--merge] [--emotion]
            → **一键跑完并逐关校验**: 情绪合并(可选) → 汇总(可选) → check → fill_excel → gen_html → verify_html
              失败即停并报是哪一关(取代手敲四条命令; 实测手敲容易漏步, 如改了数据忘了重出 Excel/HTML)
6. 收尾:   cookies.txt **保留复用, 不删除**(见 Step 1.2; 仅用户明确要求时才清理);
            清理 ext_search/<D>/ 下 subagent 遗留的临时脚本与中间文件(坑 22);
            若本次补全过(带 Cookie), Agent 重读全文逐条复核 analysis.json(坑 15), 再跑一次 run_pipeline。
7. 可选·发布(2026-09-13 新增, **需用户逐条明确授权, 不接默认流程**; **每天只发前 15 条**):
            python scripts/publish_batch.py --root %ROOT% --date %D% [--status]
            → 默认只发前 contract.PUBLISH_TOP_N(=15) 条, 其余标 draft_only; 台账 raw/<D>/publish_ledger.json
            → 单条工具: python scripts/publish_draft.py --draft <draft_n.md> --out <js> [--publish]
            → 详见「本流程不发布」一节的发布策略与 7 条纪律
8. 可选·取消关注(发布后清尾): python scripts/unfollow_question.py --out <unfollow.js>
            → 对每个已发布的问题页跑一次(发布回答会自动关注问题, 这是平台行为)。
              幂等: 已是「关注问题」则跳过。

抓取可 --resume 断点续跑;--variants 2-6 控制查询变体数(建议 6)。
CLI 路径:环境变量 ZHIHU_CLI 优先,否则默认 %LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe(缺失时按 Step 1.1 自愈)。
```

**轻量档(非深度需求可选,调用量约为标准档 1/4、耗时约 2-3 分钟)**:跳过 Step 4/4b,不跑 Swarm——
`run.py --limit 10 --variants 3` → fulltext → 分析 → check → fill_excel → gen_html → verify_html。
无 extension.json 时 fill_excel / gen_html 会自动省略热点拓展块,verify_html 的拓展范围校验也按实际产物判定。

### 单问题追加追踪(可选入口,2026-09-12 新增)

用户可能只想深挖**某一个**问题(不在热榜里也行)。入口:

```text
python scripts/question_add.py --root %ROOT% --date %D% --url <问题/回答/专栏链接> [--top 5] [--pages 3] [--rank N]
```

它做四件事:① 解析链接 → id 与标题(**标题取自 answers 接口每条结果自带的 `question.title`** —— 单问题元数据接口 `api/v4/questions/{qid}` 实测 403);② 分配 rank = **当日现有最大值 + 1**(榜单 20 条时即 21、22…,可用 `--rank` 指定);③ 抓取该问题高赞回答并**并入 `answers_summary.json`**(条目标 `extra: true`);④ 登记 `raw/<D>/extra_questions.json`。**回答链接会自动折算到它所属的问题**(追踪问题才有拓展价值)。

**顺手做掉的三件事(2026-09-12 实测摩擦)**:
- **链接自动规范化**:入参先过 `contract.canon_url()`(去掉 `?share_code=…&utm_psn=…` 等跟踪参数),避免跟踪串一路带进 Excel/HTML;话题库去重键与本函数同源;
- **自动生成派发提示词**:用 `scripts/prompt_swarm.md` 模板填好 rank/标题/URL/受控分类,写到 `ext_search/<D>/rank_<N>/PROMPT.md`,直接拿去派 subagent —— 免去每次手写约 1.2k token 的提示词(`--emit-prompt <path>` 可指定输出位置);
- **跨日期重复追踪检查**:扫其他日期的 `extra_questions.json`,同一问题已追踪过会告警(避免白跑一次 Swarm);确认要重复追踪加 `--no-cross-day-check`。

**编号与聚合规则**:
- **rank 21+ 追加**,不另开 id 空间 —— `analysis.json` / `extension.json` / `ext_search/<D>/rank_<N>/` / Excel 排名列 / HTML `q<N>.html` 全部照旧;Excel 备注会标「追加追踪(非榜单条目)」以示区别;
- **不需要当天先跑榜单**:`hot.json` 是**可选输入**(缺失=空列表);"条目数的唯一来源"是 `answers_summary.json`(`verify_html` 的页数/卡片数基准已从 hot 改为它);
- **不重跑已有 rank**:`merge_extension` 在 `--ranks` 为子集时默认保留其他 rank 块,所以追加第 21 条不动前 20 条。

**拓展范围规则(与榜单不同)**:
- 榜单:**前 20 全部**跑 Swarm(2026-09-13 起;原为前 10);
- **追加问题:默认跑 Swarm**(单 rank,用户 2026-09-12 指定)。
因此 `verify_html.py` 的「拓展块覆盖范围」按**实际产物**判定:榜单条目须与 `extension.json` 的 rank 集合一致,
追加条目(rank 21+)有拓展块不算违规。

**追加后的完整链路**:
```text
question_add ─→ Agent 写四维分析(analysis.json 的该 rank)
             ─→ 建 ext_search/<D>/rank_<N>/ 并派 1 个 subagent 产 chains
             ─→ merge_extension(汇总 + 自动复核)
             ─→ topic_lib update → fill_excel → gen_html → verify_html
```

**成本提示**:抓取不花 token(HTTP),但**默认 Swarm 约 1.6–2.7 万 token/问题**。若当天还没做榜单,整天的交付物就只有这一条,同样能正常出 Excel/HTML 并通过校验(实测输出:`条目 1 条，其中追加追踪 1 条`、10/10 通过)。

### 数据源与覆盖度(2026-09-11 起)

| 数据源 | 作用 | 局限(实测) |
|---|---|---|
| `search zhihu`(`run.py`) | 关键词召回, 作兜底 | **全站检索**:召回取决于回答正文是否命中查询词, 每次排序还不同; 上限 10 条/次。实测某问题只覆盖 5/303 |
| 问题维度网页接口(`question_fetch.py`) | 按赞取该问题最热 N 条 | 需 Cookie;`order_by=voteup` 实测不严格排序;单页 20 条未必含全部最热 |
| **并集(默认)** | 两者合并去重后按赞排序取前 N | 实测 rank1 最高赞 51 → **780**、rank2 14 → **870**、rank19 155 → **853**, 并找回 rank4 的 17503 |

**覆盖度必须标注(不得静默)**:`question_fetch.py` 写入 `total_answers` 与 `coverage`;`fill_excel.py` 写进问题行备注列;`gen_html.py` 写进索引卡片与详情页 badge;`check.py` 在终端报告全局覆盖率。目的:**不让读者把「抓到 5 条」误读成「该问题只有 5 条」**。

### 查询变体规则(重要)

搜索接口每 query 只返回 2-3 条本问题回答,且**每次排序结果不同**。必须用 6 个变体查询合并去重才能接近 10 条上限:

- v1 完整标题 / v2 去疑问句尾 / v3 段0+段1 / v4 段1+段2 / v5 段0+段2 / v6 段0+段1截短
- 段落按 `[，,。；;：]` 切分,不足 3 段时用标题截断变体兜底
- 查询间隔 ≥8s,命中限流(`Data` 为 null / 错误码 30001)退避 15s 重试,最多 3 次

### 分析要求

- **原文保留**:回答内容列必须完整摘取原文,不删改。
- **四维分析基于原文**:立场/解决思路/判断逻辑/情绪倾向逐条归纳,不编造;拿不到信息的回答如实标注。
- **情绪判断(2026-09-13 起为多元化模型)**:每条回答给 `emotion_tags`(1-3 个受控标签)+ `emotion_intensity`(1-5)
  + `emotion_target`(6 类指向),值域与判据见「约束三」。
  **开工前先把这段判据贴出来**——此前只要求"与描述一致"而没给判据,导致我边做边改口径、跨批次漂移,
  同一个 100 条数据集里的标签不完全可比。固定口径(先判标签,再判强度与指向):
  - **标签看行文里真实存在的情绪载体**,不是看立场对错:冷静举证 = 审慎;举证中夹讥刺 = 审慎+讽刺;
    通篇反讽或骂战 = 讽刺/愤怒;纯玩梗 = 调侃;温情怀念 = 共情/悲悯/认同;拥抱变化或为某方叫好 = 振奋/认同;
    冷眼旁观、无所谓 = 漠然;讲到他人苦难而生怜悯 = 悲悯。
  - **强度看情绪浓度**:冷静举证 1-2;有明确情绪但不激烈 3;通篇激愤/狂欢/痛心 4-5。
  - **指向看情绪冲着谁**(当事人/涉事机构/制度环境/舆论与媒体/自身经历/泛化社会),别一律填「泛化社会」。
  - 标完后自查一遍:同一批里"看戏式调侃"给的是调侃还是讽刺+漠然?两种都行,但**整个批次要用同一把尺子**。
- **历史日期**:08-21·09-11·09-12 仍是旧三元(judge),**不要回改**;脚本对新旧两套模型都已兼容。
- **原始链接**:所有问题/回答保留原 URL(Excel 中为超链接)。
- **月度扩展**:新日期直接插入新 sheet 到最前;raw 数据按日期归档,随时可回溯。
- 问题本质列 = 对该问题的主题内容提炼(一句话),回答行该列留空。

## 约束(一~五,不可妥协)

### 约束一:回答内容完整性(截断检测与补全)

搜索接口的 `ContentText` 是**摘要(截断)**,不是全文。抓取后必须执行:

1. **补全**:`python scripts/fulltext.py --root <root> --date <D> [--cookie <cookies.txt>]` 用网页 API(api/v4/answers/{id})补全。**带 `--cookie`(网页登录 Cookie,见 Step 1.2)可解锁全文**;不带则未登录尽力补全。写回 `content_status`:`full`(已补全)/ `truncated`(网页 API 也截断,全文需网页登录 Cookie,开放平台 Access Secret 不适用)/ `summary`(抓取失败,保留摘要)。
2. **禁止静默使用截断文本**:`content_status != full` 的回答,Excel 备注列自动标注「接口摘要,全文需登录网页查看」;HTML 原文折叠标题显示「接口摘要」标签;分析基于摘要时如实说明。
3. 完整回答判断:网页 API 返回含 `content_need_truncated=true` 即为截断;不得把「搜索摘要」当作「完整回答」写入交付物。

### 约束二:情绪判断谁来判、怎么保证一致(2026-09-13 修订)

- **四维主体(立场/解决思路/判断逻辑/情绪倾向)由 Agent 亲自读原文归纳**; **情绪三字段
  (`emotion_tags`/`emotion_intensity`/`emotion_target`)下放 subagent**(用户 2026-09-13 指定)。
- **仍然禁止**:任何脚本、py 程序、情感分析 API、词库/关键词统计、外部模型对情绪做判定。
  `check.py`/`merge_emotion.py` 只做**值域与结构校验**, 不做语义判断。
- **下放的前提是"主 Agent 复核分歧"**(实测首次下放与主 Agent 完全一致率仅 **2/10 = 20%**):
  流程是 `gen_prompts --emotion` → 每批 5 个 rank 一个 subagent → `merge_emotion --compare`(出分歧清单)
  → **主 Agent 只裁决不一致的那些** → `merge_emotion --write`。纯下放不复核会得到"每批一把尺子"的标签。
- 为压低分歧, `prompt_emotion.md` 内置:四条边界裁决(`讽刺`vs`调侃`用"读者会不会认为作者在骂谁"一问判定、
  强度锚点、指向优先序"取最具体的那一个"、`失望`/`无奈`/`忧虑`/`悲悯` 四选一)、3 条标定样例、
  以及**必填 `why`**(每个标签各一句 ≤20 字触发依据, 让分歧可复核)。
- 同样禁止 `judge` 三元回填:历史日期保留旧三元的渲染兜底, 新数据一律三字段。
- **注意区分**:热点拓展 subagent 会判断"哪几条回答只是情绪宣泄、没有可延伸判断"从而不予立链,
  那是**来源取舍**, 与情绪字段是两件事; 它们被明确禁止修改 `analysis.json`(见 prompt_swarm.md 收尾纪律)。
- 每条回答取三个字段的判据与配色基调见「约束三」。

### 约束三:情绪多元化(2026-09-13 起,取代旧三元)

用户 2026-09-13 明确要求「多元化情绪, 不要三元简化」。每条回答给三个字段:

| 字段 | 值域 | 说明 |
|---|---|---|
| `emotion_tags` | 12 个受控标签, **每条 1-3 个** | 愤怒/讽刺/忧虑/失望/无奈/共情/振奋/认同/调侃/审慎/悲悯/漠然 |
| `emotion_intensity` | 1-5 | 1 极淡 → 5 极强 |
| `emotion_target` | 6 类之一 | 当事人/涉事机构/制度环境/舆论与媒体/自身经历/泛化社会 |

- **旧三元(积极/中立/消极)已不再落库**,`judge` 仅作**历史日期渲染兜底**(08-21·09-11·09-12 仍是旧结构,
  必须继续能出页面)。两套模型的判定与渲染由 `contract.ANALYSIS_CORE / EMOTION_DIMS / ANALYSIS_LEGACY_FIELDS`
  与 `gen_html.emotions_of()` 统一兼容 —— **不要在脚本里再写 `A["judge"]` 这种硬取**。
- **标签可叠加**:一段文字同时愤怒+讽刺+无奈是常态(实测 100 条平均 1.89 个标签),不要为了"一个主情绪"而丢信息;
  但也不要凑数,标签必须是该回答**行文里真实存在**的情绪载体。
- **强度**看行文的情绪浓度而非立场强弱:冷静举证=1-2;有明确情绪但不激烈=3;通篇激愤/狂欢/痛心=4-5。
- **指向**看情绪冲着谁:骂涉事企业=`涉事机构`;骂规则与体制=`制度环境`;骂舆论场/媒体/网友=`舆论与媒体`;
  谈自己经历=`自身经历`;泛谈社会风气=`泛化社会`;指向具体当事人=当事人。
- Excel:情绪占 3 列(标签以「、」连接 / 强度 / 指向);强度与指向列有**硬下拉**,标签列因是 1-3 个多值不加下拉
  (Excel 的 list 校验无法表达多选,加了会把合法值判成非法),词表写在「说明」sheet。
- HTML:标签渲染为**多色 chip**(按情绪基调分 5 组配色)+ **强度点**(●●●○○)+ **指向小签**(见约束四)。
- 情绪倾向列(text)与三个情绪字段并存,不互相替代。

**标签配色基调(hot/cold/warm/up/wry/dry)**:由 `contract.EMOTION_TAG_TONE` 定义,同组同色系,
避免 12 种颜色各说各话;颜色值集中在 `contract.EMOTION_TONE_COLOR`,HTML 的 CSS 类与内联迷你条共用。

### 约束四:HTML 页面表现(固定规范,gen_html.py 必须遵守)

页面采用**分页式**「索引 + 每问题一页」结构,任何改动不得破坏:

**文件结构**
- `<root>/知乎热榜跟进-<date>.html` 根入口(meta refresh 自动跳转索引页)+ `<root>/知乎热榜跟进-<date>/` 目录(index.html + q01..q20.html,每问题一页)。
- 索引页:20 个卡片网格 `repeat(auto-fill, minmax(290px, 1fr))` 自适应(1→8 列随视口),每卡=整卡链接进详情页;卡内:排名/扩展标记/标题(2 行截断)/最高赞/回答数/情绪分布迷你条;悬停上浮。
- 详情页:吸顶导航(返回索引 + 上一题/下一题翻页,首末题禁用对应方向)+ 单列宽版(max-width 900px);回答默认折叠为紧凑卡片(`<details>`),summary 含序号/作者/赞/情绪标签/立场摘要,点击展开四维分析表 + 原文;有拓展的条目(当前=全部 20 条)显示金色拓展卡片,排在回答之后。

**风格(anti-slop,源自全局 taste-skill)**
- 禁止 AI 默认审美:紫色渐变、玻璃拟态滥用、Inter+slate-900、三等分卡片。
- 配色:墨蓝渐变头部(#16283f→#1f3a5f)、暖纸底(#f5f3ee)、白色卡片 + 细边框(#e8e4da)、克制阴影(hover 微升)、金色点缀(#b08d2e)。
- 情绪配色固定(2026-09-13 起为多元化):按**基调分组**上色 —— 愤激 hot `#c0493a` / 低落忧思 cold `#5b7c99` /
  亲和 warm `#2f7d4f` / 昂扬 up `#b08d2e` / 戏谑 wry `#8a6f9e` / 克制平淡 dry `#8a8a8a`。
  标签 `emotion_tags` 渲染为多色 chip、`emotion_intensity` 渲染为强度点(●●●○○)、`emotion_target` 渲染为「指向 X」小签;
  索引卡迷你条按**标签频次降序**堆叠(悬停显示「标签 次数/总数」),索引页底部有图例自解释。
- 字体:系统栈(PingFang SC / Microsoft YaHei),详情页正文 ≥13px,卡片标题 ≥14.5px,页面标题 23px。

**交互**
- 全部用原生 `<details>`(无 JS 依赖,可打印可复制);≤720px 隐藏立场摘要列。
- 生成后必须校验,统一用 `python scripts/verify_html.py --root <ROOT> --date <D>`(退出码 0 才算通过):
  详情页数=热榜条数、每页折叠数=回答数、翻页 q 前后衔接(首末页为 `class="off" href="#"`)、根入口跳转路径、索引卡片数、「接口摘要」标签数=非 full 回答数、**情绪标签/强度/指向 渲染齐全且与分析数据逐项对账 + 新旧情绪模型未串用**(2026-09-13 新增)、**拓展块覆盖范围 == `extension.json` 的 rank 集合**(2026-09-13 改为全部条目后按实际产物判定)。
  **注意折叠口径**:每条回答固定 2 个 `<details>`(折叠卡片 `class="a"` + 原文 `class="a-text"`),校验按 `class="a"` 计数;不要用 `<details` 总数判断,否则会误判成「数量翻倍」。

### 约束五:发散搜索禁止名词解释类查询(2026-09-11 用户明令)

**禁止**在发散环节做任何**名词解释 / 概念科普 / 百科式背景铺垫**类搜索。这类查询产出的是"正确的废话":读者本就知道,或与热榜事件无直接关系,属于稀释交付物价值的内容。

**判定标准(命中任一即禁止)**:

| 禁止的查询模式 | 反例 |
|---|---|
| `X是什么` / `什么是X` / `X是什么意思` | 「什么是 DRG 付费」「碳中和是什么意思」 |
| 定义与解释类 | `X 定义`、`X 解释`、`X 名词`、`X 概念`、`X 科普`、`X 入门` |
| 起源与由来类(纯背景) | `X 的由来`、`X 的起源`、`X 历史背景`(无具体主体/时间/数据) |
| 通用百科铺垫 | 「XX 制度介绍」「XX 行业概况」这类与当日事件无锚点的通识 |

**允许且鼓励的查询类型**(每条查询词必须含**具体主体 / 时间 / 数字 / 事件名**):

- **案例**:同类事件、判决、事故、产品、项目(如「XX 医院 手术事故 判决」)
- **人物**:当事人、操盘者、研究者、履历(如「XX 公司 CEO 履历」)
- **链路**:机制传导、制度沿革、产业分工、因果链(如「禁酒令 白酒 营收 数据」)

**三类首选查询构造式(用户 2026-09-12 指定,优先照此写)**——背景一律用**案例与可核数据**支撑,不用概念铺垫:

| 构造式 | 查询词写法 | 取回的应是 |
|---|---|---|
| **具体案件 + 索赔金额 + 法院结论** | 「XX 案 索赔 XX 万 判决 赔偿」 | 有金额、有审理结论的真实案件(如「祁东 店主 晕倒 索赔10万 人道主义补偿 央视」「昆明 法拉利 孩童 踩踏 家长 500元 拆车件 29360元」) |
| **调研样本数 + 百分比** | 「XX 抽查 N 台/份 检出率 %」 | 有样本量与检出率的调查(如「上海疾控 128台 洗衣机 霉菌60.2% 大肠菌群100%」「社科院 4016人 调研 断亲 80%」) |
| **人口抽样公报口径** | 「统计公报 抽样 家庭户 户均」「一人户 万户 占比」 | 官方公报口径数据,且**注明口径与年份**(如「2025年1%人口抽样调查 户均2.52人」「一人户5839万户 占16.77%」) |

口径不一致要**分别标注来源**(实测同一指标 2.52 人 vs 2.62 人来自不同年份抽样),不得混用成一个数。

**例外(唯一)**:某个术语本身是理解事件的关键、且有制度争议或金额/数量可查时,**不得**搜其定义,而应改写成该术语的**案例/判决/数据/争议**来搜(如把「什么是全租房」改写为「全租房 押金 违约 案例」)。

**背景要靠证据,不靠定义**:发散线里的"历史依据/真实社会议题"必须用**过往案例与可核数据**支撑;若某个概念确实需要交代,用一句话在 `content` 内带过即可,不单独搜索、不单列条目。

**执行要求**:
- `scripts/search_many.py` 的每条 query 落盘前自检是否命中上表;
- subagent 的 `thinking` 里若删除了名词解释类查询,应记录「已剔除名词解释类查询」;
- 主 Agent **在运行中**抽查 query 历史(不能只信 subagent 自述的「命中=无」),发现命中即要求重发。
  查历史要读**逐轮归档** `ext_search/<D>/rank_<n>/rank_0N_*.json` 的 `_meta.query`——
  `queries_rank_<n>.json` 每轮整文件覆盖,只留最后一条;`_meta.query` 不在归档顶层,别找错键
  (2026-09-13 实测:写错键位扫出 0 条,差点得出"无法核查"的错结论)。经验值:90 条 query 命中 1 条,
  而那 1 条(「教育部 互动平台 回复…没有第一学历这个概念」)是**正则误伤**(指向官方答复的可核查询,
  不是名词解释),故这条纪律**不适合做成机械硬闸**,要人来判。

**与发散逻辑的关系**:两条发散线中的"背景"最容易滑向名词解释——社会事件类的②「历史依据与过往案例」只搜**案例与数据**;非时效类的③「真实社会议题」只搜**现象与群体行为的证据**,都不搜术语解释。

## 热点拓展板块(2026-09-13 起覆盖**全部条目**,Agent Swarm 并行)

> **范围变更**:原为「仅热榜前 10」,用户 2026-09-13 要求改为**20 个全部**。范围改动要同步三处:
> `gen_html`(卡片"扩展"标不再限 rank≤10)、`verify_html`(校验「拓展块覆盖 == extension.json 的 rank 集合」)、
> 以及本文档的成本口径 —— Swarm 从 10 个 rank 变 20 个,单日成本约 **+15–25 万 token(基线 +38%~64%)**。

对热榜**前 20 名(全部条目)**做**发散性思维扩展**,同步到 Excel「热点拓展」sheet 与 HTML 问题卡片内的「🧠 热点拓展思考」块。

### 结构化框架:发散链(2026-09-12 用户要求「条目要清晰」后确立)

热点拓展**不是条目清单,而是若干条论证链**。每个 rank 产出几条链,每条链固定三段:

```text
想法(claim)  ——回答区里的一个判断,一句话,可追溯到具体回答(附出处链接)
  ├─ 证据(evidence) 每条标 relation: 印证 / 反驳 / 边界
  └─ 落点(takeaway) ——这条链最后说明了什么(不是复述证据,而是给出结论)
```

- **为什么必须是链**:扁平条目列表 + 一大段 thinking 的旧格式,读者看不出「这条证据是在支持哪个论点」,也看不出正反两侧(实测 2026-09-12 的交付物即如此)。链式结构强制每条证据回答「我在印证谁、反驳谁」。
- **有链接就附上(用户 2026-09-12 追加要求)**:想法既然提炼自某条回答,就把**那条回答的链接与序号/赞数**直接附在想法后(`chains[].source`);Excel 的落点行附上本链全部来源链接;HTML 思考过程里的裸 URL 自动变成可点击。任何一处都能一步回到原文。
- **relation 三个值**:`印证`(支持该想法)/ `反驳`(推翻或严重削弱该想法)/ `边界`(只在附加条件下成立,即「对,但仅限…」)。`边界` 是最高频也最容易被漏掉的一类。
- **一条链可以只有 1 条证据**(如某想法只有一个边界样本),但**不能为凑链数把不同论点的证据混进同一条链**。
- **每条证据只能归入一条链**(避免在 Excel/HTML 里重复出现);merge 按链展平出 `items` 供话题库使用。
- 同 rank 内 2–4 条链为宜(实测 2026-09-12 十个 rank 共产出 31 条链 / 65 条证据)。

### 执行方式:Agent Swarm(rank 1-20 并行)

主 Agent 负责调度,subagent 负责单个 rank 的完整发散:

1. **前置准备(主 Agent)**:① 读话题库(见下,了解已有话题与案例,避免跨日期重复);② 为每个 rank 建独立工作目录 `ext_search/<D>/rank_<n>/` 与独立查询文件 `ext_search/<D>/queries_rank_<n>.json`(**文件按 rank 隔离,防并发冲突,坑 16**)。
2. **派发**:rank 1-20 各派一个 subagent(可 2-3 个 agent 各包 2-5 个 rank),每个 subagent 独立执行:
   ① 读该 rank 的回答(answers_summary.json 对应段)→ 判断问题类型(社会事件类/非时效类)→ **先立想法,再找证据**:从回答里提炼出 2-4 个可被证据检验的判断,而不是先搜再想
   ② 动态发散搜索:每轮 **1 条**查询(写自己的查询文件、输出到自己的目录,`python scripts/search_many.py <自己的queries.json> <自己的outdir> --db zhihu`),**每轮检索前先做收敛性判断(见下)**;每条证据要判明它对该想法是印证、反驳还是边界
   ③ 收敛即止,产出该 rank 的 `chains`(想法 + 证据 + 落点)+ `thinking`
3. **汇总(主 Agent)**:运行 `python scripts/merge_extension.py --root <ROOT> --date <D>` 完成格式统一、schema 强校验与跨 rank 去重报告,再 `topic_lib.py update` 更新话题库。**不要相信 subagent 的「已校验通过」自述**(实测 3 个 rank 自报合规却实为 5 处硬错误:313 字超长、链路/案例各 4 条、案例 8 条),必须由本脚本复核。**派发时就让 subagent 跑权威校验器**(2026-09-13 起):`merge_extension.py --ranks <n> --lint` 是只读模式,不写文件、单 rank 可跑,把违规在子任务内部就挡掉,不必等 20 个 rank 跑完才发现、再返工 3 轮。

### subagent 输出 schema(强制,违反会被 merge_extension.py 判失败)

每个 rank 写出 `ext_search/<D>/rank_<n>/rank_<n>.json`,**顶层是单个 JSON 对象**——禁止嵌套 `{"7": {...}}`、禁止数组:

```json
{
  "rank": 7,
  "title": "<原问题标题>",
  "url": "<原问题 URL>",
  "category": "<主题分类, 如 劳动权益与消费 / 外交政策与国际关系>",
  "chains": [
    {
      "claim": "回答区里的一个判断（一句话，不含证据；【不要写「想法：」前缀】）",
      "source": {"answer_index": 3, "likes": 294, "url": "该想法提炼自的那条回答的链接"},
      "evidence": [
        {"relation": "印证", "type": "案例", "content": "要点提炼(60-300字，含数字/时间/主体)",
         "url": "真实来源链接", "note": "这条证据为什么能印证/反驳/限定该想法（直接写理由；【不要写「标XX：」这类 schema 说明】）",
         "entities": ["上海疾控", "2025"]}
      ],
      "takeaway": "这条链最后说明了什么（结论，不是复述证据；【不要写「落点：」前缀】）"
    }
  ],
  "dropped": [
    {"type": "案例", "content": "被收敛掉的同类案例要点(60-300字)", "url": "真实来源链接",
     "note": "与已采用条目同属哪一类", "reason": "为何归为同类而不单列（同样不要写「标XX：」）"}
  ],
  "thinking": "发散思考过程(为何立这些想法、检索路径、收敛依据、被舍去的同类案例)"
}
```

- `chains` **必填**且非空;每条链 `claim` 与 `takeaway` 都要写(缺 takeaway 会被 merge 告警、HTML 少一行结论);
- `source`(想法出处)**可选但推荐**:`{"answer_index": N, "likes": N, "url": "http..."}`,指该想法提炼自哪条回答——`url` 从 `answers_summary.json` 该 rank 的 answers 里取,不要手写;格式不对 merge 会告警并忽略;
- `evidence[].entities`(**必填**,2026-09-13 起):2–4 个主体锚点(机构/人物/案件名/文件名),入库后可用 `search --entity` 按主体查「这家公司/这个人还出现过几次」。**必须是必填** —— 标成"可选但推荐"时实测 71 条证据 0 条填写,该检索彻底失效;subagent 漏填时 `verify_ext.extract_entities()` 会兜底自动抽取并标 `entities_auto`;
- `dropped`(**可选**):被「同类案例只取一条」收敛掉的同类案例。**不进 items、不进 Excel/HTML**,但会被 `topic_lib` 以 `adopted=false` 入库,使后续发散查重能直接命中「已知同类、已判定不采用」。每条需 `type/content/url`,建议带 `note` 与 `reason`;
- `evidence` 每条必须带 `relation`(不写会被 merge 默认成「印证」并告警);
- 同一 `type`(案例/人物/链路)**≤3 条**(按**该 rank 全部证据**计,不是每条链各算);
- 旧格式(顶层 `items` 扁平列表)**仍被兼容**,但会渲染成"无想法的证据堆",交付物可读性差,新产出不再使用;
- `thinking` 必填,不要用 `divergence_dirs` 等替代字段名;
- `url` 必须取自搜索结果原文链接,禁止伪造;无来源的推断在 content 中标注「推断」;
- 派发 prompt 里直接粘贴本 schema **与「约束五:禁止名词解释类查询」**,并要求 subagent 结束时自报「链数 / 证据数 / type 分布 / 搜索轮数」。
- 派发 prompt 里同时给出**三类首选查询构造式**(具体案件+索赔金额+法院结论 / 调研样本数+百分比 / 人口抽样公报口径)与**「同类案例只取一条,其余写进 thinking 并以『未采用但值得记录——』起头」**这两条规则(见约束五与收敛性判断);主 Agent 汇总时按此复核。

### 拟答参考稿(2026-09-13 用户要求;同日改为由**独立书写 subagent** 产出)

每个 rank 产出一篇**成文回答稿**,落在 `ext_search/<D>/rank_<n>/draft_<n>.md`。
它不是 chains 的复述,而是把证据组织成一篇**能直接拿去用**的回答。
**2026-09-13 起不再由拓展 subagent 顺带写**(改由 Step 3c/3d/4c 的学习 loop 负责:先学写法 → 汇编成书写 skill → 再据此成文),
要求全文见 `prompt_write.md` 与 `<ROOT>/书写skill/书写skill.md`,要点:

- **语言(用户三轮反馈后定稿)**:①**讲清楚优先于精简** —— 每段的结论后面必须写全"为什么成立"+"所以意味着什么",
  不许只丢结论让读者自己拼因果;②**例子全篇最多留 2–3 个**,删例子腾出的字要花在讲道理上;
  ③**专有名词要么一句话交代(如「编剧全勇先」)要么直接不用**;④观点要一眼看明白 —— 第一段与最后一段各自能独立复述立场。
- **口吻**:纯路人/观众/消费者视角,**不立人设**(不写"我是…""作为一个…");**允许暴论**,该拍桌子就拍。
- **禁止**:AI 腔提示语(「先给结论」「值得注意的是」「综上所述」)、标签式标注(「推断:」「(推断)」)、
  中庸句式(「一方面…另一方面…」「见仁见智」「不可一概而论」)、**正文里任何链接**、小标题官腔。
- **篇幅**:≤500 字(建议用满 420–495)。**格式**:首行 `# 标题`(20 字内),自然段,结尾一句可转述的判断句。
- **落地**:HTML 每问页底部「✍️ 拟答参考」块;Excel「拟答参考」sheet(日期/排名/问题标题/拟答标题/正文);
  `verify_html` 有「有稿必渲染、无稿不许渲染」的对账检查。
- **不重跑成本提示**:拓展已跑过的 rank 若只想补稿,可派轻量书写 subagent 直接读现成 `rank_<n>.json` +
  `书写skill.md` 写稿(约 0.8 万 token/rank),不必重跑检索。

### ⚠️ 本流程不发布:开放平台没有发布接口(2026-09-13 核实)

**拟答稿只到"稿"为止,流程不做、也不应该做"发到知乎"。** 依据(机读事实,非猜测):
`zhihu-cli capabilities` 返回的全部命令中,`me/creator` 系列**全是 `GET`**(me contents / me content / me comments /
me stats / question answers / question recommend / quota),唯一的写操作是 `knowledge upload`(上传自己的知识库文件,
路径 `/api/v1/knowledge/files`)与读性质的 `knowledge search`。**没有任何创建回答/文章/想法的端点**,`answer` 子命令是
"检索资料并生成知乎直答"(读+生成,不是发帖)。因此:

- 想发布只有两条路:**人工复制粘贴**(推荐,零风险),或**浏览器自动化驱动已登录的网页端**(技术上可行但见下)。
- 浏览器自动化发布属于**操作真实账号的不可逆对外行为**,且自动化发帖多半违反平台用户协议、有账号风险;
  **未经用户逐条明确授权不得执行**;即使获准,也应只填到编辑器、停在提交前由人工点发布。
- 该结论是能力边界,不要在交付物里暗示"已发布/可自动发布"。

**若用户明确授权,可以走浏览器自动化发布**(2026-09-13 实测: 自动发出 14 条后命中平台配额; 人工补发也报同一提示)。

### 发布策略(2026-09-13 用户指定, 硬制度)

> **每天只发前 15 条**(`contract.PUBLISH_TOP_N` = 15)。第 16 条起**只出稿、不发布**,
> 但**流程保留** —— 稿子照常产出并进 Excel「拟答参考」sheet 与 HTML 页内块, 只是不做发布动作。
> 台账里这类条目标 `draft_only`。

原因是平台**日/周数量上限**: 用户手动发布时收到原文提示
「您的回答过于频繁，已达到本日或本周数量上限。草稿已保存，请稍后重试」——
这是**配额**而非短冷却, 靠"等几分钟再试"无效(实测 10 分钟冷却仍不通), 必须按天/周计。

```text
# 前置: playwright-cli open <问题URL> --browser=msedge --headed --persistent  (确认已登录, cookie 含 z_c0)
# 批量(推荐): 默认只发前 15 条, 自动跳过台账里已发布的, 命中配额即停, 状态写 raw/<D>/publish_ledger.json
python scripts/publish_batch.py --root <ROOT> --date D                 # 前 15 条中未发的
python scripts/publish_batch.py --root <ROOT> --date D --status        # 只看台账
python scripts/publish_batch.py --root <ROOT> --date D --mark "1=<answer url>"
python scripts/publish_batch.py --root <ROOT> --date D --all           # 显式要求时发全部(一般不用)
# 人工兜底(按台账自动挑出"应发但没发"的): python scripts/make_manual_publish.py --root <ROOT> --date D --out <md>
# 单条(填但不发布, 由人点提交): python scripts/publish_draft.py --draft <md> --out <js> [--publish]
```

**发布台账 `raw/<D>/publish_ledger.json` 是"发到哪一步"的唯一事实源**(为什么必须有: 见坑 64 ——
批量 18 条脚本全报成功、实际只发出 13 条, 事后要靠截图+`me contents`+逐条 goto 才拼出来,
而 `me contents` 只返回 29 条中的 17 条)。状态取值(`contract.LEDGER_STATES`):
`published` / `blocked_limit`(**命中日/周配额**) / `blocked` / `pending_manual` /
`draft_only`(按策略不发) / `gen_failed`。**隔天续发只需重跑同一条命令** —— 已发布的会自动跳过。

**发布纪律(硬性, 都是当天踩出来的)**:
1. **配额优先于一切**: 页面出现「过于频繁/数量上限」就**立即停**, 不要继续试剩下的条(毫无意义)。
   该提示是 toast、会自己消失, 所以**每次点击后要立刻扫一遍页面文本**(实测等 6 秒后再扫就抓不到,
   会把配额失败记成含义不明的 `blocked`)。`publish_draft.py` 已内置即时扫描并回报 `limitHit`。
2. **每条都要验证真的发出去了**: 判据是 URL 是否变成 `/answer/<id>`, 不是"点击已执行"。
3. **连续 2 条点不动就停**, 剩余标 `blocked`; `publish_batch.py` 已内置。
4. 被限流后**不要反复重试同一条**: 每次重试都会留下自动草稿, 而草稿会让页头按钮从
   「写回答」变成「编辑回答」 → 只找「写回答」的脚本会因 `contenteditable` 不出现而超时。
   打开编辑器必须按 `写回答 → 编辑回答 → 草稿入口` 依次兜底(`publish_draft.py` 已实现)。
5. **发布前必须确认是"新回答"**: 底部按钮应为「发布回答」(编辑已有回答是「更新回答」),
   且页面答案作者里不该有本账号 —— **在"编辑已有回答"状态下发布会覆盖用户原答案**。
6. **发布后会自动关注该问题**(平台行为), 清尾见 `unfollow_question.py`。
7. **发布完要做线上检验**: 逐条核对自己那条回答的正文与草稿是否一致(字数/段落/无整段重复)。
   注意校验器自身也会错 —— 别用 `.RichContent-inner` 的 `allInnerTexts()` 再取最长者
   (那会抓到整页所有回答), 要按 answer id 定位自己的卡片(坑 65)。

### 话题库(跨日期累积,双轨:index.json 机读 + md 人读)

**定位与数据模型(2026-09-12 用户明确)**:
- 定位:**「避免后续重复搜索的 database」**,不是运行日志。
- **维度区隔而非父子树**:`type`(案例/人物/链路,3 个稳定取值)是**全局唯一的一级索引**;`cat`(主题,19 个自由文本值、已出现近义分叉如「消费电子」vs「半导体与消费电子」)只作**二级主题标签**,仅用于展示分组。理由:同一 `type` 在每个 `cat` 下都会重复出现,若把它做成 `cat` 的子节点,这一个维度会被复制 19 份(即"多次区隔");而筛选与匹配需要的是「跨主题取全部案例」这种能力。父子结构只出现在人读视图里。
- **保留时间维度,但不用时间做区隔**:`date` = **首次收录日期**,只是条目属性。一条 url 只一行,多日重复出现不重新入库、也不覆盖既有 date(因此时间不会把同一条事实切成多份)。

**双轨结构(+1 加速索引)**:
- **`<ROOT>/话题库/index.json`(机读索引,唯一数据源)**:`{"schema": 2, "items": [...]}`(字段与分组维度由 `contract.LIB_*` 定义)。条目字段:
  | 字段 | 说明 |
  |---|---|
  | `date` / `last_seen` | 首次收录 / 最近命中日期(**只是属性, 不分区**) |
  | `type` | **一级维度**(案例/人物/链路)—— 全局唯一索引, 筛选与匹配都先走它 |
  | `cat` | 二级主题标签, **走受控词表** `contract.LIB_CATS`;自由文本经 `LIB_CAT_SYNONYMS` 映射, 未命中归「其他」并告警 |
  | `content` / `url` | 要点提炼 / 来源链接(url 归一化后为**唯一键去重**) |
  | `entities` | 主体锚点(机构/人物/案件名), 供 `--entity` 检索; 由 subagent 提供, 历史条目为空 |
  | `adopted` | `true`=已采用;`false`=**未采用但值得记录**(被「同类案例只取一条」收敛掉的案例) |
  | `claim` / `relation` / `claim_source_url` | 论证层:该证据印证/反驳/边界哪个想法、想法出自哪条回答 |
- **`<ROOT>/话题库/话题库.md`(人读展示,派生物)**:一级按 `type`(`## 案例（59）`)、二级按 `cat`(`### 医疗健康（13）`),行 `| 收录 | 最近 | 内容要点 | 来源 url |`;未采用条目带「（未采用，仅备查）」前缀。
- **`<ROOT>/话题库/index.sqlite`(加速索引,派生物)**:由 index.json 重建;`entries` 表 + `(type)/(cat)/(date,last_seen)` 索引 + **FTS5(trigram)** 全文表。**必须用 trigram**:默认 unicode61 会把整段中文当一个词,「洗衣机」查不到「家用洗衣机」(实测 0 命中)。`search` 会自动检测过期并重建,sqlite 缺失/FTS5 不可用时退化为 Python/LIKE 扫描。
- **维护脚本 `scripts/topic_lib.py`(全流程强制使用,禁止手改 md)**:
  - `update --root <ROOT> --date <D>`:增量收录当日 extension.json 的 `items`(adopted=true)与 `dropped`(adopted=false)→ cat 归一化 → 字段规整(schema 版本 +1 时自动迁) → 回填 `date/last_seen/claim/relation/entities` → **同类体检** → 原子写 index.json + 重建 md 与 sqlite。
  - `search --root <ROOT> [--url U] [--type T] [--cat C] [--entity E] [--keyword K] [--since D] [--until D] [--json] [--adopted-only]`:条件可自由组合;`--json` 输出机读结果;`--adopted-only` 排除未采用条目。
  - `rebuild --root <ROOT>`:从 index.json 重建 md;`reindex --root <ROOT>`:重建 sqlite。
  - `prune --root <ROOT>`:**全库一致性扫描**——移除 url 已不在**任何** `raw/<D>/extension.json`(含 `dropped`)里的条目(保留集合 = 所有日期 extension 的 url 并集)。`--date` 已废弃、传入会被忽略。
- **写库安全**:`update`/`prune` 是"读—改—整体重写",现改为**先写 `.tmp` 再 `os.replace` 原子替换** —— 写一半崩掉不会毁库。并发入库仍需避免(当前流程 update 只在主 Agent 汇总后单点执行)。
- **同类体检的预筛**:`similar_pairs` 先算 3-gram 集合 Jaccard(`contract.LIB_SHINGLE_JACCARD`=0.30),低于阈值直接跳过,再对候选算 `difflib` 序列相似度(阈值 0.55)——避免 O(新增×存量) 次全对比在库里上千条时拖垮 update。
- **使用时机(强制)**:
  - **搜索前**:每个 subagent 发散前用 `search --url/--keyword` 查重——已收录主题不重复搜索、不重复收录(用户明令「不需要重复搜索」);
  - **搜索中**:每轮结果 URL 与 index 交叉比对,已收录案例直接跳过;
  - **完成后**:主 Agent 汇总写入 extension.json 后依次跑 `topic_lib.py update` 与 `prune`,新发散点按 url 去重纳入(同一分类下同主题案例 ≤3,超出后新案例只进 `thinking` 不进条目)。
  - **跨 rank 复用同一 URL**:`merge_extension.py` 会告警,`topic_lib update` 按 url 去重——首个条目入库,后续同 url 条目在 content 更长时执行「内容升级」(实测 2026-09-11 出现 1 例:rank3/rank4 复用同一来源服务于不同发散点)。复用可接受,但应确认是有意为之,而非子任务重复搜索。
- **跨日期作用**:话题库是断点续跑与多日积累的共享记忆(index.json 可被任何脚本/子任务读取),新日期的发散在已有条目基础上继续补新,不重新挖旧土。

### 信源门槛(采集端强制,2026-09-12 用户要求)

**前提**:本流程信源集中在知乎,**交付的其实是「知乎平台公众言论」的事实性提炼,不是已核实的事实**。因此采信标准按"言论"定,而不是按"事实"定——后者永远验不完,前者有明确门槛。

**采集端三问(不通过就不进 items)**:

| 问 | 通过 | 不通过 |
|---|---|---|
| **① 谁说的?** | 具名机构/媒体/法院/政府/公报/实名当事人 | 匿名群体:`有从业者`、`业内人士`、`据悉`、`网传`、`某博主` → **只能作观点,不得作为事实条目** |
| **② 有可核锚点吗?** | 金额 / 比例 / 样本量 / 案号 / 法规条号 / 公报口径 / 具体时间地点 | 无任何数字与条号的概括 → 只进 `thinking` 或标 `D·观点` |
| **③ 事实还是主张?** | 可被第三方按同样数字核对的事实陈述 | 个人主张/预测(如「自媒体极难变现」「大博主赚不到钱」)→ 只进 `thinking` |

**明确禁止采集的三类**(实测案例):
1. **匿名群体的量化断言**——「有从业者对比称,2000粉博主月入3000-4000元」:数字长得像证据,归属却是匿名的,**不值得采信**(2026-09-12 rank5 实例,已被判 `C·不采信`);
2. **无出处的行业概括**——「自媒体极难变现」「大博主赚不到钱小博主稳赚钱」;
3. **未经证实的预测性判断**。

**优先采集**(天然高可信):判决/通报/公报/统计/企业公告/实名当事人陈述/带案号的案件。

**脚本兜底(不硬拦截)**:`verify_ext.py` 会按上表给每条证据打 `source_tier` ——
`A 事实性(具名主体+可核锚点)` / `B 待定(有可核锚点,未见具名主体)` / `C 不采信(匿名归属)` / `D 观点/主张(可核锚点不足)`,
并支持**多源印证升级**(独立来源组 ≥2 → 升 A)。判定权仍在采集端,脚本只是兜底:
实测纯正则识别"具名主体"会把「华为发布 Mate XT 2」这类专有名词判成无具名,误杀率过高,**不可据此硬删条目**;`C` 类保留在库可审计,但在交付物上带红色标签与「不采信」提示,不冒充事实。

**2026-09-13 修(定级口径, 实测误杀)**:`锚点` 不再只数数字 —— 只数数字会把
「湖北省纪委机关等六部门联合通报7起…王某被判有期徒刑一年六个月」「国务院办公厅印发《关于严格规范涉企行政检查的意见》」
这类**制度性事实**判成 `D·观点`(交付物上还带灰色标签)。现锚点 = **数值锚点**(带单位数字) + **制度性锚点**
(法规条号 / 案号 / 人民法院案例库入库编号 / 《文件名》+ 印发·施行 / 判例通报),`extract_entities()` 同时兜底
自动抽取 `entities`(机构/文件名/人名)。**D 的判据是"锚点不足",与有没有具名主体无关** ——
具名律师的阐释性主张同样是 D,故标签措辞改为「观点/主张(可核锚点不足)」。

### 收敛性判断(每轮检索前必做,命中即跳过本轮)

构造新查询前依次判重,以下任一命中则不执行该查询:

1. **查询主题去重**:新查询词与已执行查询词核心主题重叠(同话题线——如「台风」「观浪」「溺水」已各查过)→ 换角度或停止,不重复搜索;
2. **结果 URL 去重**:上一轮结果的全部 URL 已出现在历史轮次/话题库 → 本轮零新线索;
3. **同类型案例上限**:该 rank 已提炼的发散点中,同一 `type`(案例/人物/链路)已达 **3 条** → 同类不再新增条目(新发现只记入 thinking);
4. **同类案例只取一条(用户 2026-09-12 指定)**:具体案例本质上往往是**对同一类问题的反复讨论**——已有一条支撑某判断后,**除非与已有条目存在极大差别**(如法律定性不同、机制相反、正反两极),否则**只采用一条**,不为同类案例反复搜索、不并列多条。
   - 判据:两条案例若「换成对方,论点强度不变」,即为同类 → 只留一条(留信息量更大、金额/结论/口径更具体的那条)。
   - 被舍去的案例**不要丢弃**:写进该 rank 的 `thinking`,以 **「未采用但值得记录——」** 起头简要交代事实要点与为何归为同类,供日后跨日期复用。

**收敛停止判据**:同一 `type` 触顶(案例/人物/链路各满 3 条)**且**连续 1 轮无新 URL ⇒ **硬停**(2026-09-13 收紧);
或 3 条主线均已覆盖且同类型达上限。旧的「连续 2 轮无新线索」太松:实测 `type` 触顶只被当成"不再新增条目"
而没被当成"停止搜索",导致 rank4/rank5 各跑 **17 轮**(模板建议 3–6 轮)、rank1 跑 11 轮,白烧检索与读结果成本。
与话题库比对产生的「已有案例」也算无新线索轮;按第 4 条判定为「同类已有」的案例同样计入,不为凑条数继续搜。

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

> **查询内容硬约束(见约束五)**:禁止 `X是什么` / `什么是X` / `X定义` / `X解释` / `X科普` / `X由来` 这类**名词解释与概念铺垫**查询;每条查询词必须含**具体主体 / 时间 / 数字 / 事件名**。

**不允许**一次性规划完整 queries.json 后批量跑完,必须迭代式进行:

1. 按发散逻辑先构造 **1 条**查询执行(`scripts/search_many.py <queries.json> <outdir> [--db zhihu|global]`,单条:`[{"rank":N, "query":"...", "db":"zhihu|global", "search_db":"all|realtime|static", "filter":"...", "note":"发散点"}]`)
2. **读搜索结果**,从结果中发现新线索(新人物/新案例/新角度)→ 据此调整并生成下一条查询词
3. **由搜索不断调整搜索内容,动态调整**,每轮检索前先做收敛性判断(见上),至收敛即止
4. 每个发散点保留:`type(案例/人物/链路)` + `content(提炼要点)` + `url(来源)` + `note(发散点)`;**同一类型案例不超过 3 个**

### 其他(不变)

- **URL 定向(强制)**:原问题(标题/URL/全部回答)完整保留,发散不改变原问题;每个发散点必须附真实来源 `url`(取自搜索结果中的原文链接),无来源的推断在 content 中标注「推断」,禁止伪造链接。
- **输出** `raw/<day>/extension.json`(由 `merge_extension.py` 按链展平:链是结构,`items` 是展平结果,两者同时存在):
  ```json
  {"1": {"rank": 1, "title": "...", "url": "...", "category": "...",
         "chains": [{"claim": "想法", "takeaway": "落点",
                     "evidence": [{"relation": "印证", "type": "案例",
                                   "content": "...", "url": "...", "note": "..."}]}],
         "items": [{"relation": "印证", "claim": "想法", "type": "案例",
                    "content": "...", "url": "...", "note": "..."}],
         "thinking": "发散思考过程(该问题值得延伸的方向与关联)"}}
  ```
- Excel「热点拓展」sheet:`日期 | 排名 | 问题标题 | 扩展类型 | 扩展内容 | 来源链接 | 备注 | 发散想法 | 关系`;链式渲染会额外产出「**想法**」与「**落点**」两类行(扩展类型列标出),证据行的「关系」列给出 印证/反驳/边界。**有链接就附上**:想法行的来源链接列是该想法的出处回答(可点击,备注列写明「回答 N·M 赞」),落点行的来源链接列列出本链全部来源。末两列为新增,追加在末尾以保证历史日期的行不错位。最新日期块在最上,跨日期自动累积。
- 范围硬约束:**处理热榜前 20 名(全部条目)**;主流程四维分析与情绪标注同样覆盖全部 20 条。
  (2026-09-13 起由"仅前 10"改为全部, 见本节开头的范围变更说明; 发布仍只取前 `PUBLISH_TOP_N`=15 条。)

## 踩过的坑(1-68,勿重蹈)

**主题索引(2026-09-13 新增)** —— 坑很多, 按"你会怎么踩到"归类, 便于定位:

| 主题 | 坑号 | 一句话 |
|---|---|---|
| **账号对外动作(发布/关注)** | 59, 64, **66**, 60, 61 | 开放平台无发布接口; 点完不等于发出去; **平台配额是日/周上限(每天只发前 15 条)**; 别在"编辑已有回答"状态下发布 |
| **校验器/校验方法本身会错** | 65, 57, 30 | 校验结果大面积不符时先怀疑校验器; subagent 会误诊校验器(还白跑 4 轮); 约定散落多处则漏改不报错 |
| **subagent 协作与自述** | 29, 34, 43, 62, 46 | 不信"已校验通过"自述; 派发前 `ls` 核对环境(别凭记忆断言); schema 示例里的占位文字会被照抄 |
| **数据模型换代要兼容** | 56, 39, 15 | 新旧字段两套并存, 别直接替换; 后处理打标要传播到全部引用位置 |
| **URL / 链接纪律** | 42, 44, 55, 33 | 去跟踪参数; **同一 url 挂多条不同内容会串标**(占位/跳转页是元凶); 探活失败≠来源失效 |
| **抓取与数据源** | 26, 27, 33, 40, 41 | 网页接口 include 不能塞默认字段; order_by 不真排序; 瞬时 403 要重试; 单问题元数据 403; 重跑别删追加条目 |
| **成本与流程编排** | 10, 48, 63 | 收敛判据别太松(实测跑 17 轮); 多步流程要有编排脚本 |
| **分析与写作** | 50, 57, 58, 6, **67**, **68** | 情绪判据先定死; 语言要求逐轮收敛(省字只许从例子里省); 分析必须按 URL 对齐; **别把"数据管道的产物"学成"写作习惯"**; **自我学习 loop 必须三段分工** |
| **环境/编码/工装** | 1, 2, 3, 8, 18, 20, 25, 49 | PS 引号与 BOM、CLI 输出 BOM、`python -c` 陷阱、中文控制台 GBK、read 单行 2000 字上限 |
| **话题库** | 17, 36, 37, 46 | 只改 index.json(禁手改 md); FTS5 必须 trigram; 全量重写要原子替换 |

> 本次(2026-09-13)新增的是 **44–68**, 其中 **64(发布假成功 + 平台限流)** 与 **65(校验器自身出错)**
> 是代价最大的两个: 前者让我先报了一次"18 条全部发布成功"的错误结论, 后者让 14/15 条已发布内容
> 被误判为"不一致"。**67(把管道产物学成写作习惯)** 与 **68(学习 loop 三段分工)** 是书写 skill 这条线上
> 新增的两个, 属"方法论级"教训 —— 搬到别的平台仍然成立。

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
14. **Cookie 整串复制,勿手工誊写**:z_c0 等长串含 `|` 与签名段,人工誊写会截断(实测把签名段写丢、登录态失效,补全全失败)。改用 playwright-cli 的 `cookie-list --raw` 自动提取,零誊写(Step 1.2 方式 A)。**Cookie 不再用完即删**:按用户 2026-09-11 指示改为"长期保留复用、只在运行失败后才刷新",因此收尾**不删**;失效的显式信号是 fulltext 大量 truncated/summary 或网页接口 403,届时覆盖刷新即可。
15. **全文补全后分析必须复核**:摘要版四维分析可能与全文有出入(实测 98 条中 1 条情绪判断改判)。补全后 Agent 重读全文逐条核对 analysis.json(约束二),再重跑 check → fill_excel → gen_html,并校验 HTML 中「接口摘要」标签清零。
16. **Swarm 并发文件冲突**:多 subagent 并行发散时,查询文件与输出目录必须按 rank 隔离(`queries_rank_<n>.json` + `ext_search/<D>/rank_<n>/`),禁止共用单个 queries.json / ext_search 根目录。**输出文件名曾按「queries 内该 rank 的条目序号」生成,每轮只写 1 条时恒为 `rank_0N_1.json`,第二轮起静默覆盖上一轮的检索依据**(2026-09-12 实测,事后无法溯源);现改为**按目录内已有最大编号继续递增**,不再覆盖。若手工管理输出目录,请勿删除历史 `rank_0N_*.json`。
17. **话题库跨日期去重**:新日期发散前必须用 `topic_lib.py search --url/--keyword` 查重,同主题案例已收录的不重复搜索、不重复收录;同一分类同主题案例 ≤3,超出后新案例只进 thinking 不进条目。**只改 index.json,md 由 rebuild 重建,禁止手改 md**(手改会漂移)。
18. **`python -c` 引号陷阱复发**:任何含引号/中文/字典的 Python 代码(即使短)也写脚本文件运行——PS 5.1 会剥引号或转义错误(实测补 category 字段时 `-c` 内联失败)。
19. **CLI 二进制可能消失而凭证仍有效**:实测 `%LOCALAPPDATA%\ZhihuCLI` 整个目录被清理,但 Windows 凭证库中的 `zhihu-cli:access-secret` 仍在——重装 CLI 后 `auth status --verify` 直接 `valid`,**无需重新申请 Secret**。故抓取前先 `Test-Path` 验证 CLI 存在;不存在时先看 `zhihu` skill status 的 `auth.keychain_present`(为 `true` 即凭证可复用),不要急着向用户索要 Secret。`zhihu` skill 的 status 已修正为不再无条件报 `configured=false`。
20. **`check.py` 曾输出「假失败」**:`print("✓ ...")` 在中文 Windows 控制台(GBK)抛 `UnicodeEncodeError` 并以退出码 1 结束,让「校验通过」看起来像失败(表现:先打印"校验: N 问题, M 回答"然后 Traceback)。现已强制 UTF-8 输出并改用 `[OK]`;同类脚本也应照此处理。
21. **fulltext 单条失败要加强**:网页 API 偶发 HTTPError 会让回答退化为 `summary`(实测 86 条中 1 条)。脚本现已内置每条 3 次退避重试(`--retry`/`--backoff`),失败原因写入该条的 `error` 字段;重跑脚本(不带 `--force`)只重试非 full 条目。
22. **subagent 会在工作目录留临时文件**:实测 `ext_search/<D>/` 下出现过 `_runq.py`/`_verify.py`/`_dedup_check.py`/`search_raw/`/`rank_01_1..6.json`/`q0*_*.json` 等。收尾时**应删除临时 `.py` 脚本**(污染目录、干扰后续判断),**搜索中间结果 json 建议保留**以便追溯每条发散点的依据;`rank_<n>.json` 与 `queries_rank_<n>.json` 是流程产物,必须保留。
23. **跨天续接的会话里旧记忆整体失效**:实测会话从 08-16 续到 09-11 时,「今天」已变、ROOT 也已从 `D:\claude code\知乎动态跟进` 迁到 `D:\知乎动态跟进`。每次执行都必须**重新取当前日期**并**重新解析 ROOT**(见 Step 1.3),绝不沿用会话早前的值,否则会把数据写进废弃路径或错误日期目录。
24. **CLI 路径规则必须与基础栈同源**:修复前 `run.py` 与 `search_many.py` 各自硬编码 `%LOCALAPPDATA%\ZhihuCLI\...`,**不支持基础栈早已支持的 `ZHIHU_CLI_HOME`**——用户一旦自定义安装位置,基础栈能用而 hot-track 找不到(路径分叉)。现统一到 `scripts/zhihu_env.py`,解析顺序与基础栈一致,并在推导失败时兜底询问 `run.ps1|run.sh status` 的 `binary_path`。**新增任何调用 CLI 的脚本都必须 import 该层,禁止再写绝对路径**。另:对基础栈的本地修补(如给 run.ps1 增加凭证字段)会随其升级被覆盖,故 hot-track 的凭证判断改由 `zhihu_env.keychain_present()` 自行探测系统凭证库,不依赖该修补。
25. **Cookie 文件带 BOM 会让 HTTP 请求直接崩**:PowerShell 5.1 的 `Set-Content -Encoding UTF8` **会写 BOM**,使 Cookie 串首字符变成 `\ufeff`,放进 `urllib` 的 header 时报 `UnicodeEncodeError: 'latin-1' codec can't encode character '\ufeff'`(2026-09-11 实测踩到,现象是"网页接口全部失败"但其实是本地编码问题)。写 Cookie 必须无 BOM(用 `write` 工具,或 `[IO.File]::WriteAllText($p,$s,(New-Object Text.UTF8Encoding($false)))`);读端一律 `encoding="utf-8-sig"`,这样带不带 BOM 都能读。
26. **网页接口的 `include` 不能塞默认字段**:`api/v4/questions/{qid}/answers` 的 `include` 里若混入 `id`/`url`/`author.name` 这类**默认字段**的键, 会让 `voteup_count` 变成 `None`(表现:抓到回答但**赞数全是 0**)。只能写需要额外注入的字段, 实测可用组合:`include=data[*].voteup_count,content,data[*].comment_count`;不传 include 则连 `content` 都没有。
27. **`order_by=voteup` 并不按赞降序, 单页也不含全部最热**:实测与 `default` 同序;2026-09-11 的 rank4 那条 17503 赞回答**不在网页首 20 条内**,只有搜索召回拿到过它。因此必须三管齐下:① 在返回集合内**自行按 `voteup_count` 排序**;② `--pages` 多取几页;③ 与搜索召回取**并集**而不是二选一(并集正是把 rank1 从 51 赞提到 780 赞的关键)。
28. **发散搜索最容易退化成「名词解释」**:subagent 在找不到具体事实时,会本能地搜 `X是什么` / `X定义` / `X科普` 去"补背景",产出正确的废话。用户 2026-09-11 明令禁止(约束五):查询词必须含**具体主体/时间/数字/事件名**,背景一律用**过往案例与可核数据**支撑。主 Agent 汇总前抽查 `queries_rank_<n>.json` 与逐轮归档,发现命中即要求重发。
29. **`merge_extension.py` 的局部运行会整体覆盖输出**:实测 subagent 为自校验跑 `--ranks 9-10`,使 `raw/<D>/extension.json` 只剩 3 个 rank(其余 rank 的块全丢)。现已加固:当 `--ranks` 为子集且输出文件已存在时,**默认保留未处理 rank 的旧块**并发出警告,整体重写需显式 `--force-overwrite`。规范做法仍是:**等所有 rank 落盘后跑一次全量 merge**。
30. **约定散落多处 ⇒ 漏改不报错,只在运行期现形**:`"hot.json"` 曾出现在 6 个脚本、情绪三值出现在 4 个、HTML 标记出现在生成与校验两侧。漏改的表现是「文件找不到」或「校验莫名失败」,而非报错。现全部收敛到 `scripts/contract.py`(见「脚本间契约」一节);**新增脚本禁止再写这些字面量**。
31. **`fill_excel.py` 的热点拓展表会逐次累积重复表头**:旧写法 `delete_rows(2, max_row)` 只清数据行、保留第 1 行旧表头,`append(EXT_HEADERS)` 又把新表头写到第 2 行;更糟的是下次运行时那行残留表头首列是「日期」≠ 当日,被当作"其他日期的数据行"再保留一次——实测 2026-09 表里积了 4 行重复表头。现改为**先清空整表(含表头)再写表头**,并过滤首列为空或为「日期」的旧行。教训:凡是「保留旧行 + 重写当前日期」的表格操作,必须把**表头行本身**排除在"旧数据行"之外。
32. **PS 5.1 按 ANSI 读无 BOM 的 .ps1**:含中文的临时回归脚本若存成无 BOM UTF-8,`powershell -File` 会以 GBK 解码,报 `Unexpected token` 而非执行。用 `[IO.File]::WriteAllText($p,$s,(New-Object Text.UTF8Encoding($true)))` 存带 BOM 版本(与坑 2 同源);或直接改用 Python 写回归脚本。
33. **问题维度接口的瞬时 403 会被静默兜底,连覆盖率一起丢**:`question_fetch.py` 连续请求 20 个问题 × 3 页后,知乎网页接口会偶发 403(限流),而**同一 Cookie 单独请求同一问题立刻返回 200**(2026-09-12 实测:rank5 记 HTTP 403 并降级为 `search_fallback`,该问题因此既丢主数据源、也没了 `total_answers/coverage`——覆盖率标注的依据)。现已在**请求单一入口** `get_json()` 加默认 3 次退避重试(`--retry` / `--backoff`,第 n 次等 n×backoff 秒),单问题只在真正连续失败时才降级,并把 `已重试 N 次` 写进 `fetch_error`。**判据**:若跑完看到 `source=search_fallback`,先看 `fetch_error`——是 403 就重跑本步(不要急着换 Cookie),别把它当成 Cookie 失效。
34. **「案例」类条目会退化成同类个案的堆叠**:实测 2026-09-12 的 rank2 并列「祁东店主无责赔1.9万」与「彭宇案索赔13.6万」、rank5 并列「山西铁头13人落网」与「松哥打虎20余人」——两组各自讲的是**同一类问题**(善意介入被索赔 / 同批打假网红被刑事收网),换成其中任一条论点强度都不变,属于为凑条数反复搜索。用户 2026-09-12 明令:**案例支持类除非存在极大差别,否则只采用一条,不反复搜索**;被舍去的案例写进 `thinking` 并以「未采用但值得记录——」起头。判据见「收敛性判断」第 4 条。收敛此类条目后要**同步改 `ext_search/<D>/rank_<N>/rank_<N>.json`**(否则将来重跑 `merge_extension.py` 会把被合并的条目带回来),再跑 `topic_lib prune` + `update` 与下游 `fill_excel` / `gen_html` / `verify_html`。
35. **扁平条目列表 + 一大段 thinking ⇒ 交付物读不出论证结构**:旧格式把「洗衣机抽样」「河南病例」「灭活参数」并排堆着,读者无法判断哪条在支持哪个论点、哪条在反驳它(用户 2026-09-12 原话:「没有形成结构化分析的框架…目前太乱了,要求条目要清晰」)。现固定为**发散链**:`想法(claim) → 证据(逐条 relation=印证/反驳/边界) → 落点(takeaway)`,HTML 用金色链块渲染(证据行带彩色关系标签、thinking 收进折叠区),Excel 用「想法/落点」行 + 「关系」列表达同一结构。**注意 `边界` 是最高频也最易漏的一类**(「对,但仅限…」);每条证据只能归入一条链;旧 `items` 格式仍兼容,但只回退成"无想法的证据堆"。
36. **FTS5 默认分词器检索不了中文子串**:`fts5` 不显式指定 tokenizer 时用 unicode61,它把连续中文整段当一个词——建索引 `上海市疾控中心抽查128台家用洗衣机…`,查「洗衣机」命中 **0**(实测)。中文子串检索必须 `tokenize='trigram'`(SQLite ≥3.34;本机 3.45 实测「洗衣机」「霉菌检出率」「上海市疾控」均命中)。注意 trigram 要求查询串 ≥3 字符,短词退回 `LIKE`。
37. **话题库 update/prune 是全量重写,必须原子替换**:这两个命令都是"读 index.json → 改 → 整体写回",直接 `open(w)` 时若中途报错(如 Windows 上文件被 Excel/编辑器占用、磁盘写满)会把整库写成半截。现统一走 `atomic_write()`(写 `.tmp` 再 `os.replace`)。同理:`search` 会自动重建 sqlite 加速索引,若索引文件被别的进程占用会失败——此时删掉 `index.sqlite` 即可(它是派生物,`reindex` 随时重建)。
38. **中文关键词的两个正则陷阱(都在信源门槛里实测踩到)**:
    ① **子串误命中**——裸写 `据称` 会把「CIA数**据称**其保留战前70%」判成匿名归属,把一条外媒引述错标成「不采信」。必须加否定环视:`(?<![数据根依论票证])据称`。
    ② **数字匹配过宽**——用裸数字(如 `60`)在检索归档池里找印证,一条证据能"匹配"出 **243** 个来源组,全是巧合。必须用**完整 token**(`60.2%`、`5839万`)匹配,且只采信"特异数字"(≥3 位,或带金额/百分比单位)。另外别用 `len(digit)>=2` 过滤锚点——那会把「定损**4万**至5万」这种一等锚点丢掉;`数字+多/余/约+单位`(`900多万元`)也要覆盖。
39. **复核字段必须同时落到 `items` 与 `chains[].evidence`**:`verify_ext.py` 首次实现只给展平的 `items` 打标,而 Excel/HTML 渲染读的是 `chains[].evidence`——JSON 往返后二者是**不同对象**,结果交付物上等级标签数为 0,而话题库(读 items)却有等级。凡是"后处理打标"都要显式传播到全部引用位置。**另**:复核已并入 `merge_extension`(写出后自动调用),不再存在忘记执行的失败点;单独补跑用 `verify_ext.py` 即可。
40. **单问题元数据接口 403,标题要从 answers 结果里取**:`api/v4/questions/{qid}` 直接请求实测 **403**(带 Cookie、带问题页 Referer、加 `include=title` 都不行);而 `api/v4/questions/{qid}/answers` 的**每条结果自带 `question.title`**(2026-09-12 实测)。`question_fetch.fetch_question` 因此改为返回 `(answers, total, title)`,`question_add.py` 不再单独请求标题接口。另:`kind_of` 把回答链接识别为 `answer`,追加追踪时会**折算到它所属的问题**(追踪问题才有拓展价值)。

41. **重跑 run.py / question_fetch.py 会静默删掉追加条目(数据丢失)**:这两个脚本都按 hot.json 重建 answers_summary.json,而追加问题(rank 21+)**不在 hot.json 里**——实测若在追加后再跑一次任一脚本,rank 21 会被无声删除(它已在 analysis.json 与 extension.json 里,于是 check 会以「analysis 多余」形态暴露,或直接静默丢数据)。现两者都会**保留 extra=true 的条目**并打印 [info] 保留 N 条单问题追加条目。**凡"按榜单重建当日数据"的脚本都要保留 extra 条目**,这是新增脚本的检查项。
42. **分享链接带跟踪参数,会一路带到交付物**:用户从 App 复制的问题链接形如 `/question/2081001656066504241?share_code=rASK3M7YnZl9&utm_psn=2082191529167401174`。直接入库会让 Excel/HTML 里的"原问题链接"始终拖着一串跟踪参数(话题库因按 url 去重会隐式规范化,所以更隐蔽——库里去重了,交付物却没去)。现统一 `contract.canon_url()`(去 `?/#` 之后内容并去尾斜杠),`question_add` 入库前即规范化,`topic_lib.norm_url` 与之同源。
43. **schema 示例里的前缀会被照抄, 交付物就出现「落点：落点：」**:我在链式 schema 的示例里写了 `"takeaway": "落点：这条链最后说明了什么"`, subagent 直接**把示例当模板抄**(rank 21 实测 4 条 takeaway 全带「落点：」, 4 条 claim 带「回答区判断：」), 而 gen_html 渲染时又加一次 `<b>落点：</b>` → 页面上出现「落点：落点：…」; 另有 7 条 note 被写成「标「边界」：…」「标「印证」并给出机制锚点：…」——把 relation 说明当成了正文。**两头都要治**:① 示例里不再出现可照抄的前缀(改为「…；【不要写「落点：」前缀】」);② `merge_extension.strip_label()/strip_note_label()` 在入库时**自动剥离**这类前缀并告警(交付物因此永远干净)。教训:**给 LLM 的 schema 示例, 任何"看起来像内容"的占位文字都会被写进数据**。

44. **事实性复核的结论只按 `url` 缓存 ⇒ 同 url 不同内容互相串标**(2026-09-13 实测, 真实 bug):`verify_ext` 原先用 `annotations[url]` 缓存判定, 而**同一 url 可以挂多条互不相关的证据** —— 澎湃的占位链接 `m.thepaper.cn/wifiKey_detail.jsp` 被 rank4/5/9 的 **3 组共 6 条**无关证据共用, 于是"先被看到的那条"的结论被盖到其余各条上:rank9 一条 `named=True`、锚点=8、按规则应为 **A** 的判例(刷量判罚 896万/100万元)被标成 **D**,而交付物上就带着灰色标签。现按 **(url, content 指纹)** 缓存;`merge_extension --lint` 同时新增「同一 URL 挂了 N 条不同 content」告警(必须用 `contract.canon_url()` 归一键, 否则一条带 query 一条不带就看不出是同一 url)。**教训:凡"按 key 缓存派生结论", key 必须覆盖结论所依赖的全部输入**。
45. **信源等级只数数字锚点 ⇒ 系统性误杀制度性事实**:锚点原先只数"带单位的数字",于是「湖北省纪委机关、省委组织部…六部门**联合通报7起**…王某被判**有期徒刑一年六个月**」和「**国务院办公厅**2025年1月3日**印发**《关于严格规范涉企行政检查的意见》」这类一等一的事实性证据, 因数值锚点只有 0–1 个被判 `D·观点`。现锚点 = 数值锚点 + **制度性锚点**(法规条号/案号/人民法院案例库入库编号/《文件名》+印发·施行/判例通报), 一天内 D 从 33 条降到 24 条(其中相当部分是**本当为 D** 的具名主张)。修完覆盖率:A 85 / B 2 / C 1 / D 24(112 条独立证据)。
46. **`entities` 是"可选但推荐"⇒ 实测 0 条落库, 且两道静默**:① subagent 全都没填(schema 写"推荐"就等于不填);② 更隐蔽的是 `merge_extension.check_item()` **把返回值写死成固定 6 个键, 填了也会被丢掉** —— 所以就算有人填也进不了库。后果是话题库 `search --entity`「这家公司/这个人还出现过几次」彻底失效且无人报警。现:entities 改为**必填**(prompt 模板强制)、`check_item`/`normalize_dropped` 原样保留并规范化、rank 缺失率 >50% 时 merge 告警、`verify_ext.extract_entities()` 按主体形态兜底自动抽取并标 `entities_auto`(本次补了 26 条)。**教训:「可选但推荐」的字段等于没有字段, 必须有校验或兜底。**
47. **复核统计口径把同一份内容算两遍**:`items` 是 `chains[].evidence` 的**展平镜像**(坑 39), 旧输出把它们相加报「复核 **183** 条证据」, 而真实独立证据只有 **112** 条(链内 71 + 未采用 41)。现报告写「复核 112 条独立证据(链内 71 + 未采用 41; items 71 为链内镜像, 不另计)」。**凡是镜像/派生物, 统计时都必须点名排除。**
48. **`type` 触顶没当停止条件 ⇒ 检索超跑 3 倍**:见「收敛停止判据」。
49. **`read` 工具**单行上限 2000 字符**:长回答按原样落盘会被截断, 逼出额外的"取尾部"轮次(实测白读一次 10k 字符的重复内容)。主 Agent 渲染回答给模型看时, 应按 **1200–1500 字硬换行**再落盘, 一次读全;不要去猜"读到哪被截了"。
50. **情绪判据必须先定, 否则跨批次口径漂移**:skill 只要求「判断与描述一致」, 没给判据, 我边做边改(讥刺算消极还是中立? 说理中的批判呢?), 到第 3 批才稳定 —— 同一个 100 条数据集里的标签因此不完全可比。**这条教训在 2026-09-13 换多元模型后依然成立**, 且更重要(标签从 3 值变 12 值, 边界更多); 现判据写在「约束三」与「分析要求」里, 开工前先把那几行贴出来。
51. **约束五抽查要在运行中做, 不能只信自述**:本次是事后补做的。见「约束五 执行要求」。
52. **模板就是约定来源, 别按自己的习惯命名**:`prompt_swarm.md` 用 `{rank}`(不补零), 我却按 `rank_01`/`queries_rank_01.json` 建目录、生成完才发现与 `merge_extension` 读取的 `rank_<n>/rank_<n>.json` 和历史目录(09-12 为 `rank_1`)不一致, 白返工一轮。**目录内检索留档才是补零的**:`rank_01_1.json`(search_many 产出)—— 别被它带偏。生成前先 `ls` 历史日期核对。
53. **链接探活会被瞬时抖动放大成"死链"**:同一批 url 两次运行分别报 **4** 条与 **24** 条失败(HTTP 522 / TimeoutError, 站点侧 Cloudflare 抖动), 而 `gen_html` 把非 200 一律渲染成「来源已失效」——等于给活链接贴死链标签。现探活内置重试(5xx/超时/连接错误退避重试 2 次;4xx 视为确定性结果立即返回)。

54. **FTS5 的 `表名 MATCH` 特例掩盖了一个 JOIN 别名 bug**(2026-09-13 修):`topic_lib` 的检索 SQL 是 `JOIN fts f ON f.url = e.url`,WHERE 里写 `fts.entities MATCH ?` —— 给了别名 `f` 之后**原表名不能再作列限定符**,直接报 `no such column: fts.entities`。实测四种写法: `fts.entities` ✗ / `f.entities` ✓ / `fts MATCH` ✓ / `f MATCH` ✗ —— 也就是说**关键词检索一直能用**(FTS5 允许 `表名 MATCH` 这种特例语法),而 `--entity` 从写下就是坏的,只因 `entities` 长期为空、这条路从未被走到(坑 46)才没人发现。现改为 `f.entities MATCH ?`。**教训:一条从未被实际执行的分支,等于没验证过** —— 修好上游数据(entities 有人填了)会立刻把下游的沉睡 bug 打出来。
55. **「探活失败」不等于「来源失效」**:`gen_html` 旧逻辑把**一切非 200** 都渲染成「来源已失效」,而一次探活上百条 url 时知乎侧 Cloudflare 会成片返回 522(实测一次 22 条),等于给大批活链接贴死链标签。现区分:**4xx(除 429)才判失效**并显示红色「来源已失效」,5xx/超时/连接错误显示中性的「探活未成功」。判据常量在 `contract.EXT_LINK_DEAD`。
56. **字段模型换代必须"两套并存", 不能直接替换**(2026-09-13 情绪三元→多元化实测):把 `judge` 直接换成 `emotion_tags/intensity/target` 看起来最干净, 但立刻踩三处 —— ① 历史日期(08-21·09-11·09-12)的 `analysis.json` 只有 `judge`, `fill_excel` 里 `[A[f] for f in ANALYSIS_FIELDS]` 会 `KeyError` 直接崩; ② `check.py` 若只认新字段, 对历史日期跑校验全红; ③ HTML 渲染 `A["judge"]` 硬取同样崩。做法:**主体字段提成 `ANALYSIS_CORE` 两套共用**, 情绪字段各留一套(新的 `ANALYSIS_FIELDS` / 旧的 `ANALYSIS_LEGACY_FIELDS`), 渲染与校验都写成"有新字段走新的、只有旧字段走旧的"(`gen_html.emotions_of()`、`fill_excel.emotion_cells()`、`check.py` 的三分支), `verify_html` 还加一条「新旧模型未串用」的对账。**收益:历史日期一条数据没改、页面照旧能出**(实测 09-12 仍 10/10 通过), 代价只是几个兼容分支。另:每天一个 sheet、各自表头, 所以 Excel 从 16 列变 18 列**不会让历史行错位** —— 与「热点拓展」那种跨日期累积的单表不同, 后者加列必须追加在末尾。
57. **情绪判断下放 subagent 前必须先测一致率**(2026-09-13 实测):把 rank 1/20 的 10 条交给 subagent 重判, 与主 Agent 自己判的**只有 2/10 完全一致(20%)**, 差异集中在四处: `讽刺` vs `调侃`、强度标定(同一个梗 2 还是 4)、抽象评论的指向、`失望`/`无奈`/`忧虑` 的细分。注意**这不是"subagent 乱标"** —— 有具体攻击对象的文本两边完全一致(含 4098 赞那条), 分歧全在抽象、无明确对象、纯玩梗的文本上, 说明是**我的判据欠定义**。修法:①在 `prompt_emotion.md` 写四条硬裁决(讽刺/调侃用"读者会不会认为作者在骂谁"一问判定;强度锚点;指向优先序"取最具体的那一个";负面情绪四选一);②**新增必填 `why` 字段**(每个标签各一句 ≤20 字触发依据), 让分歧可逐条复核。**结论:可以下放, 但纯下放会得到"每批一把尺子"的标签 —— 保留主 Agent 对不一致项的复核(只复核分歧, 成本很低)。**
58. **语言要求会来回摆动, 要按"反馈方向"逐轮收敛而不是一次到位**(2026-09-13 拟答稿实测三轮):①第一版 1084 字、带链接、「先给结论：」开场 → 用户:太 AI、要压到 500 字以内、不要带链接、允许暴论、纯路人视角不立人设;②第二版压到 493 字, 结果**压成了电报体**(「需求侧一样。6.96 亿、677.9 亿、518.32 亿。时间投给快反馈了。」) → 用户:**语言要讲清楚讲明白, 可以少用例子, 但观点一定要明白**;③第三版 481 字, 把删例子省下的字全部用于补全因果, 每段"结论→为什么→所以怎样"。**教训:字数上限和讲清楚是相互挤压的, 必须明确"省字只许从例子里省, 不许从讲道理里省", 并且给"专有名词要么一句话交代要么不用"的规则**(实测「全勇先承认审美滑坡…他更准」这种写法读者不知道他是谁)。模板里要放**反例清单**(把上一版被否的句子原文列进去), 比抽象描述有效得多。
59. **开放平台没有发布接口 —— 这是能力边界, 不要猜**(2026-09-13 核实):`zhihu-cli capabilities` 的全部命令里, `me/creator` 系列**全是 GET**(me contents/content/comments/stats、question answers/recommend、quota), 唯一写操作是 `knowledge upload`(上传自己的知识库文件), **没有任何创建回答/文章/想法的端点**;`answer` 子命令是"检索资料并生成知乎直答"(读+生成, 不是发帖)。所以拟答稿只能**人工复制粘贴**发布(推荐), 或走浏览器自动化驱动已登录网页端(技术可行, 但属**操作真实账号的不可逆对外行为**, 多半违反用户协议、有账号风险, **未经用户逐条明确授权不得执行**; 即使获准也应只填到编辑器、停在提交前由人工点发布)。**教训:凡"能不能代表用户对外动手"的问题, 先查 `capabilities` 这类机读事实源, 不要凭"应该可以"回答。**
60. **浏览器自动发帖: "看起来正常"的页面可能已经把正文叠了两遍**(2026-09-13 实测, 最惊险的一个坑):`run-code` 脚本跑两遍, 编辑器里就变成 **962 字 = 2×481** —— 但**截图看着完全正常**(段落顺序、排版都对), 只靠肉眼看截图就点发布会发出重复回答。两条硬要求:①**每次先 `Ctrl+A`+`Delete` 清空并回读确认归零**再插入(幂等); ②**发布前必须回读 `innerText()` 与草稿字数比对, 不等就拒绝发布**。另外**页面上的「字数」计数器会滞后**(实测填充后截图仍显旧值 962, 稍后才变 481)⇒ **以 innerText 为准, 别信计数器**, 否则会把已修好的状态误判成仍有重复。附带坑: `WriteAnswerButton` 被吸顶 header 拦截指针事件, 普通 `click()` 必超时 ⇒ `dispatchEvent('click')` 兜底; `run-code` 执行体是**单一函数表达式、不支持 require** ⇒ 正文只能内联进 JS(用 `publish_draft.py` 生成, 不要手抄)。
61. **发布前必须确认"是新回答"而不是"在编辑已有回答"**(2026-09-13 实测):页头出现「编辑回答」时一度以为用户已答过该问题 —— 若真是在编辑状态发布, 会**覆盖用户原答案**。判据:①底部按钮应是「发布回答」(编辑已有回答显示「更新回答」); ②`authorSample` 里不该有本账号; ③自己打字产生的**自动草稿**也会让页头出现「编辑回答/草稿备份」, 这不等于已有回答。另: **发布回答会自动关注该问题**(实测两条都变「已关注」), 属平台行为, 清尾见 `unfollow_question.py`(可选后续功能, 幂等)。
62. **派发前要核对文件真的存在, 不要凭记忆断言环境状态**(2026-09-13 实测):我在派发 rank 20 时写了"你早前已有一版 `rank_20.json`, 可复用"——**这是错的**, 原 Swarm 只跑过 rank 1-10, rank 20 根本没有旧版。子 agent 发现了并照实重跑全流程(8 轮检索), 代价白花。范围从 10 扩到 20 之后, 这类"哪几个 rank 有旧产物"的判断**必须 `ls` 一次再说**。
63. **交付链要固化成一条命令**(2026-09-13 实测):链路是 5 步且顺序敏感(情绪合并 → 汇总 → check → fill_excel → gen_html → verify_html), 手敲时容易漏步 —— 实测这一轮里出现过"改了数据但忘记重出 Excel/HTML"。现由 `run_pipeline.py` 一键跑完并逐关报错(失败即停, 标明是哪一关)。**凡是"多步且顺序敏感"的流程, 都应该有一个编排脚本, 而不是让人记步骤。**
64. **「点了发布」不等于「发出去了」—— 假成功 + 平台发布限流**(2026-09-13 实测, 一次踩两个):批量发 18 条时**全部 report 成功**, 但截图与线上核对显示**只有 13 条真发出去**。两个独立原因:① **脚本假成功** —— 原实现在点完「发布回答」后无条件 `published: true`, 而实际上点完 URL 不一定跳 `/answer/<id>`; 现以**「URL 是否变成 `/answer/<id>`」为判据**, 不成立就重试一次并如实回报 `published:false`。② **平台侧限流** —— 连发约 13 条后, 后续点击**完全无效**(`elementFromPoint` 确认按钮位置正确、真实鼠标与 Ctrl+Enter 都无反应、页面无提示); 其真实性质见坑 66(**日/周配额**, 不是短冷却)。**教训: 批量做真实账号的对外动作, 必须 ①每步可验证 ②限速 ③先小批试水再放量。** 另一处相关的坑: 失败重试时页面上已留有**自动草稿**, 页头按钮变成「编辑回答」, 只找「写回答」的脚本会因 `contenteditable` 一直不出现而超时 —— 打开编辑器要按 `写回答 → 编辑回答 → 草稿入口` 依次兜底。
65. **验证脚本自己也会错, 先自查再下结论**(2026-09-13 实测):核验 15 条已发布回答时, 第一版用 `.RichContent-inner` 的 `allInnerTexts()` 再取"最长者"当正文 —— 结果抓到的是**整页所有回答**(rank7 取到 5793 字/99 段), 于是 14/15 被判"不一致", 差点误报成线上内容出错。改成"按 answer id 定位自己的回答卡片 → 取该卡片的正文"后, **15/15 字数完全一致**。**教训: 校验结果与预期大面积不符时, 先怀疑校验器本身**(尤其像"所有样本都错"这种分布), 不要急着报故障。
66. **平台配额是"日/周上限", 不是短冷却 —— 必须按天设计发布节奏**(2026-09-13 实测): 自动连发 14 条后, 后续点击**完全无效**且页面上抓不到任何提示; 我误判成"频率限制、冷却 10 分钟即可", 结果人工补发时收到了真正的原文 —— 「您的回答过于频繁，**已达到本日或本周数量上限**。草稿已保存，请稍后重试」。**三个要记的点**: ① 配额提示是 **toast, 会自己消失**, 所以判断要在**点击后立刻扫页面文本**(等 6 秒再扫就抓不到, 会把配额失败记成含义不明的 `blocked`); ② 命中配额后**立刻停止整批**, 继续试剩下的条毫无意义; ③ 发布节奏按制度定死 —— 本流程取 **每天前 15 条**(`contract.PUBLISH_TOP_N`), 第 16 条起只出稿不发布(标 `draft_only`), **隔天续发只需重跑同一条命令**(台账自动跳过已发)。教训: **把"平台的节奏约束"写进契约层常量和文档, 而不是留在人的记忆里**; 否则每次都会以同样方式撞墙。
67. **提炼"写法规律"时, 必须先把"数据管道造成的假象"剔出去**(2026-09-13 实测, 差点学错): 4 个提取 subagent 独立报告 `answers_summary.json` 的 **`text` 字段没有换行符**(24/25 条正文内部无 `\n`), 于是有批次把「单段成文、不空行」写成了 freq=24 的"高赞普遍写法"。**但那是抓取/清洗的产物, 不是写作习惯** —— 若照此写入书写 skill, 后面所有回答都会被写成一大坨不分段。汇编时已剔除并在 skill 里显式写明"不能推出单段成文"。**教训: 任何"从数据里学规律"的环节, 都要先问一句"这个特征是作者的行为, 还是我的管道造成的?"** 同类风险: 抓取时统一去掉的空白/表情/图片、字段截断、排序规则改变, 都会被误读成"用户习惯"。
68. **"自我学习 loop"要三段分工, 不能一段包办**(2026-09-13 用户设计, 已落地): ① **提取端**(subagent, 分批)→ 只产出"书写逻辑与语言习惯", 铁律是**不涉及具体内容**, 用"改写测试"判定(这条规律套到无关话题上是否仍成立); ② **汇编端**(主 Agent,**奥卡姆剃刀**)→ 先由 `merge_style.py` 折叠近义、按维度归类、给跨批频次, 主 Agent 依频次取舍: **保留跨批复现与约束力最强的禁令, 删掉低频同义与空泛项**(本次 106 条候选 → 26 条规则 + 8 条禁令); ③ **书写端**(subagent)→ **不检索**, 只读书写 skill + 本 rank 的链证据成文。**为什么必须拆开**: 若让书写端自己"边写边学", 它会在规范定稿前先写一遍、必然返工; 若让提取端直接产出规范, 它会写进大量低频的个人偏好(实测有个别特征 freq=1, 只出现在单一作者身上)。**产物是跨日期累积的 `书写skill/书写skill.md`**(与话题库同构: 越用越准), 原始候选留档在 `ext_search/<D>/style*/`, 便于下次比对增减。

## 脚本清单(skill/scripts/,全流程通用)

| 脚本 | 职责 | 关键参数 |
|---|---|---|
| `contract.py` | **流程数据契约层**:文件名/目录布局/字段名/值域/HTML 结构标记的**单一定义处**,供全部脚本 import;无业务逻辑 | 作为模块:`path_*()` / `report_*()` / `page_name()` / `EMOTIONS` / `ANALYSIS_FIELDS` / `EXT_*` / `HTML_*` |
| `zhihu_env.py` | **基础技术栈适配层**:统一解析 CLI 路径(`ZHIHU_CLI` → `ZHIHU_CLI_HOME` → 平台默认 → 兜底问 zhihu skill 的 status)与凭证库状态;被所有业务脚本 import | 作为模块:`require_cli()` / `diagnose()` / `keychain_present()` / `skill_status()` |
| `doctor.py` | **环境与数据自检**:运行时/脚本完整性/基础栈(CLI+凭证+skill 版本)/ROOT/当日数据;`--discover` 自动发现候选 ROOT | `--root --date --discover --json` |
| `check_docs.py` | **组成清单一致性体检(只读)**:磁盘组件 ↔ `ARCHITECTURE.md` §二 分层清单 ↔ 本文件的脚本/模板表 三方比对(未归类/幽灵项/表内缺漏)+ 扫"改了范围却漏改别处"的旧表述。**改流程或新增脚本后跑一次**;退出码 1=不一致 | `[--skill-dir] [--scope-pattern] [--json]` |
| `run.py` | 热榜 + 变体搜索 + 合并去重(关键词召回, 作兜底数据源) | `--root --date --limit --variants --resume` |
| `question_add.py` | **单问题追加追踪**:把单独搜的一个问题注册成当日追加条目(rank 接在榜单之后)、抓高赞回答并入 answers_summary、登记 extra_questions.json、**自动生成 subagent 提示词**(prompt_swarm.md 模板);链接自动规范化、跨日期重复追踪会告警;hot.json 缺失也能用 | `--root --date --url [--top] [--pages] [--rank] [--emit-prompt] [--no-cross-day-check] [--dry-run]` |
| `question_fetch.py` | **问题维度抓取**(主数据源):网页接口按赞取每问题最热 N 条, 与搜索召回取**并集**, 适配 Question/Article/Answer 三类条目, 写入 `total_answers`/`coverage`/`source`; 请求级退避重试(防瞬时 403 被静默降级) | `--root --date --top 5 --pages 3 --out --no-merge --retry --backoff` |
| `fulltext.py` | 回答全文补全 + 截断检测(每条自动重试 3 次、失败原因写入 `error`;`--cookie` 解锁全文) | `--root --date --delay --retry --backoff --force --cookie` |
| `search_many.py` | 批量发散搜索(热点拓展用,queries.json 驱动) | `queries.json outdir --db --delay --count` |
| `check.py` | 数据完整性校验(分析齐全/情绪字段值域/URL/内容/状态)。情绪**两套模型都认**:有 `emotion_tags` 按新模型校验(标签∈词表且≤3、强度 1-5、指向∈6类), 只有 `judge` 时按旧三元校验, 两者都无=漏标 | `--root --date` |
| `merge_extension.py` | **汇总 Swarm 产出** → extension.json:链式结构强校验(每条链 claim/evidence/takeaway、每条证据 relation 值域)、按链展平 `items`(供话题库)、type 值域 / 同类型≤3 / URL / 必填字段、容忍旧的扁平 `items` 与 `divergence_dirs` 变体、报告跨 rank 重复 URL 与**同一 URL 多内容**、`entities` 缺失告警、**`chains[].source` 与原答对账**;**`--lint` 只读模式**供 subagent 自查(不写文件、可单 rank 跑、有硬错误退出码 1) | `--root --date [--ranks 1-20] [--no-strict] [--lint]` |
| `verify_html.py` | **约束四自动校验**(详情页数/折叠数/翻页/入口/索引/接口摘要/**情绪渲染对账**/**拟答稿渲染对账**/拓展范围),退出码 0 即通过 | `--root --date` |
| `fill_excel.py` | 填月度 Excel(自动建模板、情绪三列(标签/强度/指向)+强度与指向下拉、截断备注、热点拓展 sheet、**拟答参考 sheet**);`emotion_cells()` 兼容新旧模型;每次运行刷新「说明」sheet | `--root --date --xlsx` |
| `gen_html.py` | 生成 HTML 展示页(原文状态标签、热点拓展块、**多元化情绪 chips/强度点/指向签/图例**、**✍️拟答参考块**);`emotions_of()` 兼容新旧模型 | `--root --date --out` |
| `gen_prompts.py` | **生成 subagent 提示词**(2026-09-13 新增,取代一次性脚本):`--ranks 1-20` 出拓展 `PROMPT.md`;`--emotion --per 5` 出情绪判断批次 `EMOTION_PROMPT_<tag>.md`;`--style --per 5` 出书写逻辑提取批次 `STYLE_PROMPT_<tag>.md`;`--write` 出书写批次 `WRITE_PROMPT_<tag>.md`;`--all` 全出。目录命名遵循历史约定(目录/查询文件不补零,检索留档补零)。**平台参数化**:顶部 `PLATFORM` / `UNIT` / `PLATFORM_NOTES`(可用环境变量 `TRACK_PLATFORM` / `TRACK_UNIT` / `TRACK_PLATFORM_NOTES` 覆盖)注入到 `prompt_style.md` / `prompt_write.md`,模板内无平台硬编码;改这三个常量即可搬平台 | `--root --date [--ranks] [--emotion] [--style] [--write] [--per] [--all]` |
| `prompt_swarm.md` | **拓展发散 subagent 模板**(热点拓展板块的派发提示词):问题类型判定(社会事件类/非时效类)、两条发散路线、三类首选查询构造式、**约束五(禁名词解释类查询)**、信源门槛、链式 schema 与自报格式。**2026-09-13 起不再含"附加产出:拟答参考稿"**(写稿职责已移出, 见 Step 4c) | 作为模板被 `gen_prompts.py` 填充(默认 `--ranks` 即出拓展提示词);`question_add.py --emit-prompt` 也用它 |
| `prompt_emotion.md` | **情绪判断 subagent 模板**(2026-09-13 新增):词表/判据/四条边界裁决(讽刺vs调侃、强度锚点、指向优先序、负面情绪四选一)/标定样例/必填 `why` | 作为模板被 `gen_prompts.py` 填充 |
| `prompt_style.md` | **书写逻辑提取 subagent 模板**(学习 loop 的学习端):10 个固定提取维度、**铁律"只提怎么写、不提写了什么"**(含"改写测试"判定法)、输出 schema(patterns/avoid/notes, 带 scope 与 freq) | 同上(`--style`) |
| `prompt_write.md` | **回答书写 subagent 模板**(学习 loop 的应用端):**不检索**, 读 `书写skill.md` + 本 rank 的链证据 → 写 `draft_<n>.md`; 内置用户三轮定稿的全部语言要求与反例清单 | 同上(`--write`) |
| `fix_chain_source.py` | **元数据机械修复**:`chains[].source` 的 `answer_index`/`url` 与原答错配时, 按随附的可核对字段(likes/url)反查正确引用并回填; 修不了的列出来交人。修完必须重跑 `merge_extension.py` + 交付链 | `--root --date [--ranks] [--dry-run]` |
| `merge_style.py` | **书写逻辑候选池汇总**: 折叠近义重复(同维度相似度≥0.62)、按维度归类、给跨批频次, 供主 Agent 用奥卡姆剃刀取舍 | `--root --date [--write]` |
| `publish_draft.py` | **把拟答稿填进知乎网页编辑器(可选发布)** —— ⚠️ **需用户明确授权**, 不接默认流程; 默认只填不发布, 内置"字数校验不过就拒绝发布"闸门; 详见 SKILL.md「本流程不发布」一节与脚本 docstring 里的 8 条实测坑 | `--draft <md> --out <js> [--publish] [--shot] [--shot2]` |
| `unfollow_question.py` | **可选后续功能**: 生成"取消问题关注"的 run-code 脚本(发布回答会自动关注该问题, 属平台行为); 幂等, 已是「关注问题」则跳过 | `--out <js>` |
| `publish_batch.py` | **批量发布 + 发布台账**(⚠️ 需用户授权, 不接默认流程): **默认只发前 `PUBLISH_TOP_N`(=15) 条**, 第 16 条起标 `draft_only`; 自动跳过台账里已发布的; 逐条生成脚本→goto→run-code→**以 URL 是否变成 `/answer/<id>` 判定成功**; **命中日/周配额提示即整批停止**并标 `blocked_limit`; 连续 N 条点不动也停; 状态写 `raw/<D>/publish_ledger.json` | `--root --date [--ranks] [--all] [--gap 75] [--cooldown] [--status] [--mark N=url] [--mark-manual 15]` |
| `make_manual_publish.py` | **人工发布兜底**: 把"应发但没发"的拟答稿整理成可直接复制的 md(问题链接+标题参考+正文代码块)。**省略 `--ranks` 时自动读台账**挑出 `blocked/blocked_limit/pending_manual` 且在前 N 条内的 | `--root --date [--ranks] --out <md>` |
| `merge_emotion.py` | **情绪片段合并 + 分歧对账**(情绪下放 subagent 的必备收尾): 结构校验(词表/≤3/不重复/强度1-5/指向6类/数组长度==回答数)+ 与 `analysis.json` 现有判定逐条比对(`--compare` 只出分歧, `--write` 合并, `--json` 机读); 写入时保留 `emotion_why` 供审计 | `--root --date [--frag a.json …] [--compare] [--write] [--json]` |
| `run_pipeline.py` | **一键跑完交付链路并逐关校验**: [情绪合并] → [汇总] → check → fill_excel → gen_html → verify_html, 失败即停并报是哪一关; **不跑 Swarm/不抓取/不发布** | `--root --date [--merge] [--emotion] [--no-links] [--skip-verify]` |
| `merge_extension.py` | **汇总 Swarm 产出 + 事实性复核(二合一)**:链式结构强校验(claim/evidence/takeaway、relation 值域)、按链展平 `items`、type 值域 / 同类型≤3 / URL、容忍旧的扁平 `items`、报告跨 rank 重复 URL;写出后**自动调用** `verify_ext.run()` 打信源等级/算多源印证/探活链接 | `--root --date [--ranks 1-20] [--no-strict] [--no-verify] [--no-links] [--link-delay]` |
| `verify_ext.py` | **发散证据事实性复核**(通常由 merge 自动调用, 也可单独补跑):信源门槛兜底打标(A/B/C/D,锚点=数值+**制度性**)、entities 兜底自动抽取、多源印证(当日检索归档池 + 3-gram 同源折叠识别洗稿)、链接探活(**5xx/超时退避重试**)、归档核对(url 是否真出自检索结果);结果写回 extension.json, 报告写 `raw/<D>/ext_verify.json` | `run(root, date, no_links, delay, quiet)` / CLI `--root --date [--no-links] [--delay] [--json]` |
| `topic_lib.py` | 话题库维护(定位:避免重复搜索的 database;维度区隔 type=一级全局索引 / cat=二级受控标签 / date=首次收录 / last_seen=最近命中):update 增量收录(url 去重 + 日期回填 + 同类体检告警)+ search 查重与筛选(url/type/cat/tier/日期区间/关键词/主体)+ rebuild 重建 md + reindex 重建 sqlite + prune 全库一致性扫描 | `update --root --date` / `search --root --url\|--type\|--cat\|--tier\|--entity\|--since\|--until\|--keyword\|--json\|--adopted-only` / `rebuild --root` / `reindex --root` / `prune --root` |

### 文档与产物清单(skill 目录内的非脚本件)

| 文件 | 层 | 职责 | 换平台时 |
|---|---|---|---|
| `SKILL.md` | — | 本文件:约束、流程编排、值与口径、踩坑 | 改 L2/L3 相关段落 |
| `ARCHITECTURE.md` | L1 | **架构与泛用性分层**:四层结构、28 脚本 + 4 模板逐件标注「属哪层 / 怎么复用」、四块最强泛用件、迁移指南、已知缺口 | **带走**(迁移时先读它) |
| `writing_method.md` | L1 | **书写方法(通用件)**:为什么三段分工、提取端的铁律与改写测试、汇编端的奥卡姆四条规则、**必须提防的"数据假象"**、应用端约束、累积与版本、复用清单 | **带走**(唯一被单独抽出的通用件) |
| `scripts/prompt_style.md` / `prompt_write.md` | L1 | 学习 loop 的提取端 / 应用端模板,**已参数化**(`{platform}` / `{unit}` / `{platform_notes}`) | 只改 `gen_prompts.py` 的三个常量 |
| `scripts/prompt_emotion.md` / `prompt_swarm.md` | L2 | 情绪判断 / 拓展发散模板(词表、判据、schema 与平台约束**强耦合**) | 需按新平台重写 |
| `<ROOT>/书写skill/书写skill.md` | **L4 产物** | **书写 skill 本体**(自我学习 loop 的累积结果,与话题库同构):26 条规则 + 8 条禁令 + 一页速查 | **不带**(在新平台重新学一遍) |
| `<ROOT>/话题库/` | L4 产物 | 跨日期累积话题库(index.json 机读 + md 人读) | **不带** |
| `<ROOT>/raw/<D>/` · `ext_search/<D>/` | L4 产物 | 原始存档 / Swarm 产出 / 学习 loop 留档 | **不带**(留作溯源) |

> **一句话记法**:`ARCHITECTURE.md` 回答"哪块能搬",`writing_method.md` 回答"书写这块怎么搬",
> **书写 skill 本体是学出来的、不是搬出来的**。

> **历史说明**:早期版本曾用 `api_fetch.py`(API 直拉 + top2 = 最高赞 + 最多评论)作为抓取首选,并配套 `top2_select.py` 做后置瘦身(把已抓取的全量回答压成每问题 2 条)。两者均已**移除**:抓取职能由 `question_fetch.py` 完全取代(并集召回 web ∪ search、覆盖度标注 `total_answers/coverage/source`、Question/Article/Answer 三类条目适配),条数控制改由 `question_fetch.py --top N` **前置**完成(后置瘦身会破坏 `analysis.json` 与 `extension.json` 已按回答序号对齐的结构);如需查阅可看 git 历史。**现行流程只有一条抓取链**:`run.py`(关键词搜索召回,作兜底)→ `question_fetch.py`(问题维度并集,主数据源)。

所有脚本路径全参数化(`--root` 默认当前目录),不写死任何绝对路径;日期目录 `raw/<D>/` 自动创建。分析步骤(analysis.json)由 Agent 完成,脚本负责抓取/校验/产出。
