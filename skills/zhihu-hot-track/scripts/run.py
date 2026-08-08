# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 数据抓取全流程(热榜 + 多变体搜索 + 合并去重)。

用法:
  python run.py --root <工作根目录> --date 2026-08-08 [--limit 20] [--variants 6] [--resume]

输出(按日期归档):
  <root>/raw/<date>/hot.json
  <root>/raw/<date>/search_<n>_v<k>.json   (每问题 variants 个变体查询)
  <root>/raw/<date>/answers_summary.json    (URL去重, 点赞降序, 取前10)

后续: Agent 读取 answers_summary.json 逐条写四维分析到 analysis.json,
      再用 fill_excel.py / gen_html.py 产出交付物, check.py 校验。
"""
import argparse, json, os, re, subprocess, sys, time

def cli_path():
    env = os.environ.get("ZHIHU_CLI")
    if env and os.path.exists(env):
        return env
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ZhihuCLI", "current", "zhihu-cli.exe")
    if os.path.exists(local):
        return local
    sys.exit("未找到 zhihu-cli, 设置环境变量 ZHIHU_CLI 或先安装(见 zhihu skill)")

def variants(title, n):
    segs = [s for s in re.split(r"[，,。；;：]", title) if s.strip()]
    if len(segs) < 3:  # 段落不足时的兜底
        pool = [title[:30], title[10:40], title[:15] + title[-10:]]
        return pool[:n]
    combos = [title, title.split("？")[0],
              segs[0] + segs[1], segs[1] + segs[2],
              segs[0] + segs[2], segs[0] + segs[1][:8]]
    return combos[:n]

def qid_of(url):
    m = re.search(r"/question/(\d+)", url or "")
    return m.group(1) if m else None

def fetch_one(cli, query, out, n=10, sleep=8, max_try=3):
    """单次搜索, 限流退避; 返回 True/False"""
    for attempt in range(max_try):
        r = subprocess.run([cli, "search", "zhihu", "--query", query, "--count", str(n)],
                           capture_output=True, text=True, encoding="utf-8")
        try:
            d = json.loads(r.stdout)
        except Exception:
            print(f"  解析失败: {r.stdout[:120]}")
            return False
        if d.get("Data") is not None:
            json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return True
        print(f"  限流({d.get('error', {}).get('code')}), {15}s 后重试 {attempt + 1}/{max_try}")
        time.sleep(15)
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd(), help="工作根目录(默认当前目录)")
    ap.add_argument("--date", required=True, help="抓取日期 YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=20, help="热榜条数(默认20)")
    ap.add_argument("--variants", type=int, default=6, help="每问题查询变体数(默认6, 2-6)")
    ap.add_argument("--resume", action="store_true", help="跳过已存在的搜索结果")
    args = ap.parse_args()

    cli = cli_path()
    day = os.path.join(args.root, "raw", args.date)
    os.makedirs(day, exist_ok=True)

    # 1. 热榜
    hot_out = os.path.join(day, "hot.json")
    if not os.path.exists(hot_out):
        r = subprocess.run([cli, "hot", "--limit", str(args.limit)],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            sys.exit(f"热榜失败: {r.stdout[:200]}")
        json.dump(json.loads(r.stdout), open(hot_out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"热榜 {args.limit} 条 -> hot.json")
    else:
        print("hot.json 已存在, 跳过(--resume 或删除文件重抓)")

    hot = json.load(open(hot_out, encoding="utf-8-sig"))
    items = hot["Data"]["Items"]
    n_v = max(2, min(args.variants, 6))

    # 2. 变体搜索
    for i, it in enumerate(items, 1):
        for k, q in enumerate(variants(it["Title"], n_v), 1):
            out = os.path.join(day, f"search_{i:02d}_v{k}.json")
            if args.resume and os.path.exists(out):
                continue
            if fetch_one(cli, q, out):
                print(f"[{i:02d}/{len(items)}] v{k} ok")
            else:
                print(f"[{i:02d}/{len(items)}] v{k} 失败(3次尝试后放弃)")
            time.sleep(8)

    # 3. 合并去重
    summary = []
    for i, it in enumerate(items, 1):
        qid = qid_of(it["Url"])
        seen, answers = set(), []
        for k in range(1, n_v + 1):
            f = os.path.join(day, f"search_{i:02d}_v{k}.json")
            if not os.path.exists(f):
                continue
            s = json.load(open(f, encoding="utf-8-sig"))
            for x in s.get("Data", {}).get("Items", []):
                if x.get("ContentType") != "Answer" or qid_of(x.get("Url")) != qid:
                    continue
                u = x.get("Url")
                if u in seen:
                    continue
                seen.add(u)
                answers.append({"url": u, "text": x.get("ContentText", ""),
                                "likes": x.get("VoteUpCount") or 0,
                                "author": x.get("AuthorName", ""),
                                "comment_count": x.get("CommentCount") or 0})
        answers.sort(key=lambda a: -a["likes"])
        summary.append({"rank": i, "qid": qid, "title": it["Title"], "url": it["Url"],
                        "summary": it.get("Summary", ""), "answers": answers[:10]})
        print(f"[{i:02d}] {len(answers)} 条回答(取前10) 最高赞={answers[0]['likes'] if answers else '-'}")
    json.dump(summary, open(os.path.join(day, "answers_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    total = sum(len(s["answers"]) for s in summary)
    print(f"完成: {len(summary)} 问题, {total} 回答 -> {os.path.join(day, 'answers_summary.json')}")
    print("下一步: Agent 逐条写四维分析到 analysis.json, 然后 check.py 校验、fill_excel.py 填表、gen_html.py 出网页")

if __name__ == "__main__":
    main()
