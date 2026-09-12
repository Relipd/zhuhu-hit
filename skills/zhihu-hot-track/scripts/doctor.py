# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 环境与数据自检(基础技术栈适配的诊断入口)。

为什么需要它
------------
本流程依赖三类外部状态: 基础技术栈(zhihu skill 的 CLI 与凭证)、本机运行时
(Python/openpyxl/playwright-cli)、以及工作目录 ROOT 的历史数据。这三者任一变化
都会让流程以晦涩的方式失败——实测过的场景包括: CLI 二进制被清理而凭证仍在、
会话跨天后 ROOT 与"今天"都已改变、cookie 过期、Excel 依赖缺失。doctor 用一条命令
把全部前置条件摊开, 并给出修复动作。

用法:
  python doctor.py                        # 只体检环境(不依赖 ROOT)
  python doctor.py --discover             # 自动发现候选 ROOT(替代人肉扫盘)
  python doctor.py --root <ROOT> [--date YYYY-MM-DD]   # 连带检查工作目录与当日数据
  python doctor.py --root <ROOT> --date <D> --json     # 机读输出

退出码: 0=无 FAIL(可有 WARN); 1=存在 FAIL。
"""
import argparse
import glob
import io
import json
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract   # noqa: E402  数据契约:文件名 / 字段 / 值域的单一定义处
import zhihu_env  # noqa: E402

REQUIRED_SCRIPTS = ["contract.py", "run.py", "question_fetch.py", "fulltext.py", "search_many.py",
                    "check.py", "merge_extension.py", "verify_html.py", "fill_excel.py",
                    "gen_html.py", "topic_lib.py", "zhihu_env.py"]
SKIP_DIRS = {"windows", "$recycle.bin", "system volume information", "node_modules",
             "appdata", "temp", "tmp", ".git", ".cache", "__pycache__",
             "program files", "program files (x86)", "programdata", "perflogs"}


def discover_roots(depth=2, extra_bases=None):
    """在常见位置寻找候选工作根目录(含 话题库/index.json 或 跟进excel-*.xlsx)。"""

    bases = []
    env = os.environ.get("ZHIHU_TRACK_ROOTS")
    if env:
        bases += [p for p in re.split(r"[;]", env) if p.strip()]
    if extra_bases:
        bases += list(extra_bases)
    home = os.path.expanduser("~")
    bases.append(home)
    for drive in ("D:\\", "C:\\", "E:\\"):
        if os.path.isdir(drive):
            bases.append(drive)
    bases.append(os.getcwd())

    found = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        base = os.path.abspath(base)
        for root, dirs, files in os.walk(base):
            rel = os.path.relpath(root, base)
            level = 0 if rel == "." else rel.count(os.sep) + 1
            if level >= depth:
                dirs[:] = []
            else:
                dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            is_root = (os.path.exists(contract.lib_index(root))
                       or any(f.startswith(contract.XLSX_PREFIX + "-") and f.endswith(".xlsx")
                              for f in files))
            if is_root:
                found.append(root)
                dirs[:] = []
    return sorted(set(found))


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, name, detail=""):
        self.items.append({"level": level, "name": name, "detail": detail})

    def ok(self, name, detail=""):
        self.add("OK", name, detail)

    def warn(self, name, detail=""):
        self.add("WARN", name, detail)

    def fail(self, name, detail=""):
        self.add("FAIL", name, detail)

    @property
    def failed(self):
        return [i for i in self.items if i["level"] == "FAIL"]

    def print_human(self):
        icon = {"OK": "PASS", "WARN": "WARN", "FAIL": "FAIL"}
        for i in self.items:
            line = f"  [{icon[i['level']]}] {i['name']}"
            if i["detail"]:
                line += f" — {i['detail']}"
            print(line)
        n_fail, n_warn = len(self.failed), len([i for i in self.items if i["level"] == "WARN"])
        print(f"\n体检结果: {len(self.items)} 项, FAIL {n_fail}, WARN {n_warn}")


def check_runtime(rep):
    rep.ok("Python 解释器", f"{sys.executable} ({sys.version.split()[0]})")
    if sys.version_info < (3, 8):
        rep.fail("Python 版本", "需要 3.8+")
    try:
        import openpyxl  # noqa: F401
        rep.ok("openpyxl", "可用(fill_excel.py 依赖)")
    except Exception:
        rep.warn("openpyxl", "缺失 -> fill_excel.py 将失败; 用含 openpyxl 的解释器")
    try:
        import urllib.request  # noqa: F401
        rep.ok("urllib", "可用(fulltext.py 依赖)")
    except Exception:
        rep.fail("urllib", "标准库缺失, 异常环境")


def check_basestack(rep):
    """基础技术栈: zhihu skill(CLI 安装/鉴权/入口)。"""
    cli = zhihu_env.resolve_cli()
    src = zhihu_env.cli_source(cli)
    if cli:
        rep.ok("zhihu-cli 可执行文件", f"{cli} (来源: {src})")
        v = zhihu_env.cli_version(cli)
        rep.ok("zhihu-cli 版本", v or "读取失败(不影响调用)")
    else:
        rep.fail("zhihu-cli 可执行文件", "未找到 -> " + zhihu_env.run_skill_setup_hint())

    kc = zhihu_env.keychain_present()
    if kc is True:
        rep.ok("Access Secret(系统凭证库)", "已存在, 安装/修复 CLI 后可直接复用")
    elif kc is False:
        rep.warn("Access Secret(系统凭证库)", "未发现 -> 安装后需按 zhihu skill 生成并注入")
    else:
        rep.warn("Access Secret(系统凭证库)", "无法探测(非 Windows/macOS 或工具不可用)")

    st = zhihu_env.skill_status()
    if st is None:
        rep.warn("zhihu skill 入口", f"run.ps1|run.sh status 不可用(dir={zhihu_env.skill_dir()})")
    else:
        rep.ok("zhihu skill 入口", "status 可解析")
        if st.get("installed") is False:
            rep.warn("zhihu skill 判定", f"installed=false, next_action={st.get('next_action')}")
        upd = (st.get("skill") or {}).get("update_available")
        if upd:
            rep.warn("zhihu skill 版本", "有可升级版本 -> 升级会覆盖本地对基础栈的改动, 见 SKILL.md 适配说明")

    pd = os.environ.get("PLAYWRIGHT_CLI_DIR", r"D:\claude code\playwright-cli")
    rep.ok("playwright-cli", pd if os.path.exists(os.path.join(pd, "playwright-cli.js"))
           else f"未在 {pd} 找到 -> Cookie 获取将退化到方式 B(F12 手抄)")


def check_scripts(rep):
    here = os.path.dirname(os.path.abspath(__file__))
    missing = [s for s in REQUIRED_SCRIPTS if not os.path.exists(os.path.join(here, s))]
    if missing:
        rep.fail("skill 脚本完整性", "缺失: " + ", ".join(missing))
    else:
        rep.ok("skill 脚本完整性", f"{len(REQUIRED_SCRIPTS)} 个脚本齐备")

    # 契约层自检:路径构造必须与常量自洽(改常量时若忘了改函数, 这里先炸)
    probe = contract.day_dir("X", "2026-09-12")
    want = os.path.join("X", contract.RAW_DIRNAME, "2026-09-12")
    pairs = [
        (contract.path_hot("X", "2026-09-12"), os.path.join(probe, contract.FILE_HOT)),
        (contract.path_answers("X", "2026-09-12"), os.path.join(probe, contract.FILE_ANSWERS)),
        (contract.path_analysis("X", "2026-09-12"), os.path.join(probe, contract.FILE_ANALYSIS)),
        (contract.path_extension("X", "2026-09-12"), os.path.join(probe, contract.FILE_EXTENSION)),
        (contract.path_cookie("X", "2026-09-12"), os.path.join(probe, contract.FILE_COOKIE)),
        (contract.report_entry("X", "2026-09-12"),
         os.path.join("X", contract.REPORT_TITLE + "-2026-09-12.html")),
        (contract.page_path("X", "2026-09-12", 3),
         os.path.join("X", contract.REPORT_TITLE + "-2026-09-12", contract.page_name(3))),
        (probe, want),
    ]
    bad = [f"{a!r} != {b!r}" for a, b in pairs if a != b]
    if bad:
        rep.fail("契约层自检", "; ".join(bad[:3]))
    else:
        rep.ok("契约层自检", f"路径构造自洽(情绪值域 {len(contract.EMOTIONS)} 值 / 分析字段 {len(contract.ANALYSIS_FIELDS)} 项 / 拓展类型 {len(contract.EXT_TYPES)} 类)")


def check_root(rep, root, date=None):
    if not os.path.isdir(root):
        rep.fail("ROOT 存在性", root)
        return
    rep.ok("ROOT", root)
    lib = contract.lib_index(root)
    if os.path.exists(lib):
        try:
            n = len(json.load(io.open(lib, encoding="utf-8")).get("items", []))
            rep.ok("话题库", f"{n} 条")
        except Exception as e:
            rep.fail("话题库 index.json", f"解析失败: {e}")
    else:
        rep.warn("话题库", "尚未建立(首次运行会自动创建)")

    xl = sorted(glob.glob(contract.xlsx_glob(root)))
    rep.ok("月度 Excel", ", ".join(os.path.basename(p) for p in xl) if xl else "尚无(首次填表会新建)")

    if not date:
        return
    tag = f"{contract.RAW_DIRNAME}/{date}"
    day = contract.day_dir(root, date)
    if not os.path.isdir(day):
        rep.warn(tag, "不存在(该日期尚未抓取)")
        return
    # 期望的当日产物(顺序即检查顺序, 名字与字段全部来自契约)
    expect = (contract.FILE_HOT, contract.FILE_ANSWERS, contract.FILE_ANALYSIS, contract.FILE_EXTENSION)
    for name in expect:
        p = os.path.join(day, name)
        if not os.path.exists(p):
            rep.warn(f"{tag}/{name}", "缺失")
            continue
        try:
            d = json.load(io.open(p, encoding="utf-8-sig"))
            if name == contract.FILE_HOT:
                node = d
                for key in contract.HOT_ITEMS_PATH:
                    node = node[key]
                detail = f"{len(node)} 条热榜"
            elif name == contract.FILE_ANSWERS:
                detail = f"{len(d)} 问题 / {sum(len(s['answers']) for s in d)} 回答"
            elif name == contract.FILE_ANALYSIS:
                detail = f"{len(d)} 问题已分析"
            else:
                detail = f"{len(d)} rank / {sum(len(v['items']) for v in d.values())} 发散点"
            rep.ok(f"{tag}/{name}", detail)
        except Exception as e:
            rep.fail(f"{tag}/{name}", f"解析失败: {e}")

    ck = contract.path_cookie(root, date)
    if os.path.exists(ck):
        rep.ok(f"{tag}/{contract.FILE_COOKIE}", "存在 -> 直接复用(不验证、不删除; 仅失败时刷新)")
    else:
        rep.warn(f"{tag}/{contract.FILE_COOKIE}",
                 "不存在 -> 先按无 Cookie 运行; 若 truncated+summary 占比 >20% 再按 Step 1.2 获取")


def main():
    ap = argparse.ArgumentParser(description="环境与数据自检(基础技术栈适配诊断)")
    ap.add_argument("--root", default=None)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD")
    ap.add_argument("--discover", action="store_true", help="只自动发现候选 ROOT")
    ap.add_argument("--json", action="store_true", help="机读输出")
    args = ap.parse_args()

    if args.discover:
        roots = discover_roots()
        if args.json:
            print(json.dumps({"candidates": roots}, ensure_ascii=False, indent=1))
        else:
            print("候选工作根目录(含 话题库/index.json 或 跟进excel-*.xlsx):")
            for r in roots:
                print("  -", r)
            if not roots:
                print("  (未发现; 用 --root 显式指定, 或设环境变量 ZHIHU_TRACK_ROOTS 限定搜索范围)")
        return 0

    rep = Report()
    check_runtime(rep)
    check_scripts(rep)
    check_basestack(rep)
    if args.root:
        check_root(rep, args.root, args.date)
    else:
        cands = discover_roots()
        if cands:
            rep.ok("ROOT 自动发现", "; ".join(cands) + " (用 --root 指定其一以继续深度检查)")
        else:
            rep.warn("ROOT 自动发现", "未发现候选, 用 --root 显式指定")

    if args.json:
        print(json.dumps({"items": rep.items, "failed": len(rep.failed),
                          "diagnose": zhihu_env.diagnose()}, ensure_ascii=False, indent=1))
    else:
        rep.print_human()
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
