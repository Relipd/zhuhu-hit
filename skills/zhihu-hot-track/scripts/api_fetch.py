# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 优化抓取方案(API 直拉回答列表,替代搜索变体)

背景(2026-08-20 优化):
  旧方案 run.py 用 6 个搜索变体/题 × 20 题 = 120 次搜索(约8分钟), 且每问题只能合并出 3-6 条摘要回答。
  本方案: 热榜 URL 已含 question ID -> 带网页 Cookie 直连 api/v4/questions/{id}/answers
  每问题 2 次调用(翻页拉 20 条候选,约2s/题, 20题约40秒), 返回完整全文(未截断)。

用法:
  python api_fetch.py --root <工作根目录> --date 2026-08-20 [--limit 10] [--cookie <cookies.txt>]

前置:
  hot.json 已存在(由 run.py 或手动抓取)。
  Cookie 用 playwright-cli 从 Edge 持久 profile 提取(见 SKILL Step 1.2 方式A):
    必带 z_c0; 无 Cookie 直连 api/v4 会 403(坑11)。

输出(与 run.py 完全同格式, 兼容 check/fill_excel/gen_html):
  <root>/raw/<date>/answers_summary.json   (每题取 top2 = 最高赞 + 最多评论, 去重补足, 共 2×20=40 条)

经济性: 每问题只保留最高赞 + 最多评论各 1 条(去重后不足 2 条则以第二高赞/评论补足)。
        40 条回答足够四维分析(Agent 逐条阅读), 避免 200 条的全量分析成本。
"""
import argparse, html, json, os, re, sys, time, urllib.request

def qid_of(url):
    m = re.search(r"/question/(\d+)", url or "")
    return m.group(1) if m else None

def clean_html(s):
    """知乎 content 是 HTML: 去标签、图占位, 还原实体, 保段落换行"""
    if not s:
        return ""
    s = re.sub(r"<noscript>.*?</noscript>", "", s, flags=re.S)
    s = re.sub(r"<figure>.*?</figure>", "[图片]", s, flags=re.S)
    s = re.sub(r"<img[^>]*>", "[图片]", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>", "\n", s)
    s = re.sub(r"</(?:li|blockquote|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def fetch_answers(cookies, qid, limit, offset=0, retry=3):
    """带 Cookie 直连问题回答列表; 返回 (data, totals) 或抛错"""
    url = (f"https://www.zhihu.com/api/v4/questions/{qid}/answers"
           f"?include=content,excerpt,voteup_count,author,comment_count"
           f"&limit={limit}&offset={offset}&sort_by=default&platform=desktop")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.zhihu.com/question/{qid}",
        "Accept": "application/json, text/plain, */*",
    }
    if cookies:
        headers["Cookie"] = cookies
    last = None
    for attempt in range(retry):
        try:
            req = urllib.request.Request(url, headers=headers)
            r = urllib.request.urlopen(req, timeout=20)
            d = json.loads(r.read().decode("utf-8"))
            return d.get("data", []), d.get("paging", {}).get("totals", 0)
        except Exception as e:
            last = e
            if attempt < retry - 1:
                time.sleep(3 * (attempt + 1))
    raise last

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd(), help="工作根目录")
    ap.add_argument("--date", required=True, help="抓取日期 YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=10, help="每问题最多回答数(默认10)")
    ap.add_argument("--cookie", default=None, help="网页 Cookie 文件(含 z_c0; 无则尽力直连)")
    ap.add_argument("--delay", type=float, default=0.5, help="每问题间隔秒数")
    args = ap.parse_args()

    day = os.path.join(args.root, "raw", args.date)
    hot_out = os.path.join(day, "hot.json")
    if not os.path.exists(hot_out):
        sys.exit(f"缺 hot.json: {hot_out} (先跑 run.py 或手动抓取热榜)")
    cookies = None
    if args.cookie and os.path.exists(args.cookie):
        cookies = open(args.cookie, encoding="ascii", errors="ignore").read().strip()
    elif args.cookie:
        print(f"警告: Cookie 文件不存在 {args.cookie}, 将不带 Cookie 直连(可能403)")

    hot = json.load(open(hot_out, encoding="utf-8-sig"))
    items = hot["Data"]["Items"]
    print(f"热榜 {len(items)} 条, 每问题最多 {args.limit} 条回答, 带Cookie={'是' if cookies else '否'}")

    summary = []
    ok, fail = 0, 0
    for i, it in enumerate(items, 1):
        qid = qid_of(it["Url"])
        if not qid:
            summary.append({"rank": i, "qid": None, "title": it["Title"], "url": it["Url"],
                            "summary": it.get("Summary", ""), "answers": []})
            print(f"[{i:02d}] 无 qid, 跳过")
            continue
        t0 = time.time()
        try:
            # 拉 2 页候选(20 条), 保证「最多评论」不一定在前 10 也能被选中
            answers_raw, totals = fetch_answers(cookies, qid, 10, offset=0)
            answers_raw2, _ = fetch_answers(cookies, qid, 10, offset=10)
            answers_raw = (answers_raw or []) + (answers_raw2 or [])
            seen, cand = set(), []
            for a in answers_raw:
                u = a.get("url", "")
                if not u or u in seen:
                    continue
                seen.add(u)
                author = (a.get("author") or {}).get("name", "")
                text = clean_html(a.get("content", ""))
                if not text:
                    text = a.get("excerpt", "")
                cand.append({
                    "url": u, "text": text,
                    "likes": a.get("voteup_count") or 0,
                    "author": author,
                    "comment_count": a.get("comment_count") or 0,
                    "content_status": "full" if not a.get("content_need_truncated") else "truncated",
                })
            cand = [x for x in cand if x["text"]]
            # 选 top2: 最高赞 + 最多评论(去重; 若同一则补第二高赞/最多评论)
            by_likes = sorted(cand, key=lambda x: -x["likes"])
            by_comments = sorted(cand, key=lambda x: -x["comment_count"])
            picked, urls = [], set()
            for src in (by_likes, by_comments):
                for x in src:
                    if x["url"] not in urls:
                        picked.append(x)
                        urls.add(x["url"])
                        break
            if len(picked) < 2:  # 候选不足时兜底
                for x in by_likes:
                    if len(picked) >= 2:
                        break
                    if x["url"] not in urls:
                        picked.append(x)
                        urls.add(x["url"])
            answers = picked[:2]
            summary.append({"rank": i, "qid": qid, "title": it["Title"], "url": it["Url"],
                            "summary": it.get("Summary", ""), "answers": answers})
            trunc = sum(1 for x in answers if x["content_status"] != "full")
            tag = "+".join(f"{x['author']}(👍{x['likes']}/💬{x['comment_count']})" for x in answers)
            print(f"[{i:02d}/{len(items)}] top2: {tag} (服务端total={totals}, 截断{trunc}) "
                  f"{time.time()-t0:.1f}s")
            ok += 1
        except Exception as e:
            print(f"[{i:02d}/{len(items)}] ERR: {type(e).__name__}: {e}")
            summary.append({"rank": i, "qid": qid, "title": it["Title"], "url": it["Url"],
                            "summary": it.get("Summary", ""), "answers": []})
            fail += 1
        time.sleep(args.delay)

    out = os.path.join(day, "answers_summary.json")
    json.dump(summary, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    total = sum(len(s["answers"]) for s in summary)
    print(f"\n完成: {ok} 成功 / {fail} 失败, {len(summary)} 问题, {total} 回答(每题top2) -> {out}")
    print("下一步: Agent 逐条写四维分析到 analysis.json, 然后 check.py 校验、fill_excel.py 填表、gen_html.py 出网页")

if __name__ == "__main__":
    main()
