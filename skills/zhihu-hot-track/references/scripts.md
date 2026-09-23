# 脚本与模板清单

> 本文件由 `SKILL.md` 拆出(2026-09-14)。参数表是「改脚本前先看」的入口;
> 增删脚本后要同步本表 + `ARCHITECTURE.md` §二, 再跑 `check_docs.py`。

| 脚本 | 职责 | 关键参数 |
|---|---|---|
| `contract.py` | **流程数据契约层**:文件名/目录布局/字段名/值域/HTML 结构标记的**单一定义处**,供全部脚本 import;无业务逻辑;**平台属性(交付物命名/来源文案/域名类别)一律向 `platform_profile` 取,不写死** | 作为模块:`path_*()` / `report_*()` / `page_name()` / `EMOTIONS` / `ANALYSIS_FIELDS` / `EXT_*` / `HTML_*` |
| `platform_profile.py` | **平台档案(换平台的唯一注入点)**:平台名/内容单元/写稿注意事项/交付物命名/来源说明/站内域名类别/接口地址与 URL 模板/检索库名/CLI 与环境变量名/凭证服务名;并声明 `L2_COMPONENTS` 与平台字面量模式供守卫使用。内置 `zhihu` 档案,未内置平台走"通用档案 + `TRACK_*` 环境变量"最小可用路径 | 作为模块:`profile()` / `get()` / `summary()` / `code()`;CLI 覆盖 `TRACK_PLATFORM` / `TRACK_PLATFORM_NAME` / `TRACK_UNIT` / `TRACK_PLATFORM_NOTES` / `TRACK_REPORT_TITLE` / `TRACK_API_BASE` / `TRACK_REFERER` / `TRACK_SOURCE_DB` 等 |
| `zhihu_env.py` | **基础技术栈适配层**:统一解析 CLI 路径(`ZHIHU_CLI` → `ZHIHU_CLI_HOME` → 平台默认 → 兜底问 zhihu skill 的 status)与凭证库状态;被所有业务脚本 import | 作为模块:`require_cli()` / `diagnose()` / `keychain_present()` / `skill_status()` |
| `doctor.py` | **环境与数据自检**:运行时/脚本完整性/基础栈(CLI+凭证+skill 版本)/ROOT/当日数据;`--discover` 自动发现候选 ROOT | `--root --date --discover --json` |
| `check_docs.py` | **组成清单一致性体检(只读)**:磁盘组件 ↔ `ARCHITECTURE.md` §二 分层清单 ↔ 脚本/模板表(`SKILL.md` + `references/*.md`)三方比对 + 扫"改了范围却漏改别处"的旧表述 + **平台字面量守卫**(`platform_profile.L2_COMPONENTS` 之外的文件出现平台名/域名/CLI 名即 FAIL,并双向比对 L2 名单与文档)+ **references 指针可达性**(指了不存在的文件即 FAIL)。**改流程、增删脚本或换平台后跑一次**;退出码 1=不一致 | `[--skill-dir] [--scope-pattern] [--json]` |
| `run.py` | 热榜 + 变体搜索 + 合并去重(关键词召回, 作兜底数据源) | `--root --date --limit --variants --resume` |
| `question_add.py` | **单问题追加追踪**:把单独搜的一个问题注册成当日追加条目(rank 接在榜单之后)、抓高赞回答并入 answers_summary、登记 extra_questions.json、**自动生成 subagent 提示词**(prompt_swarm.md 模板);链接自动规范化、跨日期重复追踪会告警;hot.json 缺失也能用 | `--root --date --url [--top] [--pages] [--rank] [--emit-prompt] [--no-cross-day-check] [--dry-run]` |
| `question_fetch.py` | **问题维度抓取**(主数据源):网页接口按赞取每问题最热 N 条, 与搜索召回取**并集**, 适配 Question/Article/Answer 三类条目, 写入 `total_answers`/`coverage`/`source`; 请求级退避重试(防瞬时 403 被静默降级);**cookie 预检(2026-09-21 起, 默认开)**:开跑前用第 1 个问题类条目试抓 2~3 个请求, 前 3 条回答**全部 summary** 或抓取即 403 → `[FATAL]` 中止并打印方式 C 配方(坑 77 的预防面, 不必烧完 99+ 请求才发现) | `--root --date --top 5 --pages 3 --out --no-merge --retry --backoff --no-preflight` |
| `fulltext.py` | 回答全文补全 + 截断检测(每条自动重试 3 次、失败原因写入 `error`;`--cookie` 解锁全文);结束时打印 **[死答] N 条无正文**(content_status=summary 且 text 空, 附坑 78 处置提示 —— 不必等 check「内容为空」才炸出) | `--root --date --delay --retry --backoff --force --cookie` |
| `extract_cookie.py` | **Cookie 自愈提取**(2026-09-21 新增,L2):从 playwright storageState JSON 提取登录 Cookie 写 `raw/<D>/cookies.txt` —— **单行 Cookie 头、UTF-8 无 BOM**(坑 25),缺 `z_c0` 打 WARN(未登录态)。**cookie 跑一半失效的自愈配方(坑 77)**:playwright-cli `state-save` 出 json → 本脚本 → 重跑 question_fetch 并集 + fulltext | `--state <zhihu-state.json> --out <路径> [--domain zhihu.com]` |
| `search_many.py` | 批量发散搜索(热点拓展用,queries.json 驱动)。**每次检索同时产出完整归档 + `.slim.json` 精简版**(只留标题/链接/作者/赞评/220 字摘要, 约 1/4 体积)供 subagent 优先读 | `queries.json outdir --db --delay --count`(默认 4) |
| `render_answers.py` | **分析前批量渲染**:把当日回答按 `--per` 打包渲染成硬换行文本(低于 read 单行 2000 上限), 主 Agent 整批读而非逐 rank 读(省读取步数与补读轮次) | `--root --date [--ranks 1-20] [--per 5] [--wrap 900]` |
| `regress_pipeline.py` | **回归验证(改脚本后必跑)**:临时 ROOT 复制当日 `raw/`+`ext_search/`+`话题库/`+`书写skill/` → 重跑 check/fill_excel/gen_html/verify_html/topic_lib → 根入口/详情页/话题库**逐字节**、Excel **当日 sheet 逐单元格**比对(其余 sheet 跨日累积, 单日临时根不可比, 明确跳过并注记 —— 多日月份整簿比对必误报, 坑 81);差异先怀疑数据本身(坑 69) | `--root --date [--python] [--tmp] [--keep]` |
| `check.py` | 数据完整性校验(分析齐全/情绪字段值域/URL/内容/状态)。情绪**两套模型都认**:有 `emotion_tags` 按新模型校验(标签∈词表且≤3、强度 1-5、指向∈6类), 只有 `judge` 时按旧三元校验, 两者都无=漏标 | `--root --date` |
| `merge_extension.py` | **汇总 Swarm 产出** → extension.json:链式结构强校验(每条链 claim/evidence/takeaway、每条证据 relation 值域)、按链展平 `items`(供话题库)、type 值域 / 同类型≤3 / URL / 必填字段、容忍旧的扁平 `items` 与 `divergence_dirs` 变体、报告跨 rank 重复 URL 与**同一 URL 多内容**、`entities` 缺失告警、**`chains[].source` 与原答对账**;**`--lint` 只读模式**供 subagent 自查(不写文件、可单 rank 跑、有硬错误退出码 1) | `--root --date [--ranks 1-20] [--no-strict] [--lint]` |
| `verify_html.py` | **约束四自动校验**(详情页数/折叠数/翻页/入口/索引/接口摘要/**情绪渲染对账**/**发帖短评渲染对账**/拓展范围),退出码 0 即通过 | `--root --date` |
| `fill_excel.py` | 填月度 Excel(自动建模板、情绪三列(标签/强度/指向)+强度与指向下拉、截断备注、热点拓展 sheet、**发帖短评 sheet**——2026-09-16 由「拟答参考」就地更名(历史行不分裂),末尾**追加「待发帖」状态列**(待发/已发/过闸待写/超上限/打回·中庸/打回·字数/待复核));`emotion_cells()` 兼容新旧模型;每次运行刷新「说明」sheet | `--root --date --xlsx` |
| `gen_html.py` | 生成 HTML 展示页(原文状态标签、热点拓展块、**多元化情绪 chips/强度点/指向签/图例**、**✍️ 发帖短评块:标题「✍️ 发帖短评(N 字 · 50–100 字犀利向 · 状态徽标)」,徽标读 publish_queue.json:2026-09-21 起 `ready→「推荐 #N」`、`over_daily_cap→「备选·超今日建议 #N」`;字数=正文口径(标题行不计,与队列一致)**);`emotions_of()` 兼容新旧模型;**索引页「今日短评」挑稿面板(2026-09-21 起)**:`.dpanel` 按 priority 列出 ready(推荐 #N)与 over_daily_cap(备选 #N), 含 rank/稿标题/正文前 42 字/字数, 链接 `{page_name}#draft`(详情页短评块已加 `id="draft"` 锚点);队列缺失/无稿时整块不出现 —— 挑稿一屏完成, 不用翻详情页 | `--root --date --out` |
| `gen_prompts.py` | **生成 subagent 提示词**(2026-09-13 新增,取代一次性脚本):`--ranks 1-20` 出拓展 `PROMPT.md`;**`--combo --per 5` 出复合提示词 `COMBO_PROMPT_<tag>.md`(情绪标注 + 书写逻辑提取, 一次读两份产出, 2026-09-14 起推荐)**;`--emotion` / `--style --per 5` 只出其中一路(补跑用);**`--gate` 出前置判断提示词(2026-09-16 新增, 内嵌 `publish_queue.py --signal` 预计算信号表, 判定 subagent 写 publish_verdicts.json)**;**`--gate --stage0` 出阶段0 预闸门提示词(2026-09-21 新增: 检索前只判时政 → publish_verdicts_pre.json, 不嵌信号表 —— extension.json 还没生成)**;**默认模式(拓展提示词)省略 --ranks 时按预闸名单自动过滤**(`pregated_ranks()`: pre 文件缺失=未跑预闸门 → 返回全部 rank, 行为与旧版一致), 打印 `[预闸门] 过闸 rank: [...]`, 显式 --ranks 可全量;`--write` 出发帖短评书写提示词,**省略 `--ranks` 时默认给全部过闸 rank 写**(2026-09-21 起不按每日上限预裁剪,推荐/备选由 publish_queue 排序裁决;`--top N` 为可选的旧式裁剪 = 只给前 N 个过闸 rank 写);`--all` = 拓展 + 复合 + 前置判断 + 书写(**四类**)。目录命名遵循历史约定(目录/查询文件不补零,检索留档补零)。**平台参数化**:取值全部来自 `platform_profile`(可用 `TRACK_*` 覆盖),模板内无平台硬编码 | `--root --date [--ranks] [--combo] [--emotion] [--style] [--gate] [--stage0] [--write] [--per] [--top] [--all]` |
| `prompt_swarm.md` | **拓展发散 subagent 模板**(热点拓展板块的派发提示词):问题类型判定(社会事件类/非时效类)、两条发散路线、三类首选查询构造式、**约束五(禁名词解释类查询)**、信源门槛、链式 schema 与自报格式。**出题思路含「增量导向」段(2026-09-16 起):优先采回答区/评论区没有的新数字/新文书/新机制/新案例**;「发帖短评:不在本步产出」——只有过闸 rank 才写短评(见 Step 4c) | 作为模板被 `gen_prompts.py` 填充(默认 `--ranks` 即出拓展提示词);`question_add.py --emit-prompt` 也用它 |
| `prompt_emotion.md` | **情绪判断 subagent 模板**(2026-09-13 新增):词表/判据/四条边界裁决(讽刺vs调侃、强度锚点、指向优先序、负面情绪四选一)/标定样例/必填 `why` | 作为模板被 `gen_prompts.py` 填充 |
| `prompt_style.md` | **书写逻辑提取 subagent 模板**(学习 loop 的学习端):**11 个固定提取维度**(2026-09-16 增「犀利度与锋芒」)、**铁律"只提怎么写、不提写了什么"**(含"改写测试"判定法)、输出 schema(patterns/avoid/notes, 带 scope 与 freq);**犀利是硬要求——该维度至少给 2 条 patterns, 中庸写法进 avoid** | 同上(`--style`) |
| `prompt_write.md` | **发帖短评书写 subagent 模板**(学习 loop 的应用端,2026-09-16 由拟答稿模板重写):**不检索**, 读 `书写skill.md` + 本 rank 的链证据 → 写 `draft_<n>.md`;**50–100 字犀利短评**(骨架=判断→机制/代价→落点, 第一句钉死判断, 允许暴论, 中庸句式黑名单, 正文零链接, 事实纪律不变);内置反例清单 | 同上(`--write`) |
| `fix_chain_source.py` | **元数据机械修复**:`chains[].source` 的 `answer_index`/`url` 与原答错配时, 按随附的可核对字段(likes/url)反查正确引用并回填; 修不了的列出来交人。修完必须重跑 `merge_extension.py` + 交付链 | `--root --date [--ranks] [--dry-run]` |
| `merge_style.py` | **书写逻辑候选池汇总**: 折叠近义重复(同维度相似度≥0.62)、按维度归类、给跨批频次, 供主 Agent 用奥卡姆剃刀取舍 | `--root --date [--write]` |
| `publish_queue.py` | **前置判断汇总 + 待发帖列**(2026-09-16 新增; 自动发帖三件套已删, 本脚本是其替代):校验判定(publish_verdicts.json;判定与脚本信号相反的条目列「分歧复核」)→ **三道闸门**(①时政:非时政不进列 ②增量:证据须有评论区/回答区没有的新东西, 基线优先 comments.json 缺则降级回答区 ③中庸:`MEDIOCRE_PATTERNS` 正则黑名单硬拦)→ **过闸条目全部检查稿件**(2026-09-21 起, 不再按上限预分配预算;无稿=draft_pending, 字数越界/中庸/犀利度未判照旧打回)→ 有效稿按**情绪强度(analysis 各回答最大值)降序 → 回答区最高赞降序 → rank 升序**排序存 `priority`(1 起; 新字段 `emotion_top`/`top_like`/`priority`)→ 前(上限−已发布)条 = `ready`(推荐), 其余 = `over_daily_cap`(**备选**: 稿照常进待发帖列与 HTML, 人工终审可换掉任一推荐条目改发备选)→ 待发帖 md 头部写「推荐 N 条(每日上限 X)+ 备选 M 条」与排序规则, **推荐 #k 与备选 #k 全文都渲染**;`--mark` 供人工发布后回填(对备选同样有效;队列=publish_queue.json 是"发到哪一步"的唯一事实源);`--signal` 打印预计算信号(判定 subagent 的输入, 零 token);**`--sharp` 犀利度复核回填(2026-09-21 起)**:`--sharp "N=<true|false>:<依据>"`(可重复, true=判中庸打回)原子写回 publish_verdicts.json 后**本命令继续重跑闸门汇总与渲染** —— 取代主 Agent 手写临时脚本(阶段二复核照旧由主 Agent 亲自读稿裁决);**`--mark` 归属校验(2026-09-21 起)**:链接必须是 `question/<qid>/answer/<aid>` 形态且 qid 必须等于该 rank 的问题 id, 否则 FAIL 拒绝回填(防贴错行) | `--root --date [--signal] [--status] [--mark "N=<url>"] [--sharp "N=<true|false>:<依据>"]` |
| `unfollow_question.py` | **可选后续功能**: 生成"取消问题关注"的 run-code 脚本(发布回答会自动关注该问题, 属平台行为); 幂等, 已是「关注问题」则跳过 | `--out <js>` |
| `prompt_gate.md` | **前置判断 subagent 模板**(2026-09-16 新增): 逐 rank 判 **是否时政 + swarm 证据有无增量信息**(对照评论区/回答区基线, 基线优先 comments.json, 缺则降级回答区并写 `baseline` 字段), 必填 `political_basis`/`increment_basis`/`why`; 产出 `raw/<D>/publish_verdicts.json`; 判定与脚本信号相反的条目交主 Agent 分歧复核 | 作为模板被 `gen_prompts.py --gate` 填充(内嵌 `publish_queue.py --signal` 信号表) |
| `prompt_gate_pre.md` | **阶段0 预闸门 subagent 模板**(2026-09-21 新增): 检索前只判时政 —— **不检索、不读 extension.json(还没生成)、不嵌信号表**, 判定只看题目与回答区; **从宽原则**(拿不准一律判「是」, 宁多搜不误杀; 判 `false` 必须具体说出为何不涉公权力); 产出 `raw/<D>/publish_verdicts_pre.json`(只含 rank/is_political/political_basis/why, 见 `contract.VERDICT_PRE_REQUIRED`) | 作为模板被 `gen_prompts.py --gate --stage0` 填充(一份覆盖全部 rank) |
| `merge_emotion.py` | **情绪片段合并 + 分歧对账**(情绪下放 subagent 的必备收尾): 结构校验(词表/≤3/不重复/强度1-5/指向6类/数组长度==回答数)+ 与 `analysis.json` 现有判定逐条比对(`--compare` 只出分歧, `--write` 合并, `--json` 机读); 写入时保留 `emotion_why` 供审计 | `--root --date [--frag a.json …] [--compare] [--write] [--json]` |
| `run_pipeline.py` | **一键跑完交付链路并逐关校验**: [情绪合并] → [汇总] → check → fill_excel → gen_html → verify_html, 失败即停并报是哪一关; **不跑 Swarm/不抓取/不发布** | `--root --date [--merge] [--emotion] [--no-links] [--skip-verify]` |
| `merge_extension.py` | **汇总 Swarm 产出 + 事实性复核(二合一)**:链式结构强校验(claim/evidence/takeaway、relation 值域)、按链展平 `items`、type 值域 / 同类型≤3 / URL、容忍旧的扁平 `items`、报告跨 rank 重复 URL;写出后**自动调用** `verify_ext.run()` 打信源等级/算多源印证/探活链接 | `--root --date [--ranks 1-20] [--no-strict] [--no-verify] [--no-links] [--link-delay]` |
| `verify_ext.py` | **发散证据事实性复核**(通常由 merge 自动调用, 也可单独补跑):信源门槛兜底打标(A/B/C/D,锚点=数值+**制度性**)、entities 兜底自动抽取、多源印证(当日检索归档池 + 3-gram 同源折叠识别洗稿)、链接探活(**5xx/超时退避重试**)、归档核对(url 是否真出自检索结果);结果写回 extension.json, 报告写 `raw/<D>/ext_verify.json` | `run(root, date, no_links, delay, quiet)` / CLI `--root --date [--no-links] [--delay] [--json]` |
| `topic_lib.py` | 话题库维护(定位:避免重复搜索的 database;维度区隔 type=一级全局索引 / cat=二级受控标签 / date=首次收录 / last_seen=最近命中):update 增量收录(url 去重 + 日期回填 + 同类体检告警)+ search 查重与筛选(url/type/cat/tier/日期区间/关键词/主体)+ rebuild 重建 md + reindex 重建 sqlite + prune 全库一致性扫描 | `update --root --date` / `search --root --url\|--type\|--cat\|--tier\|--entity\|--since\|--until\|--keyword\|--json\|--adopted-only` / `rebuild --root` / `reindex --root` / `prune --root` |

### 文档与产物清单(skill 目录内的非脚本件)

| 文件 | 层 | 职责 | 换平台时 |
|---|---|---|---|
| `SKILL.md` | — | **核心常驻部分**:触发规则、组成、基础技术栈、契约、前期准备(含成本口径)、执行流程、约束一~五、热点拓展板块、话题库/信源门槛/收敛判据 | 改 L2/L3 相关段落 |
| `references/pitfalls.md` | — | **踩坑库 1-81**(含主题索引)。**按需读**:开工前只在换环境/异常时看主题索引, 踩坑时按关键字 grep | 仍适用, 平台专有坑随平台失效 |
| `references/scripts.md` | — | 本文件:脚本与模板清单 + 文档与产物清单(**按需读**, 改脚本前先看参数) | 同 SKILL.md |
| `ARCHITECTURE.md` | L1 | **架构与泛用性分层**:四层结构、逐组件标注「属哪层 / 怎么复用」、四块最强泛用件、迁移指南、已知缺口 | **带走**(迁移时先读它) |
| `writing_method.md` | L1 | **书写方法(通用件)**:为什么三段分工、提取端的铁律与改写测试、汇编端的奥卡姆四条规则、**必须提防的"数据假象"**、应用端约束、累积与版本、复用清单 | **带走**(唯一被单独抽出的通用件) |
| `scripts/prompt_style.md` / `prompt_write.md` | L1 | 学习 loop 的提取端 / 应用端模板,**已参数化**(`{platform}` / `{unit}` / `{platform_notes}`) | 只改平台档案 |
| `scripts/prompt_emotion.md` / `prompt_swarm.md` | L1 | 情绪判断 / 拓展发散模板(**已参数化**, 2026-09-14 从 L2 降级);词表与判据是通用件, 平台措辞由档案 `notes` 注入 | 只改平台档案 |
| `<ROOT>/书写skill/书写skill.md` | **L4 产物** | **书写 skill 本体**(自我学习 loop 的累积结果,与话题库同构):26 条规则 + 8 条禁令 + 一页速查 | **不带**(在新平台重新学一遍) |
| `<ROOT>/话题库/` | L4 产物 | 跨日期累积话题库(index.json 机读 + md 人读) | **不带** |
| `<ROOT>/raw/<D>/` · `ext_search/<D>/` | L4 产物 | 原始存档 / Swarm 产出 / 学习 loop 留档 | **不带**(留作溯源) |

> **一句话记法**:`ARCHITECTURE.md` 回答"哪块能搬",`writing_method.md` 回答"书写这块怎么搬",
> **书写 skill 本体是学出来的、不是搬出来的**。

> **历史说明**:早期版本曾用 `api_fetch.py`(API 直拉 + top2 = 最高赞 + 最多评论)作为抓取首选,并配套 `top2_select.py` 做后置瘦身(把已抓取的全量回答压成每问题 2 条)。两者均已**移除**:抓取职能由 `question_fetch.py` 完全取代(并集召回 web ∪ search、覆盖度标注 `total_answers/coverage/source`、Question/Article/Answer 三类条目适配),条数控制改由 `question_fetch.py --top N` **前置**完成(后置瘦身会破坏 `analysis.json` 与 `extension.json` 已按回答序号对齐的结构);如需查阅可看 git 历史。**现行流程只有一条抓取链**:`run.py`(关键词搜索召回,作兜底)→ `question_fetch.py`(问题维度并集,主数据源)。

所有脚本路径全参数化(`--root` 默认当前目录),不写死任何绝对路径;日期目录 `raw/<D>/` 自动创建。分析步骤(analysis.json)由 Agent 完成,脚本负责抓取/校验/产出。
