# -*- coding: utf-8 -*-
"""热榜跟进 - HTML 交付物结构校验(约束四自动校验)。

gen_html.py 只负责生成, 不校验; 历史上靠 Agent 临时手写 PowerShell 逐项核对,
既慢又易错(实测因 PS 语法错误重跑)。本脚本把约束四的校验固化成一条命令。

用法: python verify_html.py --root <ROOT> --date 2026-09-11

校验项(逐条 PASS/FAIL):
  1. 根入口 <root>/<报告前缀>-<D>.html 存在, 且 meta refresh 指向 <目录>/index.html
  2. 目录 <root>/<报告前缀>-<D>/ 与 index.html 存在
  3. 详情页数 == 热榜条数(q01..qNN 连续无缺号)
  4. 每页回答折叠数 == 该问题回答数(每条回答固定 2 个 <details>: 卡片 + 原文)
  5. 翻页链接衔接: qNN 的「上一题」=q(N-1)、「下一题」=q(N+1), 首末页为 class="off" href="#"
  6. 索引页卡片数 == 热榜条数
  7. 「接口摘要」标签数 == content_status != full 的回答数(带 Cookie 全量补全时应为 0)
  8. 拓展块覆盖 == extension.json 的 rank 集合(2026-09-13 起扩展范围=全部条目, 不再是前 10)
"""
import argparse, io, json, os, re, sys

import contract   # 数据契约:文件名 / 字段 / 值域的单一定义处(见 contract.py)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RE_DETAIL_ANSWER = re.compile(r'<details class="%s">' % re.escape(contract.HTML_ANSWER_DETAIL_CLASS))
RE_PREV = re.compile(r'<a class="(?:off)?" href="([^"]*)">← 上一题</a>')
RE_NEXT = re.compile(r'<a class="(?:off)?" href="([^"]*)">下一题 →</a>')
RE_SUMMARY_TAG = re.compile(re.escape(contract.HTML_SUMMARY_TAG))
RE_INDEX_CARD = re.compile(r'q(\d{2})\.html')
# 多元化情绪标记(契约里定义了标签/tone, 这里只需按类名计数)
RE_EMO_TAG = re.compile(r'class="emo t-')
RE_EMO_INT = re.compile(r'class="emo-up"')
RE_EMO_TGT = re.compile(r'class="emo-tgt"')
RE_LEGACY_JUDGE = re.compile(r'class="judge ')
RE_DRAFT = re.compile(r'class="draft"')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    root, d = args.root, args.date
    entry = contract.report_entry(root, d)
    pages_dir = contract.report_pages_dir(root, d)
    idx = os.path.join(pages_dir, contract.HTML_INDEX_NAME)
    hot_path = contract.path_hot(root, d)
    sum_path = contract.path_answers(root, d)

    results = []

    def check(name, ok, detail=""):
        results.append((ok, name, detail))

    # 前置数据。**条目数基准 = answers_summary**(含单问题追加条目), hot.json 只用于标注;
    # 2026-09-12 起支持"当天只做单问题追踪"(无 hot.json)与"追加 rank 21+", 故 hot 必须容错读。
    summary = json.load(io.open(sum_path, encoding="utf-8"))
    total = len(summary)
    hot_items = contract.read_hot_items(root, d)
    hot_urls = {str(it.get("Url") or "") for it in hot_items}
    extra_ranks = {int(s["rank"]) for s in summary if s.get("extra")
                   or (hot_urls and str(s.get("url") or "") not in hot_urls)}
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
        want = f"{contract.report_name(d)}/{contract.HTML_INDEX_NAME}"
        check("根入口跳转路径", target.endswith(want), f"实际={target!r} 期望以 {want!r} 结尾")

    # 2. 目录与索引
    check("展示目录存在", os.path.isdir(pages_dir), pages_dir)
    check("index.html 存在", os.path.exists(idx), idx)

    # 3. 详情页数与连续性
    pages = sorted(f for f in os.listdir(pages_dir) if re.fullmatch(r"q\d+\.html", f)) if os.path.isdir(pages_dir) else []
    check("详情页数 == 条目数", len(pages) == total, f"{len(pages)} vs {total}")
    want_names = [contract.page_name(i) for i in range(1, total + 1)]
    missing = [n for n in want_names if n not in pages]
    check("详情页无缺号", not missing, f"缺失: {missing}")

    # 4~5. 逐页折叠数与翻页
    bad_details, bad_paging, detail_err = [], [], []
    for i in range(1, total + 1):
        p = contract.page_path(root, d, i)
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
        want_prev = contract.page_name(i - 1) if i > 1 else "#"
        want_next = contract.page_name(i + 1) if i < total else "#"
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
        check("索引卡片数 == 条目数", len(card_ids) == total, f"{len(card_ids)} vs {total}")

    # 7. 接口摘要标签
    n_tag = 0
    for i in range(1, total + 1):
        p = contract.page_path(root, d, i)
        if os.path.exists(p):
            n_tag += len(RE_SUMMARY_TAG.findall(io.open(p, encoding="utf-8").read()))
    check("接口摘要标签数 == 非 full 回答数", n_tag == not_full,
          f"{n_tag} vs {not_full}(带 Cookie 全量补全时应为 0/0)")

    # 7b. 情绪渲染齐全(2026-09-13 新增): 多元化情绪 = 多标签 chips + 强度点 + 指向签。
    # 与 analysis.json 逐项对账, 防止"数据改了但页面没跟上"(反之亦然); 同时挡住新旧模型串用:
    # 新模型页面上不应再出现旧三元徽章 class="judge", 历史日期则相反。
    an = json.load(io.open(contract.path_analysis(root, d), encoding="utf-8"))
    exp_tags = exp_int = exp_tgt = exp_legacy = 0
    for s in summary:
        for a in an[str(s["rank"])]["answers"]:
            if a.get("emotion_tags") is not None:
                exp_tags += len(a.get("emotion_tags") or [])
                exp_int += 1 if a.get("emotion_intensity") else 0
                exp_tgt += 1 if a.get("emotion_target") else 0
            elif a.get("judge"):
                exp_legacy += 1
    got_tags = got_int = got_tgt = got_legacy = 0
    for i in range(1, total + 1):
        p = contract.page_path(root, d, i)
        if not os.path.exists(p):
            continue
        h = io.open(p, encoding="utf-8").read()
        got_tags += len(RE_EMO_TAG.findall(h))
        got_int += len(RE_EMO_INT.findall(h))
        got_tgt += len(RE_EMO_TGT.findall(h))
        got_legacy += len(RE_LEGACY_JUDGE.findall(h))
    if exp_tags or exp_tgt:
        check("情绪标签/强度/指向 渲染齐全",
              (got_tags, got_int, got_tgt) == (exp_tags, exp_int, exp_tgt),
              f"页面(标签{got_tags}/强度{got_int}/指向{got_tgt}) "
              f"vs 分析(标签{exp_tags}/强度{exp_int}/指向{exp_tgt})")
        check("情绪模型未串用", got_legacy == exp_legacy,
              f"旧三元徽章 页面{got_legacy} vs 分析{exp_legacy}")

    # 7c. 发帖短评渲染对账(2026-09-13 新增; 2026-09-16 起为 50–100 字犀利短评):
    #     有 draft_<n>.md 的 rank 必须在详情页出现短评块,
    # 没有稿子的 rank 不许凭空出现该块。历史日期没有稿子 ⇒ 本项自动跳过。
    draft_bad, n_draft = [], 0
    for i in range(1, total + 1):
        dp = contract.path_draft(root, d, i)
        has_file = os.path.exists(dp) and os.path.getsize(dp) > 0
        page = contract.page_path(root, d, i)
        if not os.path.exists(page):
            continue
        has_block = bool(RE_DRAFT.search(io.open(page, encoding="utf-8").read()))
        if has_file:
            n_draft += 1
        if has_file and not has_block:
            draft_bad.append(f"q{i:02d} 有稿未渲染")
        if has_block and not has_file:
            draft_bad.append(f"q{i:02d} 无稿却渲染了拟答块")
    if n_draft or draft_bad:
        check("发帖短评渲染对账", not draft_bad, "; ".join(draft_bad[:8]))

    # 8. 拓展范围(2026-09-13 起为**全部条目**): 有多少 rank 产出过 extension.json, 就该有多少页有拓展块。
    # 注: 页脚含「热点拓展」说明文字, 故用 HTML_EXT_MARK 标题判定而非关键词「热点拓展」。
    ext_path = contract.path_extension(root, d)
    ext_ranks = set()
    if os.path.exists(ext_path):
        try:
            ext_ranks = {int(k) for k in json.load(io.open(ext_path, encoding="utf-8")).keys()}
        except Exception:
            ext_ranks = set()
    scope_bad = []
    for i in range(1, total + 1):
        p = contract.page_path(root, d, i)
        if not os.path.exists(p):
            continue
        has_block = contract.HTML_EXT_MARK in io.open(p, encoding="utf-8").read()
        if i in ext_ranks and not has_block:
            scope_bad.append(f"q{i:02d} 缺拓展块")
        if i not in ext_ranks and has_block:
            scope_bad.append(f"q{i:02d} 有拓展块但 extension.json 无此 rank")
    check("拓展块覆盖 == extension.json 的 rank 集合", not scope_bad, "; ".join(scope_bad[:8]))

    # 输出
    fails = [r for r in results if not r[0]]
    for ok, name, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    print(f"HTML 校验: {len(results) - len(fails)}/{len(results)} 通过 "
          f"(条目 {total} 条，其中追加追踪 {len(extra_ranks)} 条; 非 full 回答 {not_full} 条)")
    if fails:
        sys.exit(1)
    print("[OK] 约束四校验全部通过")


if __name__ == "__main__":
    main()
