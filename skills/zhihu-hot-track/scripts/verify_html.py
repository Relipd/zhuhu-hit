# -*- coding: utf-8 -*-
"""知乎热榜跟进 - HTML 交付物结构校验(约束四自动校验)。

gen_html.py 只负责生成, 不校验; 历史上靠 Agent 临时手写 PowerShell 逐项核对,
既慢又易错(实测因 PS 语法错误重跑)。本脚本把约束四的校验固化成一条命令。

用法: python verify_html.py --root <ROOT> --date 2026-09-11

校验项(逐条 PASS/FAIL):
  1. 根入口 <root>/知乎热榜跟进-<D>.html 存在, 且 meta refresh 指向 <目录>/index.html
  2. 目录 <root>/知乎热榜跟进-<D>/ 与 index.html 存在
  3. 详情页数 == 热榜条数(q01..qNN 连续无缺号)
  4. 每页回答折叠数 == 该问题回答数(每条回答固定 2 个 <details>: 卡片 + 原文)
  5. 翻页链接衔接: qNN 的「上一题」=q(N-1)、「下一题」=q(N+1), 首末页为 class="off" href="#"
  6. 索引页卡片数 == 热榜条数
  7. 「接口摘要」标签数 == content_status != full 的回答数(带 Cookie 全量补全时应为 0)
  8. 前 10 有「热点拓展思考」块, 第 11 名之后无(范围硬约束)
"""
import argparse, io, json, os, re, sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RE_DETAIL_ANSWER = re.compile(r'<details class="a">')
RE_PREV = re.compile(r'<a class="(?:off)?" href="([^"]*)">← 上一题</a>')
RE_NEXT = re.compile(r'<a class="(?:off)?" href="([^"]*)">下一题 →</a>')
RE_SUMMARY_TAG = re.compile(r"接口摘要")
RE_INDEX_CARD = re.compile(r'q(\d{2})\.html')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    root, d = args.root, args.date
    entry = os.path.join(root, f"知乎热榜跟进-{d}.html")
    pages_dir = os.path.join(root, f"知乎热榜跟进-{d}")
    idx = os.path.join(pages_dir, "index.html")
    hot_path = os.path.join(root, "raw", d, "hot.json")
    sum_path = os.path.join(root, "raw", d, "answers_summary.json")

    results = []

    def check(name, ok, detail=""):
        results.append((ok, name, detail))

    # 前置数据
    hot = json.load(io.open(hot_path, encoding="utf-8-sig"))
    summary = json.load(io.open(sum_path, encoding="utf-8"))
    total = len(hot["Data"]["Items"])
    answers_of = {int(s["rank"]): len(s["answers"]) for s in summary}
    not_full = sum(1 for s in summary for a in s["answers"] if a.get("content_status") != "full")

    # 1. 入口
    if not os.path.exists(entry):
        check("根入口存在", False, entry)
        entry_html = ""
    else:
        entry_html = io.open(entry, encoding="utf-8").read()
        m = re.search(r'http-equiv="refresh"[^>]*url=([^"\'>]+)', entry_html, re.I)
        target = (m.group(1).strip() if m else "")
        want = f"知乎热榜跟进-{d}/index.html"
        check("根入口跳转路径", target.endswith(want), f"实际={target!r} 期望以 {want!r} 结尾")

    # 2. 目录与索引
    check("展示目录存在", os.path.isdir(pages_dir), pages_dir)
    check("index.html 存在", os.path.exists(idx), idx)

    # 3. 详情页数与连续性
    pages = sorted(f for f in os.listdir(pages_dir) if re.fullmatch(r"q\d+\.html", f)) if os.path.isdir(pages_dir) else []
    check("详情页数 == 热榜条数", len(pages) == total, f"{len(pages)} vs {total}")
    want_names = [f"q{i:02d}.html" for i in range(1, total + 1)]
    missing = [n for n in want_names if n not in pages]
    check("详情页无缺号", not missing, f"缺失: {missing}")

    # 4~5. 逐页折叠数与翻页
    bad_details, bad_paging, detail_err = [], [], []
    for i in range(1, total + 1):
        p = os.path.join(pages_dir, f"q{i:02d}.html")
        if not os.path.exists(p):
            continue
        html = io.open(p, encoding="utf-8").read()
        n_details = len(RE_DETAIL_ANSWER.findall(html))
        want_details = answers_of.get(i, 0)
        if n_details != want_details:
            bad_details.append(f"q{i:02d}:{n_details}/{want_details}")
        mp, mn = RE_PREV.search(html), RE_NEXT.search(html)
        prev_href = mp.group(1) if mp else "<无链接>"
        next_href = mn.group(1) if mn else "<无链接>"
        want_prev = f"q{i-1:02d}.html" if i > 1 else "#"
        want_next = f"q{i+1:02d}.html" if i < total else "#"
        if prev_href != want_prev:
            bad_paging.append(f"q{i:02d} 上一题={prev_href} 应为 {want_prev}")
        if next_href != want_next:
            bad_paging.append(f"q{i:02d} 下一题={next_href} 应为 {want_next}")
        if not mp or not mn:
            detail_err.append(f"q{i:02d} 缺翻页链接")

    check("每页折叠数 == 回答数", not bad_details, "; ".join(bad_details[:8]))
    check("翻页链接前后衔接", not bad_paging, "; ".join(bad_paging[:8]) + "".join(detail_err[:3]))

    # 6. 索引卡片数
    if os.path.exists(idx):
        card_ids = {int(x) for x in RE_INDEX_CARD.findall(io.open(idx, encoding="utf-8").read())}
        check("索引卡片数 == 热榜条数", len(card_ids) == total, f"{len(card_ids)} vs {total}")

    # 7. 接口摘要标签
    n_tag = 0
    for i in range(1, total + 1):
        p = os.path.join(pages_dir, f"q{i:02d}.html")
        if os.path.exists(p):
            n_tag += len(RE_SUMMARY_TAG.findall(io.open(p, encoding="utf-8").read()))
    check("接口摘要标签数 == 非 full 回答数", n_tag == not_full,
          f"{n_tag} vs {not_full}(带 Cookie 全量补全时应为 0/0)")

    # 8. 拓展范围: 前 10 有、11+ 无
    # 注: 页脚含「热点拓展仅覆盖热榜前 10」说明文字, 故用「热点拓展思考」标题判定而非「热点拓展」
    scope_bad = []
    for i in range(1, total + 1):
        p = os.path.join(pages_dir, f"q{i:02d}.html")
        if not os.path.exists(p):
            continue
        html = io.open(p, encoding="utf-8").read()
        has_block = "热点拓展思考" in html
        if i <= 10 and not has_block:
            scope_bad.append(f"q{i:02d} 缺拓展块")
        if i > 10 and has_block:
            scope_bad.append(f"q{i:02d} 不应有拓展块")
    check("拓展块仅覆盖前 10", not scope_bad, "; ".join(scope_bad[:8]))

    # 输出
    fails = [r for r in results if not r[0]]
    for ok, name, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    print(f"HTML 校验: {len(results) - len(fails)}/{len(results)} 通过 (热榜 {total} 条, 非 full 回答 {not_full} 条)")
    if fails:
        sys.exit(1)
    print("[OK] 约束四校验全部通过")


if __name__ == "__main__":
    main()
