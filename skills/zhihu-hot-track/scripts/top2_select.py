# -*- coding: utf-8 -*-
"""从已抓取的 answers_summary.json 中, 每问题挑选 top2 回答(最高赞 + 最多评论, 去重补足)。

用途: 抓取时若已按前 10 存了全量, 分析前用本脚本瘦身为 2×20=40 条,
      避免 Agent 对 200 条做全量四维分析的经济开销。

用法:
  python top2_select.py --root <工作根目录> --date 2026-08-20 [--backup 保留原文件为 answers_summary_full.json]

输出: <root>/raw/<date>/answers_summary.json  (覆盖为 top2)
"""
import argparse, json, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True)
    ap.add_argument("--backup", action="store_true", help="原文件备份为 answers_summary_full.json")
    args = ap.parse_args()

    day = os.path.join(args.root, "raw", args.date)
    path = os.path.join(day, "answers_summary.json")
    summary = json.load(open(path, encoding="utf-8"))
    if args.backup:
        json.dump(summary, open(os.path.join(day, "answers_summary_full.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    n_top = 0
    for s in summary:
        ans = s.get("answers", [])
        by_likes = sorted(ans, key=lambda x: -x.get("likes", 0))
        by_comments = sorted(ans, key=lambda x: -x.get("comment_count", 0))
        picked, urls = [], set()
        for src in (by_likes, by_comments):
            for x in src:
                if x["url"] not in urls:
                    picked.append(x)
                    urls.add(x["url"])
                    break
        if len(picked) < 2:
            for x in by_likes:
                if len(picked) >= 2:
                    break
                if x["url"] not in urls:
                    picked.append(x)
                    urls.add(x["url"])
        s["answers"] = picked[:2]
        n_top += len(s["answers"])
    json.dump(summary, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"瘦身完成: {len(summary)} 问题, {n_top} 回答(每题top2) -> {path}")
    for s in summary:
        tag = "+".join(f"{x['author']}(👍{x.get('likes')}/💬{x.get('comment_count')})" for x in s["answers"])
        print(f"  #{s['rank']}: {tag}")

if __name__ == "__main__":
    main()
