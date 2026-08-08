# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 回答全文补全(尽力而为)。

搜索接口的 ContentText 是摘要(截断)。本脚本用知乎网页公开 API
(api/v4/answers/{id}) 尝试补全, 并通过 content_need_truncated 标记状态:
  full      已补全为全文
  truncated  网页 API 也截断(需网页登录 Cookie, 当前凭证不可用) -> 保留摘要并标注
  summary    网页 API 无内容, 保留搜索摘要

用法: python fulltext.py --root <工作根目录> --date 2026-08-08 [--delay 1.0]
说明: 结果写回 answers_summary.json 的 text 字段, 并新增 content_status 标记;
      运行于 Agent 分析之前或之后均可(之后则截断回答的分析需标注基于摘要)。
"""
import argparse, json, os, re, sys, time, urllib.request

def qid_of(url):
    m = re.search(r"/question/(\d+)", url or "")
    return m.group(1) if m else None

def fetch_answer(aid, timeout=20):
    """返回 (content_html, need_truncated) 或抛异常"""
    url = f"https://www.zhihu.com/api/v4/answers/{aid}?include=content"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    content = d.get("content", "") or ""
    plain = re.sub(r"<[^>]+>", "", content).strip()
    return plain, bool(d.get("content_need_truncated"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数(防限流)")
    ap.add_argument("--force", action="store_true", help="已补全的也重抓")
    args = ap.parse_args()

    day = os.path.join(args.root, "raw", args.date)
    path = os.path.join(day, "answers_summary.json")
    summary = json.load(open(path, encoding="utf-8"))

    stats = {"full": 0, "truncated": 0, "summary": 0}
    for s in summary:
        for a in s["answers"]:
            if a.get("content_status") == "full" and not args.force:
                stats["full"] += 1
                continue
            aid = a["url"].split("/answer/")[1].split("?")[0]
            try:
                plain, truncated = fetch_answer(aid)
                if plain and len(plain) > len(a["text"]):
                    a["text"] = plain
                a["content_status"] = "truncated" if truncated else ("full" if plain else "summary")
            except Exception as e:
                a["content_status"] = "summary"
                print(f"  #{s['rank']} answer={aid} 抓取失败: {type(e).__name__}")
            stats[a["content_status"]] += 1
            time.sleep(args.delay)

    json.dump(summary, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"补全完成: full={stats['full']} truncated={stats['truncated']} summary={stats['summary']}")
    print("truncated/summary 的回答为接口摘要, 备注列已由 fill_excel 自动标注; 全文需知乎网页登录")

if __name__ == "__main__":
    main()
