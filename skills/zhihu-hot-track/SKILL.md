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
完整清单(27 个脚本 + 6 个提示词模板 = 33 件,逐个标注所属层与复用方式)见 **[`ARCHITECTURE.md`](ARCHITECTURE.md)**;
其中**书写能力(自我学习 loop)是唯一被单独抽成通用方法文档的一块**,见 **[`writing_method.md`](writing_method.md)**。

| 层 | 内容 | 换平台时的改动量 |
|---|---|---|
| **L1 通用方法论** | 契约层 `contract.py`、编排 `run_pipeline.py`、校验 `check.py` / `verify_html.py` / `verify_ext.py`、学习 loop(3c/3d/4c + `merge_style.py` + `prompt_style/write/gate/gate_pre.md` + `writing_method.md`)、累积库 `topic_lib.py`、待发帖列 `publish_queue.py`、委派的三条纪律 | **0 改动**(校验/编排/学习/委派/闸门的方法与平台无关) |
| **L2 平台适配** | `zhihu_env.py`、`run.py` / `question_fetch.py` / `fulltext.py` / `search_many.py` / `question_add.py`、发布后清尾(`unfollow_question.py` 的选择器;原 `publish_draft.py` 已随自动发帖删除,2026-09-16)、cookie 自愈(`extract_cookie.py`,2026-09-21)、`prompt_swarm.md` | 只改这一层:换榜单/内容/检索接口与 DOM 选择器 |
| **L3 交付** | `fill_excel.py` / `gen_html.py`(Excel + 分页 HTML 两个载体) | 换载体时替换这两个 |
| **L4 数据产物** | `<ROOT>/raw/<D>/`、`ext_search/<D>/`、`话题库/`、`书写skill/` | 不随代码走,**跨日期累积** |

**四块泛用性最强、优先复用的**(细节见 `ARCHITECTURE.md` §三):

1. **学习 loop** —— 提取(subagent 分批)→ 奥卡姆汇编(主 Agent)→ 应用(subagent 不检索)。
   换任何"要产出风格化文本"的场景都能整套搬走,只改 `{platform}` / `{unit}` / `{platform_notes}` 三个变量
   (由 `gen_prompts.py` 顶部的 `PLATFORM` / `UNIT` / `PLATFORM_NOTES` 注入,模板里不留平台硬编码)。
2. **证据纪律** —— 信源门槛(A/B/C/D, 锚点=数值+制度性)+ 论证链(claim → evidence[relation] → takeaway)。
3. **委派纪律** —— 给权威只读校验器(`--lint`)、不信自述、判定任务必须给评分细则 + 标定样例 + 必填 `why` + 分歧复核。
4. **对外动作纪律** —— 台账=唯一事实源、逐条可验证(回填真实链接)、三道闸门与每日上限写进契约常量、对外不可逆动作由人工终审(2026-09-16 起自动发帖已删,机器只到"待发帖列"为止)。

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

**换主题/换平台时改哪里(2026-09-14 修订)**:平台属性(平台名/内容单元/交付物命名/来源文案/域名类别/接口地址/URL 模板/检索库名/CLI 与环境变量名/凭证服务名)**全部收敛到 `platform_profile.py` 的平台档案**,换平台 = 填一份档案;采集实现改 `zhihu_env.py` + `run.py`/`question_fetch.py`/`fulltext.py`/`search_many.py`/`question_add.py`(L2),其余脚本(check / fill_excel / gen_html / verify_html / merge_extension / topic_lib)只处理「榜单条目 + 内容 + 分析 + 拓展」这套与平台无关的结构,**一行不动**。

### 换平台清单(照做即可,6 步)

| 步 | 动作 | 验证 |
|---|---|---|
| 1 | 在 `platform_profile.py` 的 `PROFILES` 里加一份档案(或先用 `TRACK_PLATFORM` + `TRACK_PLATFORM_NAME`/`TRACK_UNIT`/`TRACK_PLATFORM_NOTES`/`TRACK_REPORT_TITLE`/`TRACK_API_BASE`/`TRACK_REFERER`/`TRACK_SOURCE_DB` 等环境变量走"通用档案") | `python -c "import platform_profile as p;print(p.summary())"` 或 `doctor.py` 首行「平台档案」 |
| 2 | 若新平台有 CLI/凭证:填 `cli_name` / `cli_env` / `cli_home_env` / `cli_home_defaults` / `keychain_services` / `basestack_skill` | `doctor.py` 的 CLI 与凭证两项不再 FAIL |
| 3 | 实现 L2 采集:`run.py`(榜单+检索变体)、`question_fetch.py`(条目→内容列表)、`fulltext.py`(正文补全)、`search_many.py`(发散检索后端) | 用一个小 limit 跑一次抓取,看 `answers_summary.json` 有内容 |
| 4 | 模板与文案**不用改**:六个 `prompt_*.md` 已全部占位化,平台注记由档案 `notes` 注入 | 看 `gen_prompts.py` 产出的 `PROMPT.md` 首行是否为该平台名 |
| 5 | 跑守卫与体检:`check_docs.py`(平台字面量必须只剩 L2 组件里) + `doctor.py` | 两者退出码 0 |
| 6 | **重学 L4**:`话题库/` 与 `书写skill/` 不能跨平台搬;在**新的 ROOT** 里重新累积(方法照 `writing_method.md`) | 新 ROOT 首次运行后 `话题库/index.json` 与 `书写skill/书写skill.md` 生成 |

**回归方式(改任何脚本后照此验证)**:直接跑 `python scripts/regress_pipeline.py --root <ROOT> --date <D>` ——
它复制 `raw/<D>/`、`ext_search/<D>/`、`话题库/`、`书写skill/` 到临时 ROOT 重跑全链路
(`check` → `fill_excel` → `gen_html` → `verify_html` → `topic_lib rebuild`),把产出与既有交付物
**逐字节比对**(根入口 / 各详情页 / `话题库.md`)并**逐单元格比对 Excel 的当日 sheet**(2026-09-21 起;
月簿「发帖短评/热点拓展」等 sheet 跨日累积,单日临时根整簿比对必误报 —— 坑 81);退出码 0 才算通过。
差异**先怀疑数据本身**(例如既有交付物早于某片段最后一次写入, 见 `references/pitfalls.md` 坑 69),
此时先重跑一次 `run_pipeline.py` 刷新交付物, 再跑回归。

## Step 1: 前期准备(依赖 · token · 关键信息 · 需求跟进)

**信息最小原则(本步一切取证的准则)**:本流程只依赖**两项凭证**(开放平台 Access Secret、网页登录 Cookie)和**两个参数**(ROOT、D,均有默认值)。向用户索取的信息仅限缺失项:能自检就不问(已有凭证先验证),能自动获取就不让用户动手(方式 A),缺哪样才问哪样,一概不多要。

### 1.1 依赖与凭证检测(先验证,再动手;缺啥补啥,不缺不问)

**首选自检**:`python scripts/doctor.py` —— 一条命令给出 Python/openpyxl、CLI 路径与版本、凭证可复用性、`zhihu` skill 版本与更新、脚本完整性,并直接附带缺失项的修复命令;确认无 FAIL 再往下走。

- **Python**:用**真实安装的 Python 3.12+（需 openpyxl）**。⚠️ Windows 裸 `python` 可能是 Microsoft Store 假别名（exit 49/9009）——先 `python -c "import openpyxl"` 验证,假别名就改用真实解释器的完整路径,或 `where.exe python` 排查。
- **知乎 CLI**:`%LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe`;环境变量 `ZHIHU_CLI` 优先。**先 `Test-Path` 验证文件存在**,不存在时不要硬闯:
  1. 跑 `zhihu` skill 的 `scripts/run.ps1 status`。若返回 `installed:false` 但 `auth.keychain_present:true`,说明**系统凭证库里的 Access Secret 仍然有效**(CLI 二进制与凭证库是两套独立存储),安装后直接复用,**不要向用户索要新 Secret**;
  2. 经用户同意后运行 `zhihu` skill 的 `scripts/setup.ps1` 安装,记下 stdout JSON 里的 `binary_path`;
  3. 安装后 `auth status --verify` 确认 `verification=valid`(坑 19)。
- **凭证定向(信息最小——只认这两样,各有各的出处,互不替代)**:
  - **开放平台 Access Secret(CLI 抓取用)**:出处 = 知乎开放平台控制台(open.zhihu.com → 登录 → 开放平台 → 应用管理,应用凭证含 Client ID 与 Access Secret)。仅当 `zhihu-cli auth list` 为空或调用报 AUTH_INVALID 时才向用户索取,且**只索取 Access Secret 一项**,不涉及 API key、权限位申请等任何多余字段。注入一律用坑 1 的无换行方式(`cmd /c "echo|set /p=<secret>|<cli> auth set --secret-stdin"`);AUTH_INVALID 基本都因换行,而非 Secret 本身无效。此凭证**不适用于网页登录**(坑 12)。
  - **网页登录 Cookie(全文解锁用)**:出处 = Step 1.2 方式 A(playwright + Edge 弹窗扫码,自动提取)或兜底方式 B。此凭证**不适用于 CLI 抓取**;与 Access Secret 两套并存、互不替代,检测时分别验证,缺哪个补哪个,齐了就不再多问。
- **脚本**:skill 的 `scripts/` 目录齐全(contract.py / run.py / fulltext.py / search_many.py / check.py / merge_extension.py / verify_html.py / fill_excel.py / gen_html.py / topic_lib.py / question_fetch.py / doctor.py / zhihu_env.py)。
- **playwright-cli(2026-09-16 起只剩两个用途:①Cookie 获取(方式 A) ②可选 unfollow;自动发帖三件套已删)**:npm 全局包 `@playwright/cli`,定位方式:`npm root -g` 拼出 `<npm-global>\node_modules\@playwright\cli\playwright-cli.js`,用**系统 Node(≥20)** 跑 `node playwright-cli.js <命令>`。
  - `open` 一律 `--browser=msedge`——Edge 通道最稳(实测部分机器 Chrome 通道 spawn 被 EACCES 拦截,疑似杀软;Chrome 被拦就换 Edge)。
  - **插件缓存里那份 `plugins\cache\codebuddy-plugins-official\playwright-cli\0.1.0\playwright-cli.js` 不要用**:它依赖 `playwright@1.59.0-alpha` 的 `lib/mcp/terminal/program` 子路径,直接报 `ERR_PACKAGE_PATH_NOT_EXPORTED`;一律用 npm 全局那份。
- **会话生命周期(cookie 获取失败的头号原因,2026-09-15 查清)**:
  - CLI 的会话/配置**按 cwd 的 sha1 前 16 位分目录**存:`%LOCALAPPDATA%\ms-playwright\daemon\<cwd-hash>\`。**cwd 一变就等于换了一套会话与 profile** —— 所以所有 CLI 调用必须在同一个 cwd,推荐固定用上面那个 npm 目录。
  - 浏览器由 **detached daemon** 持有:同一个 shell 进程内多次 CLI 调用共享会话;但**守护进程随调用方进程树结束而消失**,下次就是全新会话。⇒ **把 open → state-load → 动作 → close 放进同一次调用里**,不要跨调用依赖会话。
  - 不带 `--persistent` 时 profile **只在内存**;带 `--persistent` 才落盘到 `<daemonDir>\ud-default-<browser>`。**但只有优雅 `close` 才会把 cookie 刷进 profile** —— 直接杀进程会丢。
  - 想「永久化登录态」用**固定 profile + storageState 双保险**:`open ... --persistent --profile <固定目录>`,登录后用 `state-save <file>` 导出、以后每次 `state-load <file>`。
  - 建议**把常用动作封装成本机助手脚本**(可选,非必需),统一管理三类资产:固定 profile 目录、storageState 文件(`<脚本目录>\profiles\zhihu-edge`、`...\profiles\zhihu-state.json` 这类固定路径),子命令 `login` / `save` / `check` / `load` / `close`。下文示例用 `zhihu-pw.ps1 <子命令>` 指代这类助手,没有助手就照手工版走。
  - ⚠️ **判据别用 URL**:问题页匿名也能打开、URL 里不含 `signin`,拿「URL 是否跳 signin」判定登录会**假阳性**。要判「页面里有没有『登录/注册』入口」。
  - ⚠️ **`cookies.txt` 里的 `z_c0` 不能当浏览器登录态用**(2026-09-15 实测):把 `raw/<D>/cookies.txt` 的 cookie 注入上下文,注入当刻 `context.cookies()` 里能看到 `z_c0`,但**下一次 CLI 调用它就没了**,页面始终显示「登录/注册」——服务端不接受这份会话。HTTP 抓取(fulltext/question_fetch)认它,浏览器自动化**不认**。用浏览器前(现在是可选 unfollow)必须用 `zhihu-pw.ps1 check` 实测一次。

### 1.2 网页登录 Cookie(懒加载:默认复用,失败才获取)

知乎网页 API 对**未登录**请求的长回答只返回截断摘要(`content_need_truncated=true`),全文需网页登录 Cookie;开放平台 Access Secret 不适用于网页登录。不带 Cookie 时大量回答只能标注「接口摘要」(2026-08-09 实测:74 条中仅 24 条拿到全文;带 Cookie 后 74/74 全量解锁)。

**处理策略(用户 2026-09-11 明确指示:不反复测试、不每次删除——只在真正失败后才动它)**:

1. **有 `raw/<D>/cookies.txt` → 直接复用,不验证、不删除、不询问。** 跨天/跨会话续跑也一样:先用起来,让流程自己暴露问题。不验证的代价可控——失效时会显式表现为下面第 3 步的失败信号;且 **2026-09-21 起 `question_fetch.py` 默认带 cookie 预检**:开跑前用第 1 个问题类条目试抓 2~3 个请求,前 3 条回答**全部 summary** 或抓取即 403 → `[FATAL]` 当场中止并打印方式 C 配方(`--no-preflight` 可跳过)——预检把坑 77 从「自愈」变成「预防」。无 Cookie 时的截断回答也带内容(truncated),预检照常放行,不误拦正常的无 Cookie 降级路径。
2. **没有 cookies.txt → 先按"无 Cookie"正常跑**(抓取与补全照常执行)。这不是错误状态,只是拿不到全文。
3. **只有出现失败信号才去获取/刷新 Cookie**,判定标准(任一命中):
   - `fulltext.py` 报告的 `truncated + summary` 占比 **> 20%**(大部分回答退化);
   - 任何网页接口返回 **403 / 要求登录**;
   - 用户明确要求「带 Cookie 重抓」。
   获取成功后**只重跑失败的那一步**(cookie 跑一半失效时 = `question_fetch.py` 并集 + `fulltext.py`,见方式 C),不必重跑榜单抓取。
4. **获取后长期保留**。下次运行乃至跨天都优先复用同一份;只有确认失效才覆盖刷新。
   - 清理方式(**仅在用户明确要求时**执行):`Remove-Item raw/<D>/cookies.txt`。

**方式 A(主手段,playwright-cli + Edge —— 零誊写;路径判据按实测校正)**:
1. 先做**预检**(有助手脚本就 `zhihu-pw.ps1 check`;没有就跑下面手工版的 `cookie-get` 看返回):
   → 输出 `"anonymous": false` 即已登录;**输出 `anonymous: true` 就是没登录**(要人工登一次:`login` → 在 Edge 里登录 → `save` → `close`)。
2. ⚠️ **判据不许用 URL**:问题页匿名也能打开、URL 不含 `signin`,`!signin` 判定会假阳性(实测踩过:脚本报 `signedIn:true` 而页面明明挂着「登录/注册」)。要么看「登录/注册」入口是否存在,要么看 `context.cookies()` 里**下一次调用**是否还在(`cookie-get z_c0` 是按当前页域过滤的,页面在 `about:blank` 时会误报「未找到」)。
3. 手工版(以 `%ZHIHU_PW%` 代指你选定的助手资产目录,如 `%USERPROFILE%\zhihu-pw`):
   ```
   Set-Location "<npm root -g>\node_modules\@playwright\cli"   # cwd 必须固定,变了就换会话
   node playwright-cli.js open "https://www.zhihu.com" --browser=msedge --headed --persistent --profile "%ZHIHU_PW%\profiles\zhihu-edge"
   ```
4. **未登录时**:告知用户「请在 Edge 窗口内登录,完成后回复我」——**以用户回传为信号**,不轮询、不猜测、不设超时;收到确认后重跑第 1 步。
5. **提取**:把 `cookie-list --domain=zhihu.com` 输出每行取 `name=value` 用 `; ` 拼接(**含 z_c0 等全部,不过滤域名**)→ 写 `raw/<D>/cookies.txt`。
   顺手把这个登录态固化下来:`node playwright-cli.js state-save "%ZHIHU_PW%\profiles\zhihu-state.json"`(下次 `state-load` 即用)。
6. **收尾**:`node playwright-cli.js close`(**必须优雅关**,别杀进程 —— 否则 cookie 不落盘)。

**方式 B(兜底,仅 playwright-cli 不可用时)**:浏览器登录 zhihu.com → F12 → Network → 刷新任意页面 → 复制 `Request Headers` 里 `Cookie:` 的**完整值**(从 `_xsrf=` 到末尾)→ 存为 `raw/<D>/cookies.txt`。**整串复制粘贴,勿手工誊写**(z_c0 含 `|` 与签名段,誊写会截断致登录态失效,坑 14)。

**方式 C(自动重提,流程跑到一半 cookie 失效的自愈;2026-09-21 实战,坑 77)**:
症状 = `question_fetch` **全部** `source=search_fallback` + `fulltext` **全部** `summary`(整批退化;个别 403 是坑 33,重跑本步即可,别混)。免手工配方三步:
1. 用 playwright-cli 从**已登录的 Edge 持久配置**导出 storageState:`node playwright-cli.js state-save "%ZHIHU_PW%\profiles\zhihu-state.json"`(cwd 固定在 npm 目录;用助手则 `zhihu-pw.ps1 save`)。
2. 提取:`python scripts/extract_cookie.py --state "%ZHIHU_PW%\profiles\zhihu-state.json" --out <ROOT>/raw/<D>/cookies.txt` → 产出**单行 Cookie 头、UTF-8 无 BOM**;缺 `z_c0` 打 WARN = 提取到的是未登录态,先回方式 A 人工登录再走本方式。
3. **重跑 `question_fetch.py`(并集)+ `fulltext.py`**,其余步骤不重跑;重跑前**别手改 `raw/<D>/` 里的 hot.json**(下游按它对账,手改会造成"看起来正常"的脏数据)。2026-09-21 实战:当日全部 summary/search_fallback 由此恢复 full=99。


**写入注意事项**:文件必须是 **UTF-8 无 BOM**。PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写入 BOM,使 Cookie 串首字符变成 `\ufeff`,放进 HTTP header 时报 latin-1 编码错(坑 25);读取端一律用 `encoding="utf-8-sig"` 兼容。

**风险提示**:Cookie 长期留在 `raw/<D>/cookies.txt`,属敏感凭证。在共享设备、或需要把目录交付他人时,按第 4 步的清理命令显式删除。

### 1.3 关键信息取得(每次执行都重新确认,不依赖会话记忆)

**三条强制动作(跨天续接的会话里旧记忆会整体失效,见坑 23)**:

1. **重新取当前日期**:`Get-Date -Format "yyyy-MM-dd"`(Windows)或 `date +%F`。**不要沿用会话早些时候得到的日期**。
2. **ROOT 自动发现**(按优先级):① 用户在本次消息里给的路径 → ② 运行 `python scripts/doctor.py --discover`,它扫描含 `话题库/index.json` 或 `跟进excel-*.xlsx` 的目录并列出候选(可用环境变量 `ZHIHU_TRACK_ROOTS` 限定搜索范围,分号分隔)→ ③ 都没找到才用兜底默认值。**发现多个候选时必须向用户确认**,不要自行挑选。
3. **检查 `raw/<D>/` 是否已存在**:存在则先报告已有产物(hot.json / answers_summary.json / analysis.json / extension.json)并询问「补抓 / 覆盖 / 复用断点」,不要静默覆盖。

| 信息 | 默认值 | 说明 |
|---|---|---|
| 工作根目录 ROOT | 自动发现(兜底见 `doctor.py --discover`;示例 `D:\zhihu-track`) | 任意目录均可,所有脚本 `--root` 参数化 |
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
   **2026-09-21 起先过阶段0 预闸门**: 默认只搜过闸 rank, 每天最贵的一步砍掉约四分之三
   (2026-09-21 实证: 20 题里 16 题非时政)—— 上列全量数字是上限口径, 实际按预闸名单打折。
2. **是否重跑书写 loop(3c/3d/4c)** —— 提取端 4 批 ≈ **4.8 万 token**;书写端 20 个 subagent ≈ **10 万 token**;
   合计 **≈+12.4 万/天**(其中约 2.4 万是从拓展端省下的——写稿职责已移出拓展 subagent)。
   (2026-09-16 起:写稿端只为**过闸 rank** 写 50–100 字短评;2026-09-21 起**过闸全写**、不按每日上限
   预裁剪,推荐/备选由队列排序裁决;上列书写端数字为改制前的实测口径。)
   **提取端必须每天跑**(用户 2026-09-15 定; 旧口径"规范稳定时隔日跑"已作废)——
   这一环**不再是可省项**, 报成本时按固定支出计入, 不要建议用户跳过。
3. **是否重跑抓取/补全(带 Cookie)** —— 不花 token(HTTP),但会触发后续分析与校验重跑。

**报告示例(2026-09-12 实测口径)**:
> 一次性实现 7k + 数据回填 5k = **约 13k token**;此后每天 +2.5k(占基线 0.6%)。**不重跑 Swarm**(重跑需 +30–50 万)。

### 1.6 成本结构与本流程的省钱口径(2026-09-14 会话记账实测)

**实测结构(当日 hot-track 全部会话, 共 18 个:主 Agent + 17 个子 agent)**:

| 环节 | 缓存读(累加) | 输出 | 占比 |
|---|---|---|---|
| 话题延伸 Swarm(5 agent × 4 rank) | 88.7M | 30.1 万 | **≈58%** |
| 主 Agent(渲染阅读 + 四维分析 + 调度) | 44.0M | 15.0 万 | **≈29%** |
| 情绪 + 书写提取 + 写稿(13 agent) | ≈19M | 28.9 万 | ≈12% |

> 口径:缓存读是"每次 API 调用重读缓存前缀"的累加值,绝对值不等于账单,但**相对占比**稳定可用。
> 取数方法:`~/.dsh/storages/session_projcache/sessions/*.json` 里每个会话的 `rows.tokenUsage.val.totals`。

**五条省钱口径(按省下的量排序, 已固化进 Step 2 流程)**:

1. **阶段0 预闸门:检索前先挡明显非时政**(2026-09-21 起, 现在的最大单项):
   `gen_prompts --gate --stage0` → 预闸门 subagent 只判时政(从宽: 拿不准判「是」)→
   `raw/<D>/publish_verdicts_pre.json` → swarm 默认只搜过闸 rank。
   **2026-09-21 实证: 20 题里 16 题非时政 —— 每天最贵的一步(swarm 检索)砍掉约四分之三**;
   阶段1(检索后全量两关判定)不变, 对预闸结果构成双保险。
2. **Swarm 只读 slim + 轮数上限 3**(省 Swarm 的 40–60%):`search_many.py` 现已同时产出
   `rank_0N_*.slim.json`(只留标题/链接/作者/赞评/220 字摘要, 约完整归档 1/4);`--count` 默认 4;
   模板要求 3 轮硬上限。**理由**:59% 的成本在这一环, 而大头是"把 20–46KB 的检索归档整份读进上下文"。
3. **SKILL.md 拆分**(省主线程常驻上下文 ≈40%):踩坑库与脚本表移到 `references/pitfalls.md` /
   `references/scripts.md`, 按需读;主文件只留触发/准备/流程/约束/拓展板块。**理由**:主线程占 29%,
   而它每一步都要重读这份常驻前缀。
4. **写稿只给过闸条目**(省检索-成文的全额成本):`gen_prompts --write` **省略 `--ranks` 时默认给全部过闸 rank 写**
   (2026-09-16 起;前置判断三道闸门之后;2026-09-21 起**不再按每日上限预裁剪** —— 推荐位/备选由
   `publish_queue.py` 排序裁决, `--top N` 是可选的旧式裁剪),没过闸的条目不产稿。
   **理由**:写它不会被发出去。(本条原为"只覆盖发布集前 15 条",随自动发帖删除改为按闸门裁剪。)
    (**注**: 本条原写作"写稿只覆盖发布集 + 提取端隔日跑", 其中"提取端隔日跑"半条已被用户 2026-09-15 取消 ——
    书写提取 + 汇编改为每个新日期必跑, 见 Step 2 的 3d。)
5. **读答两件事合并 + 批量渲染**(省读答成本约一半 + 减少读取步数):3b 用 `--combo` 把情绪标注与
   书写提取合成**一个** subagent(同一批回答只读一次);分析前用 `render_answers.py --per 5` 批量渲染,
   整批 read 而非逐 rank read。**理由**:重复读同一批回答是纯浪费;逐 rank 读还会把步数乘进缓存成本。

**明确不做省的**:权威校验器(`--lint`)、事实性复核、`verify_html` 断言、入列前的字数与中庸检查 —— 这些是脚本在跑, 不花 token。

## Step 2: 执行流程(现有逻辑)

### 交付物

| 文件 | 说明 |
|---|---|
| `跟进excel-YYYY-MM.xlsx` | 月度 Excel:每个抓取日期一个 sheet(命名 `YYYY-MM-DD`),**最新日期 sheet 插到最前**;一级行=问题(本质信息),二级行=回答(最多 10 条) |
| `知乎热榜跟进-YYYY-MM-DD.html` + 同名目录 | 分页式展示:入口自动跳转 → 索引页(自适应网格卡片 + **✍️ 今日短评挑稿面板**:按 priority 列出推荐 #N 与备选 #N,含 rank/稿标题/正文摘要/字数,链接详情页 `#draft` 锚点,一屏选稿;队列缺失/无稿时整块不出现)→ 每问题一页(回答折叠扩展 + 四维分析 + 多元化情绪 + 全部条目的热点拓展 + ✍️ 发帖短评(状态徽标,`id="draft"` 锚点)) |
| `raw/YYYY-MM-DD/` | 原始 JSON 存档(hot/search/answers_summary/analysis/extension/publish_verdicts_pre/publish_verdicts/publish_queue),可溯源 |
| `raw/YYYY-MM-DD/answers_web_preview.json` | (可选)问题维度抓取的对比预览,用于核对覆盖率变化;不影响交付物一致性 |
| `ext_search/YYYY-MM-DD/rank_<n>/draft_<n>.md` | **发帖短评**(2026-09-16 起,路径不变、体裁改短):50–100 字犀利短评,**只有过三道闸门的 rank 才写**,由独立书写 subagent 产出;同步进 Excel「发帖短评」sheet 与 HTML 每问页底部(原「拟答参考稿」≤500 字口径已废弃) |
| `raw/YYYY-MM-DD/publish_verdicts.json` | **前置判断结果**(判定 subagent 撰写):逐 rank 是否时政 + 有无增量信息,必填 basis/baseline/why |
| `raw/YYYY-MM-DD/publish_verdicts_pre.json` | **阶段0 预闸门结果**(2026-09-21 起,检索前跑):只判时政,从宽原则(拿不准判「是」);`gen_prompts` 默认只给过预闸 rank 生成拓展提示词,省约 70-80% 检索;**文件缺失 = 未跑预闸门(回退全部 rank)** |
| `raw/YYYY-MM-DD/publish_queue.json` | **待发帖列**(2026-09-16 起"该发哪几条/发到哪一步"的唯一事实源):三道闸门 + 每日上限内**推荐/备选排序**的裁决结果(2026-09-21 起:过闸全写,有效稿按情绪强度→最高赞排序,前(上限−已发布)条=推荐、其余=备选),状态值域 `contract.QUEUE_STATES` |
| `<ROOT>/待发帖-YYYY-MM-DD.md` | **人读待发帖清单**:推荐 N 条 + 备选 M 条**全文逐条可复制**(2026-09-21 起),由用户人工粘贴发布(可发推荐、也可换发备选),再用 `publish_queue.py --mark` 回填 |
| `书写skill/书写skill.md` | **书写 skill(自我学习 loop 的产物, 跨日期累积)**:由提取 subagent 从高赞回答里提炼"书写逻辑与语言习惯"(**不含具体内容**), 主 Agent 按奥卡姆剃刀汇编。书写 subagent 按它成文;越用越准。原始提取片段留档在 `ext_search/<D>/style/style_batch_*.json`, 候选池 `ext_search/<D>/style_merge.json` |
| `话题库/话题库.md` | **跨日期累积话题库**(每次运行必更新):按分类组织,发散搜索前查重、收敛性判断依据 |

Excel 列(18 列,2026-09-13 起):层级 / 问题序号 / 排名 / 问题标题 / 原问题URL / 问题点赞数 / 问题本质 / 回答序号 / 回答内容 / 回答点赞数 / 立场分析 / 解决思路 / 判断逻辑 / 情绪倾向 / **情绪标签** / **情绪强度** / **情绪指向** / 备注
(旧日期 sheet 仍是 16 列、以「情绪判断(积极·中立·消极)」占 1 列 —— **每天一个 sheet、各自表头,故新旧列数并存不冲突**;
历史 sheet 不回改。)

### 主流程(脚本全部在 skill 的 scripts/ 目录,参数化,可复用)

```text
ROOT=D:\zhihu-track          # 工作根目录(示例;任意目录均可,首次用 doctor.py --discover 找到它)
D=2026-08-09                              # 抓取日期

0. 体检:   python scripts/doctor.py --root %ROOT% --date %D%    (前置条件一条命令看清; 有 FAIL 先修再跑)
1. 抓取:   python scripts/run.py --root %ROOT% --date %D% [--limit 20] [--variants 6]
            → raw/<D>/hot.json + search_<n>_v<k>.json + answers_summary.json(关键词搜索召回, 作兜底)
1b.问题维度: python scripts/question_fetch.py --root %ROOT% --date %D% --top 5 --pages 3
            → 重写 answers_summary.json: 每问题取「问题维度网页接口(按赞) ∪ 上一步搜索召回」**并集**前 5,
              并写入 total_answers / coverage / source(覆盖率标注的依据)
            (需 Cookie; 无 Cookie 时自动降级为搜索数据, 标 source=search_fallback;
              2026-09-21 起默认先 cookie 预检: 开跑前 2~3 个请求试抓, 失效即 [FATAL] 中止并提示方式 C,
              --no-preflight 跳过)
2. 补全:   python scripts/fulltext.py --root %ROOT% --date %D% [--cookie raw/<D>/cookies.txt]
            (约束一。有 cookies.txt 就带上, 不必先验证其有效性; 没有就先不带跑,
             若 truncated+summary 占比 >20% 再按 Step 1.2 获取 Cookie 并只重跑本步)
3. 分析:   python scripts/render_answers.py --root %ROOT% --date %D% --ranks 1-20 --per 5
            → **先批量渲染**(硬换行 900, 每批 5 个 rank 一个文件), 再**整批 read**, 不要逐 rank 读:
              省读取步数与"补读尾部"的重复轮次(坑 49; 2026-09-14 成本实测后固化)
            → 四维主体(立场/解决思路/判断逻辑/情绪倾向)由 **Agent 亲自**读渲染文本逐条写 → analysis.json
            (四维主体按 URL 对应, 见约束二)
3b.情绪 + 书写提取(**复合子任务**, 2026-09-14 起推荐):
            python scripts/gen_prompts.py --root %ROOT% --date %D% --ranks 1-20 --combo --per 5
            → 每批 5 个 rank 派**一个** subagent, 同一次阅读里产出**两份**结果:
              ① 情绪标注(模板 scripts/prompt_emotion.md: 词表/判据/四条边界裁决/标定样例/必填 why)
                 → ext_search/<D>/emotion/emotion_batch_<tag>.json
              ② 书写逻辑提取(模板 scripts/prompt_style.md: 11 个固定维度, 只提"怎么写")
                 → ext_search/<D>/style/style_batch_<tag>.json
            → **为什么合**: 两件事读的是同一批回答、彼此无依赖, 分开派等于把回答读两遍
              (2026-09-14 实测: 书写 loop + 情绪共 13 个 agent ≈ 全天 12% 成本, 合并后读答成本减半)
            → **为什么"写稿"不能一起合**: 写稿依赖**汇编好的书写 skill**(提取→汇编→应用, 坑 68), 顺序上必须后派
            → 合并后逐条对账: python scripts/merge_emotion.py --root %ROOT% --date %D% --compare
              → **主 Agent 只复核分歧项**(实测与主 Agent 完全一致率仅 20%, 分歧集中在 讽刺vs调侃/强度/指向/失望·无奈·忧虑)
              → python scripts/merge_emotion.py --root %ROOT% --date %D% --write
            → 单跑其中一路(补跑/换语域时): 把 --combo 换成 --emotion 或 --style
3c.(已并入 3b; 单独重跑书写提取时才用 `--style`)
3d.汇编书写 skill(主 Agent, **奥卡姆剃刀**):
            python scripts/merge_style.py --root %ROOT% --date %D% --write
            → 折叠近义重复(同维度相似度≥0.62 合一条)、按维度归类、给出跨批频次
            → 主 Agent 依频次取舍: **保留普遍做法与约束力最强的"避免"项, 删掉低频同义与空泛项**,
              汇编成 <ROOT>/书写skill/书写skill.md(**跨日期累积**, 与话题库同构: 越用越准)
            → **每个新日期都必须跑完 3b 的书写提取 + 3d 汇编**(用户 2026-09-15 明确要求, **取代**此前的
              "隔日跑即可/规范 2 天内可跳过"口径 —— 那条省钱口径作废, 不要再拿"规范还新"当跳过理由):
              规范的价值在于随每一批新语料持续优化, 跳过一天等于让当天的语域变化不被吸收。
              默认用 `--combo`(情绪 + 书写提取一次读), 只有单独补跑其中一路时才用 `--emotion` / `--style`。
              唯一的例外: 当日 rank 未抓取或无回答(无新语料可学)时, 3b/3d 自然无从执行。
3e.阶段0 预闸门(2026-09-21 起, 检索前先挡明显非时政 —— 当天最贵的一步省约 70-80% 检索):
            python scripts/gen_prompts.py --root %ROOT% --date %D% --gate --stage0
            → 一份预闸门提示词(**不嵌信号表** —— extension.json 还没生成), 派**阶段0 判定 subagent** 只判时政:
              **从宽原则 —— 拿不准一律判「是」, 宁多搜不误杀; 判 false 必须具体说出为何不涉公权力**
              → 写 raw/<D>/publish_verdicts_pre.json(只判时政不填增量; 阶段1 检索后全量两关照旧, 双保险)
4. 拓展:   **Agent Swarm 并行**: python scripts/gen_prompts.py(默认模式; **省略 --ranks 时自动按预闸门
              名单过滤**, 打印 [预闸门] 过闸 rank: [...]; pre 文件缺失 = 未跑预闸门 → 回退全部 rank;
              显式 --ranks 1-20 可全量)→ **只给过预闸的 rank 各派 subagent**(2026-09-21 实证: 20 题里
              16 题非时政, 检索只做剩下的)
            → 每个 subagent 读回答 → 迭代发散搜索 → **只产出 chains/dropped/thinking**(不再顺带写稿, 见 Step 4c 的前置判断)
            → **省钱硬要求(2026-09-14 成本实测后收紧)**:
              ① 只读精简版 `rank_0N_*.slim.json`(search_many 自动生成, 约完整归档 1/4 体积),
                 需要核对原文时才读完整归档;
              ② `--count` 用默认 4(8 条里过半与想法无关);
              ③ **轮数硬上限 3 轮**(确有新 URL 才放宽到 4, 并在 thinking 里逐轮说明新线索);
              ④ 建议每 agent 打包 4–5 个 rank, 别一个 rank 一个 agent(固定开销 × 20)。
              依据: 本次运行 5 个 Swarm agent 占全天缓存成本的 **58%**, 而大头正是"反复读检索结果"。
            (schema 见"热点拓展板块"; 收尾必须跑 merge_extension.py --ranks <n> --lint)
4b.汇总+复核: python scripts/merge_extension.py --root %ROOT% --date %D%
            → ① 链式强校验(claim/evidence/takeaway + relation 值域 + type 值域 + 同类型≤3 + URL + entities
               + **chains[].source 与原答对账**)
              并按链展平 items → 写 raw/<D>/extension.json
            → ② **紧接着自动做事实性复核**(--no-verify 跳过; --no-links 不联网):
              信源门槛兜底(A事实性/B待定/C不采信/D观点, 锚点=数值+制度性) + 多源印证(归档池 + 同源折叠)
              + 链接探活(5xx/超时退避重试) + 归档核对; 结果写回 extension.json 并另出 raw/<D>/ext_verify.json
            (复核已与汇总合并, 不需要单独跑; verify_ext.py 仍保留, 供单独补跑/机读)
4c.前置判断 + 发帖短评(2026-09-16 起取代原"回答书写"; **学习端的用武之地**):
            ① 前置判断(**阶段1**: 检索后全量两关判定 publish_verdicts.json, 对阶段0 预闸结果构成双保险):
              python scripts/gen_prompts.py --root %ROOT% --date %D% --gate
              → 一份判定提示词(**内嵌 publish_queue.py --signal 预计算的信号表**) → 派**判定 subagent**
                写 raw/<D>/publish_verdicts.json: 逐 rank 判 **是否时政 + swarm 证据有无增量信息**
                (必填 political_basis / increment_basis / baseline / why; 增量基线优先 comments.json, 缺则降级回答区)
            ② 汇总 + 闸门: python scripts/publish_queue.py --root %ROOT% --date %D%
              → 校验判定 → **三道闸门**: ①非时政不进列 ②无增量不进列(只认评论区/回答区没有的新东西)
                ③过闸者写完短评后查言语中庸(脚本 MEDIOCRE_PATTERNS 黑名单硬拦 + 主 Agent 复核犀利度)
              → **判定与脚本信号相反的条目列为「分歧复核」交主 Agent**(与情绪判定同一套纪律)
              → **过闸条目全部检查稿件**(2026-09-21 起,不再按上限预分配预算): 无稿=draft_pending,
                字数越界/中庸/犀利度未判照旧打回; 有效稿按 **情绪强度(analysis 各回答最大值)降序
                → 回答区最高赞降序 → rank 升序** 排序(存 priority, 1 起),
                前(上限−已发布)条 = ready(推荐位), 其余 = over_daily_cap(备选, 人工终审可换)
            ③ 书写: python scripts/gen_prompts.py --root %ROOT% --date %D% --write
              → **省略 --ranks 时默认给全部过闸 rank 写**(--top N 可选=旧式裁剪,只给前 N 个过闸 rank 写);
                派**书写 subagent**(模板 scripts/prompt_write.md):
                **不检索**, 读 <ROOT>/书写skill/书写skill.md + 本 rank 的 rank_<n>.json → 写 draft_<n>.md
                (50–100 字犀利短评 / 骨架=判断→机制/代价→落点 / 第一句钉死判断 / 允许暴论 / 正文零链接 / 事实纪律不变)
            ④ 复检 + 渲染: 重跑 python scripts/publish_queue.py --root %ROOT% --date %D%
              (字数 50–100 + 中庸黑名单复查) → **推荐 N 条 + 备选 M 条全文**渲染进 <ROOT>/待发帖-<D>.md,
              等人工发布(Step 7); 每日上限 3 仍然只管**发布数** —— 可以少、不可以多, 不因备选而放宽
5. 出交付: python scripts/run_pipeline.py --root %ROOT% --date %D% [--merge] [--emotion]
            → **一键跑完并逐关校验**: 情绪合并(可选) → 汇总(可选) → check → fill_excel → gen_html → verify_html
              失败即停并报是哪一关(取代手敲四条命令; 实测手敲容易漏步, 如改了数据忘了重出 Excel/HTML)
6. 收尾:   cookies.txt **保留复用, 不删除**(见 Step 1.2; 仅用户明确要求时才清理);
            清理 ext_search/<D>/ 下 subagent 遗留的临时脚本与中间文件(坑 22);
            若本次补全过(带 Cookie), Agent 重读全文逐条复核 analysis.json(坑 15), 再跑一次 run_pipeline。
7. 人工发布与回填(2026-09-16 起; **自动发帖三件套已删, 不再自动发布**):
            → 打开 <ROOT>/待发帖-<D>.md, **由用户本人复制粘贴发布**(默认发推荐条目;人工终审可换掉
              任一推荐条目改发备选, 发布后同样回填, 每日 ≤3, 人工终审)
            → 发布后回填: python scripts/publish_queue.py --root %ROOT% --date %D% --mark "<rank>=<回答链接>"
              (队列 raw/<D>/publish_queue.json 是"发到哪一步"的唯一事实源; 状态值域见 contract.QUEUE_STATES;
               制度细则见「待发帖列制度」一节)
8. 可选·取消关注(人工发布后清尾): python scripts/unfollow_question.py --out <unfollow.js>
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
- 榜单:**前 20 全部**跑 Swarm(2026-09-13 起;原为前 10;2026-09-21 起默认先过阶段0 预闸门,
  只给过闸 rank 生成拓展提示词,显式 --ranks 1-20 可全量);
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
2. **派发**:过预闸的 rank 各派一个 subagent(可 2-3 个 agent 各包 2-5 个 rank;2026-09-21 起
   默认只派过阶段0 预闸门的 rank, 显式 --ranks 1-20 可全量),每个 subagent 独立执行:
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

### 发帖短评(2026-09-16 用户要求「语言一定要犀利」;由原「拟答参考稿」改制)

**过闸的 rank 才产出一条发帖短评**,落在 `ext_search/<D>/rank_<n>/draft_<n>.md`(路径不变,体裁改短)。
它不是成文回答,而是**一条 50–100 字、态度鲜明的短评**,进待发帖列由人工发布。
**原「≤500 字拟答参考稿」口径已废弃**(2026-09-16):"每个 rank 必出稿、写满 500 字"的制度随自动发帖一起退役,
写稿改为**闸门之后、只为过闸条目服务**(2026-09-21 起**过闸全写**、不按每日上限预裁剪 —— 推荐/备选由 publish_queue.py 排序裁决)。仍由 Step 3c/3d/4c 的学习 loop 负责(先学写法 → 汇编成书写 skill → 再据此成文),
要求全文见 `prompt_write.md` 与 `<ROOT>/书写skill/书写skill.md`,要点:

- **篇幅(硬)**:正文 50–100 字(不含标题),越界打回重写(`publish_queue.py` 复检,状态 `len_out_of_range`)。
- **骨架 = 判断 → 机制/代价 → 落点**:**第一句就把判断钉死**,不许铺垫 —— 字数上限把"讲清机制"
  压成"一句判断 + 一句机制/代价 + 一句落点",顺带挤掉缓冲与和稀泥。
- **语言要犀利(用户 2026-09-16 原话)**:允许暴论、该拍桌子就拍;**中庸句式黑名单**
  (`contract.MEDIOCRE_PATTERNS`,「一方面…另一方面」「见仁见智」「理性看待」等)是**硬闸门**,命中即打回;
  学习 loop 的「犀利度与锋芒」维度(2026-09-16 新增)专门学"怎么把话说狠",中庸写法进各维度的 avoid。
- **纪律不变**:正文零链接(来源留在素材层)、事实纪律照旧(数字/主体/出处照素材写,不编造)、
  禁 AI 腔提示语(「先给结论」「值得注意的是」「综上所述」)与标签式标注。
- **只有过闸 rank 才写**:三道闸门没过的 rank **不出短评** —— 写了也不会发,纯烧检索-成文成本。
- **落地**:HTML 每问页底部「✍️ 发帖短评(N 字 · 50–100 字犀利向 · 状态徽标)」块(徽标读 publish_queue.json:
  `ready→「推荐 #N」`、`over_daily_cap→「备选·超今日建议 #N」`;**字数=正文口径,标题行不计**,与队列一致 —— 2026-09-21 修);
  Excel「发帖短评」sheet(2026-09-16 由「拟答参考」就地更名,历史行不分裂;末列「待发帖」标状态:
  待发/已发/过闸待写/超上限/打回·中庸/打回·字数/待复核);`verify_html` 对账项「发帖短评渲染对账」。
- **不重跑成本提示**:过闸后若只想补稿,可派轻量书写 subagent 直接读现成 `rank_<n>.json` +
  `书写skill.md` 写短评(远低于旧拟答稿的单价),不必重跑检索。

### ⚠️ 本流程不发布:自动发帖已删除(2026-09-16),对外动作由人工终审

**流程只到「待发帖列」为止,发布动作一律由人执行(2026-09-16 起自动发帖三件套已删)。** 两层依据:

1. **开放平台没有发布接口**(2026-09-13 核实,机读事实):`zhihu-cli capabilities` 返回的全部命令中,
   `me/creator` 系列**全是 `GET`**,唯一的写操作是 `knowledge upload` —— **没有任何创建回答/文章/想法的端点**。
2. **浏览器自动发帖三件套已整体删除**(2026-09-16 用户决策"目前来说收益太少"):
   `publish_draft.py` / `publish_batch.py` / `make_manual_publish.py` 已从 skill 移除 ——
   日发 15 条的自动化收益,抵不上 DOM 脆弱、平台风控与配额、逐条盯守的成本
   (教训见坑 60/61/64/65/66;决策与替代方案见坑 76)。

因此本 skill 交付**待发帖列**(见下节),由用户本人粘贴发布;**交付物不得暗示"已发布/可自动发布"**(2026-09-16 起该结论落实为制度)。
该能力边界 2026-09-13 核实, 至今成立。

### 待发帖列制度(2026-09-16 起, 硬制度)

> **自动发帖已退役(2026-09-16), 台账思想存活**: `raw/<D>/publish_queue.json` 是"该发哪几条/发到哪一步"的
> 唯一事实源, 状态值域 `contract.QUEUE_STATES`(ready / draft_pending / published / verdict_missing /
> skip_not_political / skip_no_increment / over_daily_cap / len_out_of_range / mediocre / sharpness_unjudged)。

**制度五条(硬性)**:

1. **三道闸门(顺序即优先级;判定权在判定 subagent, 脚本只兜底 —— 与信源门槛同一套纪律)**:
   ① **是否时政** —— 非时政不进列(拓展照常做, 只不出短评);脚本按 `contract.POLITICAL_CATS/POLITICAL_HINTS`
   预计算信号,**判定与信号相反的条目列为「分歧复核」交主 Agent**;
   ② **增量信息** —— swarm 证据必须拿到**评论区/回答区没有的新东西**(新数字/新文书/新机制/新案例),
   只是复述已有观点则不进列;基线优先 `raw/<D>/comments.json`, 缺则降级回答区, 结论必写 `baseline` 字段
   (取值见 `contract.VERDICT_BASELINES`;证据与基线文本 3-gram Jaccard ≥ `contract.GATE_REPEAT_JACCARD`(=0.30)
   即疑似复述);
   ③ **言语中庸** —— 过闸者写完 50–100 字短评后, 脚本按 `contract.MEDIOCRE_PATTERNS` 黑名单正则硬拦
   (命中=「打回·中庸」), 主 Agent 再复核犀利度(`sharpness_unjudged` = 还没复核);
   **阶段二复核照旧由主 Agent 亲自读稿裁决, 复核结论用 `--sharp` 一等命令回填**(2026-09-21 起,
   取代主 Agent 手写临时脚本; 回填后本命令自动重跑闸门汇总与渲染 —— 见下方日常命令)。
2. **过闸全写 + 排序推荐(2026-09-21 新制度)**:过闸条目**全部检查稿件**(不再按 rank 序预分配预算)——
   无稿 = `draft_pending`,字数越界/中庸/犀利度未判照旧打回(打回**不递补**);有效稿按
   **情绪强度(analysis 各回答 `emotion_intensity` 最大值)降序 → 回答区最高赞降序 → rank 升序**排序,
   存 `priority`(1 起;队列条目新增字段 `emotion_top` / `top_like` / `priority`)。
   **每日上限 3**(`contract.PUBLISH_MAX_PER_DAY`)只裁决**发布数**:前(上限−已发布)条 = `ready`(**推荐位**),
   其余 = `over_daily_cap`(**备选**)—— 稿照常进待发帖列与 HTML,人工终审可换掉任一推荐条目改发备选。
   **可以少、不可以多**,不因备选而放宽。
3. **判定必留痕**:判定 subagent 写 `raw/<D>/publish_verdicts.json`(必填字段见 `contract.VERDICT_REQUIRED`:
   rank / is_political / political_basis / has_increment / increment_basis / baseline / why),
   缺判定 = `verdict_missing`, 先补判定再谈入列。
4. **人工终审 + 回填**:推荐 N 条 + 备选 M 条**全文**渲染进 `<ROOT>/待发帖-<D>.md`(逐条可复制),
   由用户本人粘贴发布;想发备选就直接发它 —— **`--mark` 回填对备选同样有效**。
   发布后 `python scripts/publish_queue.py --root <ROOT> --date <D> --mark "<rank>=<回答链接>"` 回填 `published`。
   **回填必须带回答链接** —— "点了发布"不等于"发出去了"(坑 64), 以外部状态(真实回答 URL)为准。
   **`--mark` 归属校验(2026-09-21 起)**:链接必须是 `question/<qid>/answer/<aid>` 形态、且 qid 必须等于
   该 rank 的问题 id, 否则 FAIL 拒绝回填(防贴错行)。
5. **事实纪律不变**:交付物只呈现"哪几条过闸待发",不冒充已发;线上效果(赞/评)不进交付物。

**历史经验仍然有效**(坑 64/66 保留在 pitfalls;2026-09-16 起正文不再指挥任何自动发布动作):
平台配额是**日/周上限**而非短冷却(实测提示原文「您的回答过于频繁，已达到本日或本周数量上限」)——
所以"每日上限 3"是**按平台节奏设计的制度**,不是拍脑袋;隔天想续发, 看 `publish_queue.json` 里
还没 `published` 的条目即可。

```text
# 待发帖列的日常命令(2026-09-16 起取代已删的自动发帖三件套)
python scripts/publish_queue.py --root <ROOT> --date D --signal                    # 只看预计算信号(判定 subagent 的输入, 零 token)
python scripts/publish_queue.py --root <ROOT> --date D                             # 汇总判定 → 闸门 → 上限 → 更新待发帖列
python scripts/publish_queue.py --root <ROOT> --date D --status                    # 只看队列
python scripts/publish_queue.py --root <ROOT> --date D --mark "1=<answer url>"     # 人工发布后回填(可重复; 2026-09-21 起校验归属: 须 question/<qid>/answer/<aid> 且 qid == 该 rank 的问题 id, 否则 FAIL 拒绝回填)
python scripts/publish_queue.py --root <ROOT> --date D --sharp "3=false:<依据>"    # 犀利度复核回填(可重复; true=判中庸打回); 回填后本命令自动重跑闸门汇总与渲染
```

**playwright-cli 在本流程只剩两个用途**:Cookie 获取(Step 1.2 方式 A)与可选 unfollow(`unfollow_question.py`)。
旧自动发帖时代的登录预检(`zhihu-pw.ps1 check`,2026-09-16 前实测沉淀)在 unfollow 前仍适用。

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
  (2026-09-13 起由"仅前 10"改为全部, 见本节开头的范围变更说明; 2026-09-16 起发布侧改为**待发帖列**、
  每日上限 3 条, 见「待发帖列制度」一节。)

## 踩过的坑(1-81)—— 已移到 `references/pitfalls.md`

> **按需读, 不要每次全读**: 坑库共 81 条、约 46KB, 常驻上下文会白烧 token。
> 什么时候读哪一段:
> - 开工前(只在**换平台 / 换环境 / CLI 或凭证异常**时):读该文件顶部的「主题索引」表, 按主题跳读;
> - 踩到具体失败时:`grep` 该文件的错误关键字(如 `AUTH_INVALID` / `BOM` / `403` / `truncated`), 再读命中的那几条;
> - 收尾复核时:只看与本次改动相关的主题(如改了 subagent 派发 → 主题「subagent 协作与自述」)。
> 新增经验仍然写进 `references/pitfalls.md`(编号续写), 并在顶部主题索引里登记一行。

## 脚本清单 —— 已移到 `references/scripts.md`

> 需要"某个脚本负责什么、支持哪些参数"时再打开该文件(含全部脚本与六个提示词模板的参数表),
> 平时不必常驻上下文。**新增/删除脚本后必须同步该文件的表 + `ARCHITECTURE.md` §二,
> 然后跑 `check_docs.py`**(它会比对三处是否一致)。

