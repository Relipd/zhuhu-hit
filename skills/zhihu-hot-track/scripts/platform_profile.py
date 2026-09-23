# -*- coding: utf-8 -*-
"""平台档案(platform profile)—— **换平台的唯一注入点**。

定位
----
本文件属 **L2 平台适配层**(见 ARCHITECTURE.md §二)。它把"平台叫什么、抓哪个站、
CLI 怎么找、交付物怎么命名、页面上写什么来源说明"这些**平台属性**收敛成一份数据:

    L1(方法论/校验/编排)与 L3(交付生成)只通过 `profile()` 取值, 文件里不再出现平台字面量;
    换平台 = 新增/修改本文件里的一个档案 + 实现 L2 采集脚本, **L1/L3 一行不改**。

`check_docs.py` 的第五项检查会**机械校验**这条边界:除本文件与其余 L2 组件外,
任何脚本/模板出现 `知乎` / `zhihu.com` / `ZhihuCLI` 等平台字面量即判 FAIL。

取值优先级
----------
    内置档案(下方 PROFILES) < 环境变量覆盖(TRACK_* 系列)

环境变量(全部可选, 只覆盖不改结构):
    TRACK_PLATFORM         平台代码, 如 zhihu(默认) / bilibili / weibo(未内置则走通用档案)
    TRACK_PLATFORM_NAME    平台显示名(如「知乎」)
    TRACK_UNIT             内容单元名(如「回答」)
    TRACK_PLATFORM_NOTES   写稿时给 LLM 的平台注意事项(一句话)
    TRACK_REPORT_TITLE     交付物名称前缀(如「知乎热榜跟进」)
    TRACK_XLSX_PREFIX      月度表格名称前缀(如「跟进excel」)
    TRACK_API_BASE         网页接口根地址
    TRACK_REFERER          请求头 Referer
    TRACK_SOURCE_BAR       索引页脚注里的数据来源说明
    TRACK_EXCEL_SOURCE     Excel「说明」sheet 的数据来源行
    TRACK_SOURCE_DB        检索库标识(search_many 的 --db 默认值)

通用档案(未内置的平台)
----------------------
传入未内置的 `TRACK_PLATFORM`(如 `bilibili`)时, 会以环境变量给出的信息拼出一份**最小可用档案**:
名称/单元/命名/接口地址来自环境变量, 站点域名与 URL 模板留空。这样"换平台"至少能跑通
L1/L3(校验、Excel、HTML、话题库), 采集与发布由新平台的 L2 脚本补齐。
"""

from __future__ import annotations

import os

# ────────────────────────────── 内置档案 ──────────────────────────────

PROFILES = {
    "zhihu": {
        "code": "zhihu",
        "name": "知乎",
        "unit": "回答",
        "article_unit": "文章",
        # 写稿子任务要读的平台注意事项(原 gen_prompts.PLATFORM_NOTES, 逐字保留; 2026-09-16 随 sheet 更名修订)
        "notes": "知乎「回答」没有标题字段（只有「文章」有），所以稿子只发正文、不发标题；"
                 "标题仅用于我们自己的交付物（Excel「发帖短评」sheet 与 HTML 页内块）。",
        # 交付物命名(L3 消费; 换平台改这一处)
        "report_title": "知乎热榜跟进",
        "xlsx_prefix": "跟进excel",
        # 交付物上的来源说明(必须与历史产物逐字一致, 否则回归比对会失败)
        "source_bar": "数据来源：知乎开放平台热榜 · 每问题数据 =「问题维度网页接口(按赞取前 N)」"
                      "∪「关键词搜索召回」并集 · 点击卡片进入详情页 · 全部条目含热点拓展",
        "excel_source": "zhihu-cli: hot + search zhihu 多变体查询合并。详见 skill 文档。",
        # 域名 → 来源类别(信源门槛/探活报告用)
        "site_hosts": (("zhuanlan.zhihu.com", "站内专栏"),
                       ("www.zhihu.com", "站内回答"),
                       ("zhihu.com", "站内回答")),
        # 采集接口(L2 采集脚本消费)
        "api_base": "https://www.zhihu.com/api/v4",
        "referer": "https://www.zhihu.com/",
        "url_question": "https://www.zhihu.com/question/{qid}",
        "url_answer": "https://www.zhihu.com/question/{qid}/answer/{aid}",
        "url_answer_bare": "https://www.zhihu.com/answer/{aid}",
        "url_article": "https://zhuanlan.zhihu.com/p/{pid}",
        "source_db": "zhihu",          # search_many --db 默认库
        # 基础技术栈(zhihu_env 消费)
        "cli_name": "zhihu-cli",
        "cli_env": "ZHIHU_CLI",
        "cli_home_env": "ZHIHU_CLI_HOME",
        "cli_home_defaults": {
            "nt": ("LOCALAPPDATA", "ZhihuCLI"),
            "darwin": ("~", "Library/Application Support/zhihu-cli"),
            "linux": ("~", ".local/share/zhihu-cli"),
        },
        "keychain_services": ("zhihu-cli:access-secret", "zhihu-cli"),
        "basestack_skill": "zhihu",
        "basestack_env": "ZHIHU_SKILL_DIR",
        # 发布(浏览器自动化)相关文案
        "publish_no_title": "知乎「回答」没有标题字段(只有「文章」有): 稿子的 `# 标题` 不发, 只发正文。",
        "publish_entry": "知乎发帖",
        "publish_editor_entry": "写回答",
        "follow_note": "浏览器自动化发布回答后, 平台会自动关注该问题",
        "discover_env": "ZHIHU_TRACK_ROOTS",   # 限定 ROOT 自动发现范围(通用名 TRACK_ROOTS 亦可)
    },
}

# 环境变量覆盖表: 档案字段 ← 环境变量名
_ENV_MAP = {
    "name": "TRACK_PLATFORM_NAME",
    "unit": "TRACK_UNIT",
    "notes": "TRACK_PLATFORM_NOTES",
    "report_title": "TRACK_REPORT_TITLE",
    "xlsx_prefix": "TRACK_XLSX_PREFIX",
    "api_base": "TRACK_API_BASE",
    "referer": "TRACK_REFERER",
    "source_bar": "TRACK_SOURCE_BAR",
    "excel_source": "TRACK_EXCEL_SOURCE",
    "source_db": "TRACK_SOURCE_DB",
    "publish_no_title": "TRACK_PUBLISH_NO_TITLE",
}

DEFAULT_CODE = "zhihu"

# ──────────────────── L2 组件名单(供 check_docs 机械守卫使用) ────────────────────
# 列在这里的组件"允许出现平台字面量";其余脚本/模板一旦出现平台字面量即判 FAIL。
# 名单与 ARCHITECTURE.md §二 的 L2 表一致; 改动这里必须同步文档(反之亦然, check_docs 会比对)。
L2_COMPONENTS = (
    "platform_profile.py",     # 本文件:平台档案(唯一允许写死平台属性的地方)
    "zhihu_env.py",            # CLI 定位与凭证探测
    "run.py",                  # 榜单 + 关键词搜索变体
    "question_fetch.py",       # 条目维度接口(按赞取前 N、并集、覆盖率)
    "fulltext.py",             # 正文补全接口
    "search_many.py",          # 发散检索后端
    "question_add.py",         # 链接形态解析
    "unfollow_question.py",    # 关注按钮 DOM(人工发布后的可选清尾)
    "extract_cookie.py",       # storageState → cookies.txt(cookie 失效自愈, 坑 77)
)

# 平台相关环境变量的名字也在档案里(换平台时可改, 或直接用 TRACK_ROOTS 通用名)。
ROOTS_ENV_FALLBACK = "TRACK_ROOTS"    # 通用名: 限定 doctor --discover 的搜索范围

# 机械守卫用的"平台字面量"模式(L1/L3 文件中出现即 FAIL)。
# 允许标识符 `zhihu_env`(模块名引用), 但禁止独立的平台名 / 域名 / CLI 名。
PLATFORM_LITERAL_PATTERN = r"知乎|zhihu\.com|ZhihuCLI|zhihu-cli|(?i:zhihu)(?!_env)"


def code() -> str:
    """当前平台代码(默认 zhihu)。"""
    return (os.environ.get("TRACK_PLATFORM") or DEFAULT_CODE).strip().lower()


def _generic(name: str) -> dict:
    """未内置平台的最小档案: 名称/单元/命名可来自环境变量, 域名与接口留空。"""
    return {
        "code": name,
        "name": name,
        "unit": "条目",
        "article_unit": "文章",
        "notes": "",
        "report_title": f"{name}热榜跟进",
        "xlsx_prefix": "跟进excel",
        "source_bar": f"数据来源：{name} · 每问题数据 =「平台接口(按赞取前 N)」∪「关键词搜索召回」并集",
        "excel_source": f"{name}: hot + search 多变体查询合并。详见 skill 文档。",
        "site_hosts": (),
        "api_base": "",
        "referer": "",
        "url_question": "",
        "url_answer": "",
        "url_answer_bare": "",
        "url_article": "",
        "source_db": name,
        "cli_name": f"{name}-cli",
        "cli_env": f"{name.upper()}_CLI",
        "cli_home_env": f"{name.upper()}_CLI_HOME",
        "cli_home_defaults": {"nt": ("LOCALAPPDATA", f"{name.title()}CLI"),
                              "darwin": ("~", f".{name}"),
                              "linux": ("~", f".{name}")},
        "keychain_services": (f"{name}-cli:access-secret", f"{name}-cli"),
        "basestack_skill": name,
        "basestack_env": f"{name.upper()}_SKILL_DIR",
        "publish_no_title": f"{name}「{os.environ.get('TRACK_UNIT', '条目')}」按平台规则发布: 标题仅用于交付物。",
        "publish_entry": f"{name}发帖",
        "publish_editor_entry": "写内容",
        "follow_note": f"浏览器自动化发布后, {name} 可能自动产生副作用(如关注该问题)",
        "discover_env": f"{name.upper()}_TRACK_ROOTS",
    }


def profile(platform_code: str | None = None) -> dict:
    """取当前平台档案(内置优先, 未知平台走通用档案), 再套用 TRACK_* 环境变量覆盖。"""
    c = (platform_code or code()).strip().lower()
    data = dict(PROFILES.get(c) or _generic(c))
    data["code"] = c
    for field, env in _ENV_MAP.items():
        val = os.environ.get(env)
        if val:
            data[field] = val
    return data


def get(field: str, default=None):
    """便捷取值(档案缺该字段时返回 default)。"""
    return profile().get(field, default)


def summary() -> str:
    """一行摘要, 供 doctor / 日志打印, 让"当前跑的是哪个平台"可见。"""
    p = profile()
    builtin = "内置" if p["code"] in PROFILES else "通用(未内置)"
    return f"{p['name']}({p['code']}, {builtin}) · 单元={p['unit']} · 交付物={p['report_title']}-<date>"
