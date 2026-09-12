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
    zhihu_env.py         ← 需要访问知乎 CLI / 凭证的脚本(run / question_fetch / fulltext / doctor)
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

# ────────────────────────────── 目录与文件名 ──────────────────────────────

RAW_DIRNAME = "raw"                    # <root>/raw/<date>/
FILE_HOT = "hot.json"                  # 榜单条目(标题/链接/摘要)
FILE_ANSWERS = "answers_summary.json"  # 回答(含正文、赞数、获取状态、覆盖度元数据)
FILE_ANALYSIS = "analysis.json"        # 逐条四维分析(由 Agent 撰写)
FILE_EXTENSION = "extension.json"      # 前 N 名的延伸检索产出(由 Swarm 产出后汇总)
FILE_COOKIE = "cookies.txt"            # 网页登录凭证(供复用)

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
LIB_OPT_FIELDS = ("entities", "adopted", "claim", "relation", "claim_source_url")
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

REPORT_TITLE = "知乎热榜跟进"           # 交付物名称前缀(换主题改这一处)
XLSX_PREFIX = "跟进excel"               # 月度表格名称前缀

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

ANALYSIS_FIELDS = ("stance", "approach", "logic", "emotion", "judge")
ANALYSIS_ESSENCE = "essence"
EMOTIONS = ("积极", "中立", "消极")     # 情绪标签值域(脚本仅做值域校验,不做语义判断)
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
# 想法的出处(可选但推荐): 该想法提炼自哪条回答 → 直接把链接与序号附上去
# {"answer_index": 3, "likes": 294, "url": "https://www.zhihu.com/question/.../answer/..."}
EXT_CHAIN_SOURCE = "source"

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
    """交付物基名:知乎热榜跟进-2026-09-12"""
    return f"{REPORT_TITLE}-{date}"


def report_entry(root, date):
    return os.path.join(root, report_name(date) + ".html")


def report_pages_dir(root, date):
    return os.path.join(root, report_name(date))


def page_name(rank):
    return HTML_PAGE_FMT.format(rank)


def page_path(root, date, rank):
    return os.path.join(report_pages_dir(root, date), page_name(rank))
