# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 单问题追加追踪(把"单独搜的一个问题"聚合进当日交付物)。

定位
----
用户可能只想深挖**某一个**问题(不在热榜里也行)。本脚本把它注册成当日的**追加条目**:
  · rank 接在当日现有最大值之后(默认 21、22…), 因此全链路 id 空间不变 ——
    analysis.json / extension.json / ext_search/<D>/rank_<N>/ / Excel 排名列 / HTML q<N>.html 全部照旧;
  · 写 raw/<D>/extra_questions.json 登记(与榜单条目区分), 并在 answers_summary 条目上标 extra=true;
  · **不需要当天先跑榜单**: hot.json 缺失也能工作(条目数基准已改为 answers_summary)。

与榜单的区别(用户 2026-09-12 指定):
  · 榜单: 只有**前 10** 跑 Swarm 拓展;
  · 追加问题: **默认跑 Swarm 拓展**(单 rank, 约 1.6-2.7 万 token)。

用法
----
  python scripts/question_add.py --root <ROOT> --date <D> --url <问题/回答/专栏链接>
                                 [--top 5] [--pages 3] [--delay 1.5] [--rank N] [--dry-run]

之后依次: Agent 写四维分析 → 该 rank 跑 Swarm → merge_extension(自动复核) → topic_lib → 下游交付物。
"""
import argparse
import io
import json
import os
import re
import sys
import time

import contract

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import question_fetch as qf  # noqa: E402  复用问题维度抓取(接口/解析/重试全在同一处)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)



def main():
    ap = argparse.ArgumentParser(description="单问题追加追踪(聚合进当日交付物)")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True)
    ap.add_argument("--url", required=True, help="问题/回答/专栏链接")
    ap.add_argument("--title", default=None, help="标题(接口取不到时可手填)")
    ap.add_argument("--top", type=int, default=5, help="保留的高赞回答数(默认5)")
    ap.add_argument("--pages", type=int, default=3, help="取几页(每页20条)")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--rank", type=int, default=None, help="指定 rank(默认接在当日最大值之后)")
    ap.add_argument("--dry-run", action="store_true", help="只解析与分配 rank, 不抓取不落盘")
    args = ap.parse_args()

    url = args.url.strip()
    kind = qf.kind_of(url)
    if not kind or kind == "unknown":
        sys.exit("[FAIL] 无法识别链接类型(支持 问题/回答/专栏): %s" % url)
    qid = qf.qid_of(url)
    if kind == "article":
        m = re.search(r"/p/(\d+)", url)
        qid = m.group(1) if m else None
    if not qid:
        sys.exit("[FAIL] 从链接中解析不到 id: %s" % url)
    # 回答链接 → 追踪它所属的**问题**(那才是有拓展价值的目标)
    if kind == "answer":
        kind, url = "question", "https://www.zhihu.com/question/%s" % qid

    ans_path = contract.path_answers(args.root, args.date)
    ext_path = contract.path_extra(args.root, args.date)
    summary = load_json(ans_path, [])
    extra = load_json(ext_path, {"items": []})
    if isinstance(extra, list):          # 容错: 允许裸数组
        extra = {"items": extra}

    if any(str(s.get("url") or "") == url for s in summary):
        rank = next(int(s["rank"]) for s in summary if str(s.get("url")) == url)
        print("[info] 该问题已在当日数据里: rank %d(如需重抓请先删除该条目)" % rank)
        return 0

    rank = args.rank or (max([int(s["rank"]) for s in summary], default=0) + 1)
    if any(int(s["rank"]) == rank for s in summary):
        sys.exit("[FAIL] rank %d 已被占用(用 --rank 指定其他值)" % rank)

    if args.dry_run:
        print("dry-run: kind=%s id=%s 分配 rank=%d(当日已有 %d 条)"
              % (kind, qid, rank, len(summary)))
        return 0

    cookie, cookie_path = qf.load_cookie(args.root, args.date)
    print("[info] cookie: " + (f"复用 {cookie_path}(不验证、不删除)" if cookie
                               else "无 —— 网页接口可能 403, 将无法抓取"))
    answers, total, title, src = [], None, "", None
    try:
        if kind == "question":
            answers, total, title = qf.fetch_question(qid, args.top, cookie, args.delay, args.pages)
            src = "web_question"
        else:
            answers, total, title = qf.fetch_article(qid, cookie)
            src = "web_article"
    except Exception as e:
        sys.exit("[FAIL] 抓取失败: %s: %s" % (type(e).__name__, e))
    title = args.title or title or ("(标题未知) %s" % qid)

    answers = sorted(answers, key=lambda a: -(a.get("likes") or 0))[:args.top]
    rec = {"rank": rank, "qid": qid, "title": title, "url": url, "summary": "",
           "answers": answers, "total_answers": total, "coverage": None,
           "source": src, "sources": ["web"], "extra": True}
    if total:
        rec["coverage"] = round(len(answers) / total, 4)

    summary = [s for s in summary if int(s["rank"]) != rank] + [rec]
    summary.sort(key=lambda s: int(s["rank"]))
    os.makedirs(contract.day_dir(args.root, args.date), exist_ok=True)
    with io.open(ans_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    extra["items"] = [x for x in extra.get("items", []) if int(x.get("rank", 0)) != rank]
    extra["items"].append({"date": args.date, "rank": rank, "title": title, "url": url,
                           "qid": qid, "kind": kind, "source": src,
                           "added_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    extra["items"].sort(key=lambda x: int(x["rank"]))
    with io.open(ext_path, "w", encoding="utf-8") as f:
        json.dump(extra, f, ensure_ascii=False, indent=1)

    cov = ("覆盖 %d/%d" % (len(answers), total)) if total else "覆盖 n/a"
    print("[OK] 追加 rank %d: %s" % (rank, title))
    print("     回答 %d 条 | %s | 来源 %s | 登记 extra_questions.json" % (len(answers), cov, src))
    print("\n下一步(该问题按规则**默认跑拓展**):")
    print("   1) Agent 依据 raw/%s/answers_summary.json 的 rank %d 写四维分析到 analysis.json"
          % (args.date, rank))
    print("   2) 建目录 ext_search/%s/rank_%d/ 并派 1 个 subagent 产出 chains(链式 schema)"
          % (args.date, rank))
    print("   3) python scripts/merge_extension.py --root %s --date %s  (汇总+自动复核)"
          % (args.root, args.date))
    print("   4) python scripts/topic_lib.py update --root %s --date %s  → fill_excel → gen_html → verify_html"
          % (args.root, args.date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
