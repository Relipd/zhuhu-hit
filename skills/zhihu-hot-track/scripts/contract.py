# -*- coding: utf-8 -*-
"""流程数据契约:文件名、目录布局、字段名与约束的**单一定义处**。

为什么需要这一层
----------------
本流程由十余个脚本接力完成,它们通过**约定好的文件与字段**互相通信。引入本模块之前,
这些约定以字面量形式重复散落在各脚本中——`"hot.json"` 出现在 6 个脚本、情绪三值出现在
4 个脚本、HTML 结构标记出现在 2 个脚本。由此带来两个问题:

  1. 改一处约定要改多个文件,且容易漏改;漏改不会报错,只在运行期表现为"文件找不到"
     或"校验莫名失败"(本流程历史上已在 merge 覆盖、search_many 同名覆盖上踩过同类问题)。
  2. 脚本之间的真实依赖不可见,判断"这个脚本的上游是谁"只能靠通读代码。

本模块把约定收敛为**唯一来源**。各脚本只从本模块取约定,不再书写字面量。

数据流(→ 表示写入,← 表示读取)
-------------------------------
    hot.json             → run.py
                         ← check / fill_excel / gen_html* / doctor / question_fetch / verify_html
    answers_summary.json → run.py(初始:搜索召回)
                         → question_fetch.py(重写:与问题维度结果并集)
                         → fulltext.py(就地补齐正文与状态)
                         ← check / fill_excel / gen_html / verify_html / doctor
    analysis.json        → Agent(逐条四维分析)
                         ← check / fill_excel / gen_html / doctor
    extension.json       → merge_extension.py(汇总各 rank 产出)
                         ← topic_lib / fill_excel / gen_html / doctor
    cookies.txt          → Cookie 获取步骤(见 SKILL.md Step 1.2)
                         ← zhihu_env(定位复用之) / fulltext / question_fetch

    (*) gen_html 通过 answers_summary + analysis + extension 三者联合渲染。

分层(谁依赖谁)
--------------
    contract.py          ← 所有脚本(只提供常量与路径函数,无业务逻辑)
    zhihu_env.py         ← 需要访问平台 CLI / 凭证的脚本(run / question_fetch / fulltext / doctor)
    其余脚本             ← 只依赖 contract(纯文件与字段处理,与采集平台无关)

换主题或换平台时改哪里
----------------------
  · **换交付物命名/字段约定**:只改本文件常量。但**文件名不要随意改动**——历史
    `raw/<日期>/` 数据依赖这些名字,改名等于放弃向后兼容,需另写迁移。
  · **换采集平台**:改 `zhihu_env.py` 与 `run.py` / `question_fetch.py` / `fulltext.py`;
    check / fill_excel / gen_html / verify_html / merge_extension / topic_lib 不受影响
    (它们只处理"榜单条目 + 回答 + 分析 + 拓展"这套与平台无关的结构)。
"""
import os
import re

import platform_profile as pf          # L2 平台档案(换平台的唯一注入点)

# ────────────────────────────── 目录与文件名 ──────────────────────────────

RAW_DIRNAME = "raw"                    # <root>/raw/<date>/
FILE_HOT = "hot.json"                  # 榜单条目(标题/链接/摘要)
FILE_ANSWERS = "answers_summary.json"  # 回答(含正文、赞数、获取状态、覆盖度元数据)
FILE_ANALYSIS = "analysis.json"        # 逐条四维分析(由 Agent 撰写)
FILE_EXTENSION = "extension.json"      # 前 N 名的延伸检索产出(由 Swarm 产出后汇总)
FILE_COOKIE = "cookies.txt"            # 网页登录凭证(供复用)
FILE_EXTRA = "extra_questions.json"    # 单问题追加追踪登记(不等同榜单条目, rank 接在榜单之后)

LIB_DIRNAME = "话题库"                  # <root>/话题库/
LIB_INDEX = "index.json"               # 机读索引(唯一键去重)
LIB_MD = "话题库.md"                    # 人读视图(由 index 重建,勿手改)
# 话题库条目字段(2026-09-12 用户要求):
#   · 保留时间维度, 但**不用时间做区隔** —— date(首次收录)/last_seen(最近命中)只是条目属性,
#     一条 url 只一行, 不按日期分桶、不因多日出现而重复入库;
#   · **聚合维度到 type**(案例/人物/链路) —— 只有 3 个稳定取值, 适合当全局一级索引;
#     cat 是主题标签, 走受控词表(见 LIB_CATS), 仅作二级分组。
LIB_SCHEMA = 2                          # index.json schema 版本(每次改字段结构都要 +1)
LIB_FIELDS = ("date", "last_seen", "type", "cat", "content", "url")
LIB_OPT_FIELDS = ("entities", "adopted", "claim", "relation", "claim_source_url",
                  "source_tier", "corroborated", "link_status")
LIB_GROUP_FIELD = "type"               # 人读视图(index→md)的分组维度
LIB_SQLITE = "index.sqlite"            # 加速索引(派生物, 由 index.json 重建)
LIB_SIMILAR_RATIO = 0.55               # 「疑似同类」相似度阈值(仅告警, 不自动合并)
LIB_SHINGLE_JACCARD = 0.30             # 相似度比对的预筛阈值(3-gram 集合 Jaccard)

# 受控主题词表(一级维度是 type, 这里只约束二级标签):
#   cat 曾是自由文本, 实测跨天累积后出现同义分叉(「消费电子」vs「半导体与消费电子」、
#   「网络谣言治理」vs「健康科普与科技辟谣」)。未命中词表的一律归入 LIB_CAT_FALLBACK 并告警。
LIB_CAT_FALLBACK = "其他"
LIB_CATS = (
    "医疗健康",
    "网络谣言与科普争议",
    "家庭关系与教育",
    "消费电子与半导体",
    "司法与法治",
    "外交政策与国际关系",
    "家居与居住",
    "影视与短剧",
    "消费变迁与代际文化",
    "劳动权益与消费",
    "国际冲突与军事",
    "体育产业与赛事治理",
    "教育与社会流动",
    "食品与消费",
    "历史与社会生活",
    "社会心理",
    "社会事件与法律责任",
)
# 历史自由文本 → 受控词
LIB_CAT_SYNONYMS = {
    "网络谣言治理": "网络谣言与科普争议",
    "健康科普与科技辟谣": "网络谣言与科普争议",
    "网络谣言与平台治理": "网络谣言与科普争议",
    "消费电子": "消费电子与半导体",
    "半导体与消费电子": "消费电子与半导体",
    "美食烹饪/消费与食品工业": "食品与消费",
    "历史文化/社会生活史": "历史与社会生活",
    "家庭与教育": "家庭关系与教育",
    "汽车行业": "消费电子与半导体",
    "硬件与算力": "消费电子与半导体",
    "医疗安全": "医疗健康",
    "自然灾害安全": "社会事件与法律责任",
    "跨境犯罪与安全": "司法与法治",
    "影视行业": "影视与短剧",
    "文学与文化": "历史与社会生活",
}

# 交付物命名来自平台档案(platform_profile.py); 换平台只改档案, 本文件不动。
REPORT_TITLE = pf.get("report_title")   # 交付物名称前缀(取自平台档案的 report_title)
XLSX_PREFIX = pf.get("xlsx_prefix")     # 月度表格名称前缀, 如「跟进excel」

HTML_INDEX_NAME = "index.html"
HTML_PAGE_FMT = "q{:02d}.html"         # 详情页命名

# ────────────────────────────── 榜单与回答字段 ──────────────────────────────

HOT_ITEMS_PATH = ("Data", "Items")     # hot.json 里条目数组的位置
HOT_FIELD = {"title": "Title", "url": "Url", "summary": "Summary"}

# 回答条目字段(写入方构造、读取方消费,两侧必须一致)
ANS_FIELDS = ("url", "text", "likes", "author", "comment_count", "content_status")
# 问题级元数据:total_answers/coverage 用于覆盖率标注,source/sources 记录数据来源
ANS_META_FIELDS = ("total_answers", "coverage", "source", "sources")
# 正文获取状态:full=全文 / truncated=接口亦截断 / summary=仅摘要
CONTENT_STATUS = ("full", "truncated", "summary")

# ────────────────────────────── 四维分析契约 ──────────────────────────────

# ── 情绪模型(2026-09-13 用户要求「多元化情绪, 不要三元简化」) ──────────────────
# 新模型: 多标签 + 强度 + 指向。三元(积极/中立/消极)不再落库, 仅作**历史数据的渲染兜底**
# (EMOTIONS / judge 保留, 08-21·09-11·09-12 的 analysis.json 仍是旧结构, 必须继续能出页面)。
EMOTION_TAGS = ("愤怒", "讽刺", "忧虑", "失望", "无奈", "共情",
                "振奋", "认同", "调侃", "审慎", "悲悯", "漠然")
EMOTION_TAG_MAX = 3                       # 每条回答最多保留几个标签
EMOTION_INTENSITY = (1, 2, 3, 4, 5)       # 1 极淡 → 5 极强
EMOTION_TARGETS = ("当事人", "涉事机构", "制度环境", "舆论与媒体", "自身经历", "泛化社会")
EMOTION_DIMS = ("emotion_tags", "emotion_intensity", "emotion_target")
# 标签分色(HTML/Excel 共用): 按情绪基调归 5 组, 同组同色系, 避免 12 种颜色各说各话
EMOTION_TAG_TONE = {
    "愤怒": "hot", "讽刺": "hot",
    "忧虑": "cold", "失望": "cold", "无奈": "cold", "悲悯": "cold",
    "共情": "warm", "认同": "warm",
    "振奋": "up",
    "调侃": "wry", "审慎": "dry", "漠然": "dry",
}
# 旧三值 → 新标签的展示映射(仅用于历史日期渲染, 不改写历史数据)
EMOTION_LEGACY_TAG = {"积极": "振奋", "中立": "审慎", "消极": "忧虑"}
# 底色(内联 style 用; 与 gen_html 的 CSS 类同色, 改一处即可)
EMOTION_TONE_COLOR = {"hot": "#c0493a", "cold": "#5b7c99", "warm": "#2f7d4f",
                      "up": "#b08d2e", "wry": "#8a6f9e", "dry": "#8a8a8a"}
EMOTION_LEGACY_COLOR = {"pos": "#2f7d4f", "neu": "#8a8a8a", "neg": "#c0493a"}
EMOTION_TONE_LABEL = {"hot": "愤激", "cold": "低落/忧思", "warm": "亲和",
                      "up": "昂扬", "wry": "戏谑", "dry": "克制/平淡"}

ANALYSIS_CORE = ("stance", "approach", "logic", "emotion")   # 两套模型都必须有的四维主体
ANALYSIS_FIELDS = ANALYSIS_CORE + EMOTION_DIMS                # 新模型(2026-09-13 起)
ANALYSIS_LEGACY_FIELDS = ANALYSIS_CORE + ("judge",)           # 旧模型(历史日期仍可用)
ANALYSIS_ESSENCE = "essence"
EMOTIONS = ("积极", "中立", "消极")     # 旧三值域(仅历史数据校验/渲染)
EMOTION_CSS_CLASS = {"积极": "pos", "中立": "neu", "消极": "neg"}

# ────────────────────────────── 延伸检索产出契约 ──────────────────────────────

EXT_TYPES = ("案例", "人物", "链路")
EXT_MAX_PER_TYPE = 3                   # 同一类型条目上限(超出部分写入 thinking)
EXT_REQUIRED = ("type", "content", "url", "note")
EXT_CONTENT_LEN = (60, 300)            # content 建议长度(超出仅告警)

# ── 发散链结构(2026-09-12 用户要求: 热点拓展必须是结构化分析, 不是扁平条目堆叠) ──
# 一条链 = 一个想法(回答区里的判断) → 一组证据(各自印证/反驳/限定该想法) → 一个落点。
# 生成方(subagent / Agent)写 chains; merge_extension 校验后**同时展平出 items**,
# 使话题库(按 url 收录)与旧格式消费者无需改动。
EXT_CHAIN_FIELDS = ("claim", "evidence", "takeaway")
EXT_RELATIONS = ("印证", "反驳", "边界")   # 证据对想法的关系; 边界=只在附加条件下成立
EXT_RELATION_DEFAULT = "印证"
EXT_RELATION_CSS = {"印证": "ok", "反驳": "no", "边界": "mid"}
# 未采用但值得记录(被「同类案例只取一条」收敛掉的案例): 不进 items/交付物, 但会以
# adopted=false 入话题库, 使后续发散查重能命中「已知同类、已判定不采用」。
EXT_DROPPED_FIELDS = ("type", "content", "url", "note", "reason")

# ── 信源门槛与事实性复核(2026-09-12 用户要求) ──────────────────────────────
# 前提: 本流程的信源集中在单一内容平台, 交付的其实是**「该平台公众言论」的事实性提炼**, 不是已核实的事实。
# 因此采信标准按「言论」定: 谁说的(归属) + 有没有可核锚点(数字/条号/公报口径) + 是事实还是主张。
# 判定权在**采集端(subagent)**; 脚本只做兜底打标 —— 实测纯正则识别「具名主体」会把
# 「华为发布 Mate XT 2」这类专有名词判成无具名(31/65 条落入"待定"), 误杀率过高, **不可硬拦截**。
EXT_SOURCE_TIERS = {
    "A": "事实性(具名主体+可核锚点)",
    "B": "待定(有可核锚点, 未见具名主体)",
    "C": "不采信(匿名归属, 仅作平台观点)",
    # 2026-09-13 改措辞: D 的判据是「锚点不足」, 与「有没有具名主体」无关 ——
    # 具名律师的阐释性主张同样落 D(它没有可核数值/文书锚点), 旧措辞「无锚点」易被读成"匿名"。
    "D": "观点/主张(可核锚点不足)",
}
EXT_TIER_ORDER = ("A", "B", "C", "D")
# 匿名/转述归属 → 不可作为事实采信(用户举例: 「有从业者对比称, 2000粉博主月入3000-4000元」)
# 注意: 不能直接写 `据称` —— 实测「CIA数**据称**」会被子串误命中, 必须加否定环视。
EXT_HEARSAY = (r"有从业者|业内人士|(?<![数据根依论票证])据称|据传|据说|网传|据悉|"
               r"网友(称|表示|爆料)|有人(称|说)|知情人|传闻|爆料称|相关人士|某(博主|公司|企业)")
# 具名主体(**严格版**): 只认"专有名词形态" —— 实测宽松版把「品牌投放」「报告」当具名主体,
# 会把用户举例的「有从业者对比称…」那条顶出「不采信」桶(它本该在里面)。
# 形态 = 书名号引用 / 独特媒体与机构名 / 「[中文2-6字]+机构后缀」/ 中文人名+职务
EXT_NAMED = (r"《[^》]{2,24}》|新华社|央视|人民日报|澎湃|界面新闻|财新|第一财经|南方周末|"
             r"华盛顿邮报|纽约时报|路透|美联社|CNN|BBC|彭博|华尔街日报|CIA|白宫|五角大楼|"
             r"[\u4e00-\u9fa5]{2,6}(局|院|部|委|署|中心|集团|公司|大学|银行|法院|检察院|"
             r"研究所|研究院|协会|基金会|实验室|统计局|疾控中心|白皮书|公报)")
# 常见姓氏(entities 兜底抽取人名用)。2026-09-13 实测: 只靠「名字后面跟着职务词」判人名会
# 大量误抽 —— 「长沙市律师协会」里的「长沙市」「律师协会」、「有从业者对比称」里的「业者对比」
# 都会被当成姓名。必须再用**姓氏锚定** + 职务紧邻。
EXT_SURNAMES = ("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章"
                "云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常"
                "乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞"
                "熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍"
                "虞万支柯管卢莫房裘缪解应宗丁宣邓郁单杭洪包诸左石崔吉龚程邢裴陆荣翁荀羊甄曲封芮储"
                "靳段富巫乌焦巴弓牧山谷车侯全班秋仲伊宫宁仇栾甘厉祖武符刘景詹束龙叶幸司韶黎薄印宿"
                "白怀蒲鄂索咸赖卓蔺屠蒙池乔胥苍双闻莘党翟谭贡劳姬申扶冉郦雍桑桂濮牛寿通边扈燕冀浦"
                "尚农温别庄晏柴瞿阎慕连茹习宦艾鱼容向古易慎戈廖庾居衡步都耿满弘匡国文寇广禄阙东欧"
                "沃利蔚越隆师巩聂晁勾敖融冷辛阚那简饶曾沙养鞠须丰巢关查后荆红游竺权盖益桓")
# 人名形态 = 姓氏 + 1-2 字 + **紧邻**职务词。
# 2026-09-13 实测两轮教训:
#   ① 只靠「后面跟着职务/动词」判人名 → 「长沙市律师协会」被抽成「长沙市」「律师协会」;
#   ② 加上姓氏锚定、但职务词里含**机构后缀同形字**(律师/会长)或**动词**(表示/称/受访) →
#      仍抽出「沙市」(沙+市, 撞上"律师")「师协会」(撞上"副会长")「时明确」(撞上"表示")。
# 故只保留**强职务名词**(不会是机构名的一部分): 宁可少抽, 不污染话题库检索。
EXT_PERSON_TITLE = "博士|教授|研究员|所长|局长|副部长|部长|主任|院长|院士|总监|总裁|总经理|经理|记者"
# 法规条号/案号 也属可核锚点(中文数字, 数字正则抓不到)
# 2026-09-13 修: 去掉裸 `案号` —— 它会把「已有带案号、带金额的判例」里的**这个词本身**
# 当成锚点(实测 rank9 因此多算一个); 改为只认真实的案号形态, 并补人民法院案例库入库编号。
EXT_ANCHOR_EXTRA = (r"第[一二三四五六七八九十百零〇\d]+条|法释〔\d{4}〕\d*号?|〔\d{4}〕\d+号|"
                    r"[（(]\d{4}[)）][^\s，。；、]{0,12}\d+号|[\u4e00-\u9fa5]{0,4}案例〔\d{4}〕\d+号|"
                    r"\d{4}-\d+-\d+-\d+-\d+")
# 制度性锚点(2026-09-13 补充): 官方文件与判例的可核锚点常常**不是数字**, 而是
# 「《文件名》/ 判例通报 / 印发施行」这类**可被第三方按名字调阅**的凭据。
# 实测教训: 「湖北省纪委机关、省委组织部…六部门联合通报7起…王某被判有期徒刑一年六个月」
# 与「国务院办公厅2025年1月3日印发《关于严格规范涉企行政检查的意见》」这类一等一的事实性
# 证据, 因数值锚点只有 0-1 个被判成 D·观点(交付物上还带灰色标签), 属系统性误杀。
EXT_DOC_ANCHOR = (r"《[^》]{2,30}(意见|办法|条例|规定|通知|通报|公报|白皮书|方案|细则|决定|"
                  r"答复|报告|宣言|公约|标准|指引|规划|答复)》|"
                  r"(判决|裁定|通报|公告|答复|批复|纪要|白皮书|公报)|印发|施行|生效|废止|"
                  r"联合通报|典型案例|指导案例")
# 可核锚点: 具体数字 + 量词/单位(金额/比例/样本量/数量/年龄/时长/技术参数)
# 允许数字与单位之间夹「多/余/约/近/上/左右」—— 实测「900多万元」「300多天」不加这层就抓不到
EXT_NUM_UNIT = (r"\d[\d,.]*\s*[多余约近上]?\s*(元|万元|亿元|亿美元|万|亿|%|‰|台|份|人|例|户|个|名|条|次|"
                r"天|年|月|日|岁|小时|分钟|分|秒|米|公里|吨|辆|架|枚|颗|起|家|项|款|层|楼|GHz|TOPS|"
                r"MTr|PB/s|万辆|万台|万人次|周岁|页|篇)")
EXT_NUM_MIN = 2                    # 认定为「有可核锚点」的锚点个数下限(数值锚点+制度性锚点)
EXT_ENTITY_MAX = 4                 # entities 每个条目最多保留的主体锚点数
EXT_CORROBORATION_MIN = 2          # 多源印证的「独立来源组」下限
EXT_SHINGLE_FOLD = 0.60            # 同源折叠阈值: 洗稿转载视为同一来源
EXT_LINK_TIMEOUT = 15              # 链接探活超时秒
EXT_LINK_DELAY = 0.4               # 探活间隔秒
EXT_LINK_RETRY = 2                 # 探活尝试次数(5xx/超时/连接错误才重试; 4xx 立即返回)
EXT_LINK_RETRY_BACKOFF = 1.5       # 探活重试退避基数秒(第 n 次等 n*backoff)
# 哪些探活结果才算「来源已失效」。2026-09-13 实测: 探活上百条 url 时平台侧 Cloudflare 会成片返回
# 522(一次跑出 22 条), 而 gen_html 旧逻辑把**一切非 200** 都渲染成「来源已失效」——等于给活链接
# 贴死链标签。4xx(除 429 限流)才是确定性不可达; 5xx/超时/连接错误只能算「未探明」。
EXT_LINK_DEAD = ("400", "401", "402", "404", "405", "406", "410", "451",
                 "HTTP 400", "HTTP 401", "HTTP 402", "HTTP 404", "HTTP 405",
                 "HTTP 406", "HTTP 410", "HTTP 451")
# 来源类别(按域名判定, 零 token): 官方 / 一手媒体 / 站内专栏 / 站内回答 / 其他
EXT_OFFICIAL_HOSTS = ("gov.cn", "stats.gov.cn", "court.gov.cn", "spp.gov.cn", "nhc.gov.cn",
                      "mofcom.gov.cn", "miit.gov.cn", "samr.gov.cn")
EXT_MEDIA_HOSTS = ("xinhuanet.com", "news.cn", "people.com.cn", "cctv.com", "thepaper.cn",
                   "caixin.com", "jiemian.com", "yicai.com", "infzm.com", "bjnews.com.cn",
                   "chinanews.com.cn", "nbd.com.cn", "21jingji.com", "stcn.com")
# 站内域名 → 来源类别(来自平台档案; 换平台改档案)
EXT_HOST_KINDS = pf.get("site_hosts") or ()
# 想法的出处(可选但推荐): 该想法提炼自哪条回答 → 直接把链接与序号附上去
# {"answer_index": 3, "likes": 294, "url": "<该平台的回答链接>"}
EXT_CHAIN_SOURCE = "source"

# ── 发帖短评(2026-09-16 用户要求: 由「≤500 字拟答参考稿」改为 50–100 字犀利短评) ──
# 每个候选 rank 一份短评, 落在 ext_search/<D>/rank_<n>/draft_<n>.md。
# 为什么改短: 发帖物是**一条态度鲜明的短评**, 不是一篇完整回答。字数上限把"讲清机制"压成
# "一句判断 + 一句机制/代价 + 一句落点", 顺带挤掉铺垫、缓冲与和稀泥
# (用户原话: 语言一定要犀利; 字数 50–100 字左右)。
DRAFT_FMT = "draft_%d.md"
DRAFT_LEN = (50, 100)                    # 正文(不含首行标题)字数区间; 越界即打回重写
DRAFT_SHEET = "发帖短评"                  # Excel 累积 sheet(2026-09-16 由「拟答参考」更名)
DRAFT_SHEET_LEGACY = "拟答参考"           # 旧名: fill_excel 遇到即改名, 历史行不分裂成两张表
DRAFT_HEADERS = ("日期", "排名", "问题标题", "拟答标题", "正文", "待发帖")

# ── 书写 skill: 自我学习 loop(2026-09-13 用户要求) ────────────────────────
# 流程: 高赞回答 → subagent 只提取「书写逻辑与语言习惯」(**不涉及具体内容**)
#       → 主 Agent 按奥卡姆剃刀汇编成一份跨日期累积的书写 skill
#       → 书写 subagent 按该 skill 成文 → 批量发布。
# 与话题库同构: 机器可读的候选池 + 人读的汇编稿, 跨日期累积、越用越准。
STYLE_DIR = "书写skill"                   # <ROOT>/书写skill/
STYLE_FILE = "书写skill.md"               # 主 Agent 汇编后的最终稿(唯一人读入口)
STYLE_POOL_FMT = "style_batch_%s.json"    # 各提取 subagent 的产出(批次片段)
STYLE_MERGE = "style_merge.json"          # 汇总候选池(带维度/频次, 供主 Agent 取舍)
# 提取维度(固定值域, 便于汇总与去重): 只看"怎么写", 不看"写了什么"
# 2026-09-16 增「犀利度与锋芒」: 用户要求发帖语言一定要犀利, 且**前期学习就要关注这一点** ——
# 于是把它变成一个独立提取维度(而不是塞进「情绪表达」), 让高赞回答里"怎么把话说狠"的手法
# 被单独学出来、单独进汇编稿。
STYLE_DIMS = ("开头方式", "结构推进", "句长与节奏", "人称与口吻", "情绪表达",
              "论证顺序", "结尾方式", "标点与格式", "词汇习惯", "犀利度与锋芒",
              "避免的写法")

# ── 待发帖列 + 前置判断(2026-09-16 用户要求; 同日**删除自动发帖**) ────────────
# **自动发帖已删除**(用户: "把自动发帖删了, 目前来说收益太少"): 流程不再驱动浏览器点击发布
# (`publish_draft.py` / `publish_batch.py` / `make_manual_publish.py` 三件套已移除),
# 只产出**待发帖列** `待发帖-<D>.md`(逐条可复制), 由人复制粘贴发布, 再回填状态。
#
# 三道闸门(顺序即优先级; 判定权在判定 subagent, 脚本只做兜底复核 —— 与信源门槛同一套纪律):
#   ① 是否时政: 非时政**不进列**(只出稿);
#   ② 时政: swarm 发散是否拿到**评论区(或回答区)没有的增量信息** —— 只是复述已有观点则不进列;
#   ③ 过①②者写 50–100 字短评, 再查**言语中庸** —— 命中即打回重写。
# 上限: 每日最多 PUBLISH_MAX_PER_DAY 条入列, **可以少、不可以多**; 被打回的那条**不递补**。
PUBLISH_MAX_PER_DAY = 3                  # 每日最多入列条数(硬上限)
QUEUE_FILE = "publish_queue.json"        # 待发帖列: "该发哪几条/发到哪一步"的唯一事实源
VERDICT_FILE = "publish_verdicts.json"   # 前置判断结果(判定 subagent 撰写, publish_queue 复核)
VERDICT_PRE_FILE = "publish_verdicts_pre.json"   # 阶段0 预闸门(2026-09-21 起): 只判时政, 检索前跑
VERDICT_PRE_REQUIRED = ("rank", "is_political", "political_basis", "why")
QUEUE_MD_FMT = "待发帖-%s.md"             # 人读清单(在 ROOT 下, 逐条可复制)
GATE_DIRNAME = "gate"                    # ext_search/<D>/gate/ —— 判定提示词与留档
FILE_COMMENTS = "comments.json"          # 评论区基线(可选输入): {"<rank>": [{"text": ...}]}; 缺则降级为回答区
# 状态取值:
#   ready=可发(推荐位) / draft_pending=过闸待写稿 / published=人工已发(回填)
#   verdict_missing=缺前置判断(先跑判定 subagent) / skip_not_political / skip_no_increment=未过闸
#   over_daily_cap=过了闸但超出当日建议位 —— 备选: 稿已写、照常进待发帖列与 HTML,
#                   人工终审可换掉任一推荐条目改发它(2026-09-21 起, 过闸全写+排序推荐)
#   len_out_of_range / mediocre=短评不合格, 打回重写 / sharpness_unjudged=犀利度未复核
QUEUE_STATES = ("ready", "draft_pending", "published", "verdict_missing",
                "skip_not_political", "skip_no_increment", "over_daily_cap",
                "len_out_of_range", "mediocre", "sharpness_unjudged")
# 判定条目字段: 前七个由**阶段一**(时政 + 增量)填; 后两个由**阶段二**(读到短评后)补 ——
# 阶段二覆盖全部已写稿的过闸条目(2026-09-21 起过闸全写, 条数通常 = 过闸数), 由主 Agent 亲自读短评填。
VERDICT_REQUIRED = ("rank", "is_political", "political_basis", "has_increment",
                    "increment_basis", "baseline", "why")
VERDICT_BASELINES = ("comments", "answers")      # 增量比对基线: 评论区 / 回答区
VERDICT_SHARP_FIELDS = ("mediocre", "sharpness_why")
# 时政信号(脚本**初判**, 不硬拦): 类目命中或关键词命中 ≥2 即报信号;
# 判定 subagent 若给出相反结论, publish_queue 会把它列为**分歧项**交主 Agent 复核。
POLITICAL_CATS = ("外交政策与国际关系", "国际冲突与军事", "司法与法治")
POLITICAL_HINTS = (
    "政策", "法规", "条例", "办法", "通知", "通报", "两会", "人大", "政协", "国务院",
    "中央", "部委", "纪委", "监察", "官员", "干部", "政府", "政务", "公权力", "信访",
    "外交", "制裁", "关税", "出口管制", "领事", "大使", "条约", "峰会",
    "军事", "军演", "战争", "停火", "国防", "征兵", "领土", "主权",
    "选举", "总统", "议会", "执政", "立法", "司法", "判决", "起诉", "立案",
    "白宫", "欧盟", "北约", "联合国", "美国", "俄罗斯", "乌克兰", "以色列", "伊朗",
)
# 中庸/和稀泥句式黑名单(**硬闸门**, 正则): 命中即打回重写 ——
# 不采信任何"已经很犀利"的自述(与"不信 subagent 自述"同一条纪律)。
MEDIOCRE_PATTERNS = (
    r"一方面.{0,15}另一方面", r"见仁见智", r"仁者见仁", r"一概而论", r"一分为二",
    r"值得(深思|思考|反思)", r"各有各的(道理|难处|立场)", r"没有绝对", r"因人而异",
    r"辩证(地)?(看|看待)", r"具体情况具体分析", r"既要.{0,12}也要",
    r"理性(看待|对待|讨论)", r"客观(地)?(说|讲|来说)", r"冷静(看待|对待)",
    r"无可厚非", r"换位思考", r"多(一份|点)理解", r"把握好?(度|分寸)",
    r"时间会(证明|给出)", r"交给时间", r"拭目以待", r"不可否认",
    r"(希望|相信)(有关部门|相关方面)", r"不宜(过度|过激)", r"要看到.{0,10}另一面",
)
GATE_REPEAT_JACCARD = 0.30               # 证据与基线文本的 3-gram Jaccard ≥ 此值 ⇒ 疑似复述

# ────────────────────────────── HTML 结构标记 ──────────────────────────────
# 生成方(gen_html)与校验方(verify_html)共用,避免两侧各自硬编码而漂移

HTML_ANSWER_DETAIL_CLASS = "a"         # 回答折叠卡片
HTML_TEXT_DETAIL_CLASS = "a-text"      # 原文折叠
HTML_SUMMARY_TAG = "接口摘要"           # 非全文回答的提示标签
HTML_EXT_MARK = "热点拓展思考"          # 延伸块的标题标记(用于范围校验:仅前 N 名)
HTML_EXT_CLAIM_PREFIX = "想法"          # 链式渲染时的想法前缀

# ────────────────────────────── 路径构造 ──────────────────────────────


def day_dir(root, date):
    """<root>/raw/<date>/"""
    return os.path.join(root, RAW_DIRNAME, date)


def canon_url(u):
    """规范化链接: 去掉查询串与锚点, 去尾部斜杠。

    实测(2026-09-12): 用户贴的问题链接常带跟踪参数(`?share_code=...&utm_psn=...`),
    直接入库会一路带到 answers_summary / Excel / HTML。**入库与去重都用规范化后的链接**。
    (话题库的 norm_url 与本函数同源, 不再各写一份)
    """
    return re.sub(r"[?#].*$", "", (u or "").strip()).rstrip("/")


def path_hot(root, date):
    return os.path.join(day_dir(root, date), FILE_HOT)


def path_answers(root, date):
    return os.path.join(day_dir(root, date), FILE_ANSWERS)


def path_analysis(root, date):
    return os.path.join(day_dir(root, date), FILE_ANALYSIS)


def path_extension(root, date):
    return os.path.join(day_dir(root, date), FILE_EXTENSION)


def path_cookie(root, date):
    return os.path.join(day_dir(root, date), FILE_COOKIE)


def ext_search_dir(root, date):
    """拓展工作目录(各 rank 的链/检索留档/发帖短评都在这里)。"""
    return os.path.join(root, "ext_search", date)


def rank_dir(root, date, rank):
    return os.path.join(ext_search_dir(root, date), "rank_%d" % int(rank))


def path_draft(root, date, rank):
    """发帖短评路径(2026-09-16 起为 50–100 字犀利短评)。文件不存在即视为该 rank 没产出稿子。"""
    return os.path.join(rank_dir(root, date, rank), DRAFT_FMT % int(rank))


def path_queue(root, date):
    """待发帖列(raw/<date>/publish_queue.json): 该发哪几条/发到哪一步的唯一事实源。"""
    return os.path.join(day_dir(root, date), QUEUE_FILE)


def path_verdicts(root, date):
    """前置判断结果(raw/<date>/publish_verdicts.json), 由判定 subagent 撰写。"""
    return os.path.join(day_dir(root, date), VERDICT_FILE)


def path_verdicts_pre(root, date):
    """阶段0 预闸门结果(raw/<date>/publish_verdicts_pre.json): 只判时政, 检索前跑,
    用于把明显非时政的 rank 挡在发散检索之外(宁多搜不误杀: 拿不准一律判是)。"""
    return os.path.join(day_dir(root, date), VERDICT_PRE_FILE)


def path_comments(root, date):
    """评论区基线(可选输入, raw/<date>/comments.json)。"""
    return os.path.join(day_dir(root, date), FILE_COMMENTS)


def queue_md_path(root, date):
    """人读待发帖清单(<ROOT>/待发帖-<date>.md, 逐条可复制)。"""
    return os.path.join(root, QUEUE_MD_FMT % date)


def gate_dir(root, date):
    """前置判断工作目录(ext_search/<date>/gate/: 判定提示词与留档)。"""
    return os.path.join(ext_search_dir(root, date), GATE_DIRNAME)


def path_extra(root, date):
    """单问题追加追踪登记文件(<root>/raw/<date>/extra_questions.json)"""
    return os.path.join(day_dir(root, date), FILE_EXTRA)


def read_hot_items(root, date):
    """容错读取榜单条目: hot.json 缺失/为空都返回 [](2026-09-12 起支持"当天只做单问题追踪")。

    注意: **条目数的唯一来源是 answers_summary.json**(它含追加条目), hot.json 只用于
    标注"哪些是榜单原始条目"与"拓展范围(2026-09-13 起覆盖全部条目, 原为仅前 10)"。
    """
    import io as _io
    import json as _json
    p = path_hot(root, date)
    if not os.path.exists(p):
        return []
    try:
        with _io.open(p, "r", encoding="utf-8-sig") as f:
            node = _json.load(f)
        for k in HOT_ITEMS_PATH:
            node = node[k]
        return node if isinstance(node, list) else []
    except Exception:
        return []


def lib_dir(root):
    return os.path.join(root, LIB_DIRNAME)


def lib_index(root):
    return os.path.join(lib_dir(root), LIB_INDEX)


def lib_md(root):
    return os.path.join(lib_dir(root), LIB_MD)


def month_of(date):
    """'2026-09-12' -> '2026-09'"""
    return "-".join(date.split("-")[:2])


def xlsx_name(date):
    return f"{XLSX_PREFIX}-{month_of(date)}.xlsx"


def xlsx_path(root, date):
    return os.path.join(root, xlsx_name(date))


def xlsx_glob(root):
    """供体检脚本按前缀发现月度表格"""
    return os.path.join(root, f"{XLSX_PREFIX}-*.xlsx")


def report_name(date):
    """交付物基名, 如「<报告前缀>-2026-09-12」(前缀取自平台档案)"""
    return f"{REPORT_TITLE}-{date}"


def report_entry(root, date):
    return os.path.join(root, report_name(date) + ".html")


def report_pages_dir(root, date):
    return os.path.join(root, report_name(date))


def page_name(rank):
    return HTML_PAGE_FMT.format(rank)


def page_path(root, date, rank):
    return os.path.join(report_pages_dir(root, date), page_name(rank))
