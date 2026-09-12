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
| 抓取范围 | 热榜前 20,每问题最多 10 条回答 | 接口上限:热榜 `--limit` ≤30、`search zhihu --count` ≤10;20 已足够(拓展只做前 10),要更大分析面可用 30 |

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
| 相对基线占比 | 分母 = 当日全量运行(上次实测 **≈39 万 token**:含 Agent 逐条四维分析 + 10 rank Swarm) | |

**必须显式回答一条**:**是否需要重跑 Swarm?** 这是最大成本杠杆——单 rank 约 **1.5–2.5 万 token**(读 5 条回答 + 3–6 轮检索 + 写链),10 rank 全量重跑 **15–25 万 token**。若可以人工回填而不重跑,必须写明「不重跑,改人工回填」并给出与重跑的差额。

**报告示例(2026-09-12 实测口径)**:
> 一次性实现 7k + 数据回填 5k = **约 13k token**;此后每天 +2.5k(占基线 0.6%)。**不重跑 Swarm**(重跑需 +15–25 万)。

## Step 2: 执行流程(现有逻辑)

### 交付物

| 文件 | 说明 |
|---|---|
| `跟进excel-YYYY-MM.xlsx` | 月度 Excel:每个抓取日期一个 sheet(命名 `YYYY-MM-DD`),**最新日期 sheet 插到最前**;一级行=问题(本质信息),二级行=回答(最多 10 条) |
| `知乎热榜跟进-YYYY-MM-DD.html` + 同名目录 | 分页式展示:入口自动跳转 → 索引页(自适应网格卡片)→ 每问题一页(回答折叠扩展 + 四维分析 + 情绪着色 + 前10热点拓展) |
| `raw/YYYY-MM-DD/` | 原始 JSON 存档(hot/search/answers_summary/analysis/extension),可溯源 |
| `raw/YYYY-MM-DD/answers_web_preview.json` | (可选)问题维度抓取的对比预览,用于核对覆盖率变化;不影响交付物一致性 |
| `话题库/话题库.md` | **跨日期累积话题库**(每次运行必更新):按分类组织,发散搜索前查重、收敛性判断依据 |

Excel 列(16 列):层级 / 问题序号 / 排名 / 问题标题 / 原问题URL / 问题点赞数 / 问题本质 / 回答序号 / 回答内容 / 回答点赞数 / 立场分析 / 解决思路 / 判断逻辑 / 情绪倾向 / 情绪判断(积极·中立·消极)/ 备注

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
3. 分析:   Agent 亲自读 answers_summary.json, 逐条写四维分析 → analysis.json
            (按 URL 对应!情绪判断必须自行阅读判断, 见约束二/三)
4. 拓展:   **Agent Swarm 并行**: rank 1-10 各派 subagent 独立执行"读回答→发散搜索→产出发散点"
            (subagent 输出 schema 见"热点拓展板块", 必须遵守)
4b.汇总:   python scripts/merge_extension.py --root %ROOT% --date %D%
            → raw/<D>/extension.json(schema 强校验: type 值域 / 同类型≤3 / URL 真实 / 必填字段;
              容忍历史格式变体, 但缺失 thinking、跨 rank 重复 URL、超限类型会告警或直接失败)
5. 校验:   python scripts/check.py --root %ROOT% --date %D%     (零缺失才继续)
6. 填表:   python scripts/fill_excel.py --root %ROOT% --date %D%
            → 跟进excel-YYYY-MM.xlsx(自动建模板;新日期 sheet 插最前;情绪列下拉 + 截断备注 + 热点拓展 sheet)
7. 出网页: python scripts/gen_html.py --root %ROOT% --date %D%
            → 知乎热榜跟进-<D>.html(原文状态标签 + 前10热点拓展块)
7b.校验页: python scripts/verify_html.py --root %ROOT% --date %D%   (约束四自动校验, 必须 PASS)
8. 收尾:   cookies.txt **保留复用, 不删除**(见 Step 1.2; 仅用户明确要求时才清理);
            清理 ext_search/<D>/ 下 subagent 遗留的临时脚本与中间文件(坑 22);
            若本次补全过(带 Cookie), Agent 重读全文逐条复核 analysis.json(坑 15),
            再重跑 check → fill_excel → gen_html → verify_html, 并校验「接口摘要」标签清零(约束一)。

抓取可 --resume 断点续跑;--variants 2-6 控制查询变体数(建议 6)。
CLI 路径:环境变量 ZHIHU_CLI 优先,否则默认 %LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe(缺失时按 Step 1.1 自愈)。
```

**轻量档(非深度需求可选,调用量约为标准档 1/4、耗时约 2-3 分钟)**:跳过 Step 4/4b,不跑 Swarm——
`run.py --limit 10 --variants 3` → fulltext → 分析 → check → fill_excel → gen_html → verify_html。
无 extension.json 时 fill_excel / gen_html 会自动省略热点拓展块,verify_html 的拓展范围校验也按实际产物判定。

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
- **情绪判断**:三选一 积极/中立/消极,与情绪倾向描述一致。
- **原始链接**:所有问题/回答保留原 URL(Excel 中为超链接)。
- **月度扩展**:新日期直接插入新 sheet 到最前;raw 数据按日期归档,随时可回溯。
- 问题本质列 = 对该问题的主题内容提炼(一句话),回答行该列留空。

## 约束(一~五,不可妥协)

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
- 生成后必须校验,统一用 `python scripts/verify_html.py --root <ROOT> --date <D>`(退出码 0 才算通过):
  详情页数=热榜条数、每页折叠数=回答数、翻页 q 前后衔接(首末页为 `class="off" href="#"`)、根入口跳转路径、索引卡片数、「接口摘要」标签数=非 full 回答数、拓展块仅覆盖前 10。
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
- 主 Agent 汇总时抽查 query 历史(`queries_rank_<n>.json` 与逐轮归档),发现命中即要求重发。

**与发散逻辑的关系**:两条发散线中的"背景"最容易滑向名词解释——社会事件类的②「历史依据与过往案例」只搜**案例与数据**;非时效类的③「真实社会议题」只搜**现象与群体行为的证据**,都不搜术语解释。

## 热点拓展板块(仅热榜前 10,Agent Swarm 并行)

对热榜前 10 名问题做**发散性思维扩展**,同步到 Excel「热点拓展」sheet 与 HTML 问题卡片内的「🧠 热点拓展思考」块。

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

### 执行方式:Agent Swarm(rank 1-10 并行)

主 Agent 负责调度,subagent 负责单个 rank 的完整发散:

1. **前置准备(主 Agent)**:① 读话题库(见下,了解已有话题与案例,避免跨日期重复);② 为每个 rank 建独立工作目录 `ext_search/<D>/rank_<n>/` 与独立查询文件 `ext_search/<D>/queries_rank_<n>.json`(**文件按 rank 隔离,防并发冲突,坑 16**)。
2. **派发**:rank 1-10 各派一个 subagent(可 2-3 个 agent 各包 2-5 个 rank),每个 subagent 独立执行:
   ① 读该 rank 的回答(answers_summary.json 对应段)→ 判断问题类型(社会事件类/非时效类)→ **先立想法,再找证据**:从回答里提炼出 2-4 个可被证据检验的判断,而不是先搜再想
   ② 动态发散搜索:每轮 **1 条**查询(写自己的查询文件、输出到自己的目录,`python scripts/search_many.py <自己的queries.json> <自己的outdir> --db zhihu`),**每轮检索前先做收敛性判断(见下)**;每条证据要判明它对该想法是印证、反驳还是边界
   ③ 收敛即止,产出该 rank 的 `chains`(想法 + 证据 + 落点)+ `thinking`
3. **汇总(主 Agent)**:运行 `python scripts/merge_extension.py --root <ROOT> --date <D>` 完成格式统一、schema 强校验与跨 rank 去重报告,再 `topic_lib.py update` 更新话题库。**不要相信 subagent 的「已校验通过」自述**(实测有 subagent 自述合规但同类型实为 5 条),必须由本脚本复核。

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
      "claim": "想法：回答区里的一个判断（一句话，不含证据）",
      "source": {"answer_index": 3, "likes": 294, "url": "该想法提炼自的那条回答的链接"},
      "evidence": [
        {"relation": "印证", "type": "案例", "content": "要点提炼(60-300字，含数字/时间/主体)",
         "url": "真实来源链接", "note": "这条证据说明了什么、为什么标这个 relation",
         "entities": ["上海疾控", "2025"]}
      ],
      "takeaway": "落点：这条链最后说明了什么（结论，不是复述证据）"
    }
  ],
  "dropped": [
    {"type": "案例", "content": "被收敛掉的同类案例要点(60-300字)", "url": "真实来源链接",
     "note": "与已采用条目同属哪一类", "reason": "为何归为同类而不单列"}
  ],
  "thinking": "发散思考过程(为何立这些想法、检索路径、收敛依据、被舍去的同类案例)"
}
```

- `chains` **必填**且非空;每条链 `claim` 与 `takeaway` 都要写(缺 takeaway 会被 merge 告警、HTML 少一行结论);
- `source`(想法出处)**可选但推荐**:`{"answer_index": N, "likes": N, "url": "http..."}`,指该想法提炼自哪条回答——`url` 从 `answers_summary.json` 该 rank 的 answers 里取,不要手写;格式不对 merge 会告警并忽略;
- `evidence[].entities`(可选但推荐):2–4 个主体锚点(机构/人物/案件名),入库后可用 `search --entity` 按主体查「这家公司/这个人还出现过几次」;
- `dropped`(**可选**):被「同类案例只取一条」收敛掉的同类案例。**不进 items、不进 Excel/HTML**,但会被 `topic_lib` 以 `adopted=false` 入库,使后续发散查重能直接命中「已知同类、已判定不采用」。每条需 `type/content/url`,建议带 `note` 与 `reason`;
- `evidence` 每条必须带 `relation`(不写会被 merge 默认成「印证」并告警);
- 同一 `type`(案例/人物/链路)**≤3 条**(按**该 rank 全部证据**计,不是每条链各算);
- 旧格式(顶层 `items` 扁平列表)**仍被兼容**,但会渲染成"无想法的证据堆",交付物可读性差,新产出不再使用;
- `thinking` 必填,不要用 `divergence_dirs` 等替代字段名;
- `url` 必须取自搜索结果原文链接,禁止伪造;无来源的推断在 content 中标注「推断」;
- 派发 prompt 里直接粘贴本 schema **与「约束五:禁止名词解释类查询」**,并要求 subagent 结束时自报「链数 / 证据数 / type 分布 / 搜索轮数」。
- 派发 prompt 里同时给出**三类首选查询构造式**(具体案件+索赔金额+法院结论 / 调研样本数+百分比 / 人口抽样公报口径)与**「同类案例只取一条,其余写进 thinking 并以『未采用但值得记录——』起头」**这两条规则(见约束五与收敛性判断);主 Agent 汇总时按此复核。

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

### 收敛性判断(每轮检索前必做,命中即跳过本轮)

构造新查询前依次判重,以下任一命中则不执行该查询:

1. **查询主题去重**:新查询词与已执行查询词核心主题重叠(同话题线——如「台风」「观浪」「溺水」已各查过)→ 换角度或停止,不重复搜索;
2. **结果 URL 去重**:上一轮结果的全部 URL 已出现在历史轮次/话题库 → 本轮零新线索;
3. **同类型案例上限**:该 rank 已提炼的发散点中,同一 `type`(案例/人物/链路)已达 **3 条** → 同类不再新增条目(新发现只记入 thinking);
4. **同类案例只取一条(用户 2026-09-12 指定)**:具体案例本质上往往是**对同一类问题的反复讨论**——已有一条支撑某判断后,**除非与已有条目存在极大差别**(如法律定性不同、机制相反、正反两极),否则**只采用一条**,不为同类案例反复搜索、不并列多条。
   - 判据:两条案例若「换成对方,论点强度不变」,即为同类 → 只留一条(留信息量更大、金额/结论/口径更具体的那条)。
   - 被舍去的案例**不要丢弃**:写进该 rank 的 `thinking`,以 **「未采用但值得记录——」** 起头简要交代事实要点与为何归为同类,供日后跨日期复用。

**收敛停止判据**:连续 2 轮无新线索(零新 URL、零新发散点)即止;或 3 条主线均已覆盖且同类型达上限。与话题库比对产生的「已有案例」也算无新线索轮;按第 4 条判定为「同类已有」的案例同样计入无新线索轮,不为凑条数继续搜。

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
- 范围硬约束:**只处理热榜前 10**,第 11-20 名不扩展(主流程四维分析照常覆盖全部 20)。

## 踩过的坑(1-37,勿重蹈)

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

## 脚本清单(skill/scripts/,全流程通用)

| 脚本 | 职责 | 关键参数 |
|---|---|---|
| `contract.py` | **流程数据契约层**:文件名/目录布局/字段名/值域/HTML 结构标记的**单一定义处**,供全部脚本 import;无业务逻辑 | 作为模块:`path_*()` / `report_*()` / `page_name()` / `EMOTIONS` / `ANALYSIS_FIELDS` / `EXT_*` / `HTML_*` |
| `zhihu_env.py` | **基础技术栈适配层**:统一解析 CLI 路径(`ZHIHU_CLI` → `ZHIHU_CLI_HOME` → 平台默认 → 兜底问 zhihu skill 的 status)与凭证库状态;被所有业务脚本 import | 作为模块:`require_cli()` / `diagnose()` / `keychain_present()` / `skill_status()` |
| `doctor.py` | **环境与数据自检**:运行时/脚本完整性/基础栈(CLI+凭证+skill 版本)/ROOT/当日数据;`--discover` 自动发现候选 ROOT | `--root --date --discover --json` |
| `run.py` | 热榜 + 变体搜索 + 合并去重(关键词召回, 作兜底数据源) | `--root --date --limit --variants --resume` |
| `question_fetch.py` | **问题维度抓取**(主数据源):网页接口按赞取每问题最热 N 条, 与搜索召回取**并集**, 适配 Question/Article/Answer 三类条目, 写入 `total_answers`/`coverage`/`source`; 请求级退避重试(防瞬时 403 被静默降级) | `--root --date --top 5 --pages 3 --out --no-merge --retry --backoff` |
| `fulltext.py` | 回答全文补全 + 截断检测(每条自动重试 3 次、失败原因写入 `error`;`--cookie` 解锁全文) | `--root --date --delay --retry --backoff --force --cookie` |
| `search_many.py` | 批量发散搜索(热点拓展用,queries.json 驱动) | `queries.json outdir --db --delay --count` |
| `check.py` | 数据完整性校验(分析齐全/情绪值域/URL/内容/状态) | `--root --date` |
| `merge_extension.py` | **汇总 Swarm 产出** → extension.json:链式结构强校验(每条链 claim/evidence/takeaway、每条证据 relation 值域)、按链展平 `items`(供话题库)、type 值域 / 同类型≤3 / URL / 必填字段、容忍旧的扁平 `items` 与 `divergence_dirs` 变体、报告跨 rank 重复 URL | `--root --date [--ranks 1-10] [--no-strict]` |
| `verify_html.py` | **约束四自动校验**(详情页数/折叠数/翻页/入口/索引/接口摘要/拓展范围),退出码 0 即通过 | `--root --date` |
| `fill_excel.py` | 填月度 Excel(自动建模板、情绪列下拉、截断备注、热点拓展 sheet) | `--root --date --xlsx` |
| `gen_html.py` | 生成 HTML 展示页(原文状态标签、热点拓展块) | `--root --date --out` |
| `topic_lib.py` | 话题库维护(定位:避免重复搜索的 database;维度区隔 type=一级全局索引 / cat=二级主题标签 / date=首次收录日期只作属性):update 增量收录(url 去重 + 日期回填 + 同类体检告警)+ search 查重与筛选(url/type/cat/日期区间/关键词)+ rebuild 重建 md + prune 全库一致性扫描 | `update --root --date` / `search --root --url\|--type\|--cat\|--since\|--until\|--keyword` / `rebuild --root` / `prune --root` |
| `top2_select.py` | 可选工具:对已抓取的**全量** `answers_summary.json` 做瘦身,每问题保留「最高赞 + 最多评论」2 条,用于压缩 Agent 分析开销(现流程通常在抓取时就用 `--top N` 前置控制条数) | `--root --date [--backup]` |

> **历史说明**:早期版本曾用 `api_fetch.py`(API 直拉 + top2 = 最高赞 + 最多评论)作为抓取首选。其职能已由 `question_fetch.py` **完全取代**,且后者更强(并集召回 web ∪ search、覆盖度标注 `total_answers/coverage/source`、Question/Article/Answer 三类条目适配),该脚本已移除;如需查阅可看 git 历史。**现行流程只有一条抓取链**:`run.py`(关键词搜索召回,作兜底)→ `question_fetch.py`(问题维度并集,主数据源)。

所有脚本路径全参数化(`--root` 默认当前目录),不写死任何绝对路径;日期目录 `raw/<D>/` 自动创建。分析步骤(analysis.json)由 Agent 完成,脚本负责抓取/校验/产出。
