# -*- coding: utf-8 -*-
"""批量执行扩展搜索(Agent 发散分析用)。

用法: python search_many.py <queries.json> <输出目录> [--db <平台库>|global] [--delay 8] [--count 4]
queries.json 格式: [{"rank": 1, "query": "...", "note": "发散维度"}, ...]
输出: <输出目录>/rank_<n>_<idx>.json        完整归档(溯源自用, 不删)
      <输出目录>/rank_<n>_<idx>.slim.json   精简摘要(subagent 优先读这个)

为什么要 slim(2026-09-14 成本实测): 完整归档每个 20-46KB, 其中大头是头像 URL、
评论列表、排序分等**与判断无关**的字段; 一个 rank 3-8 轮就是 100-300KB, 全读进上下文
是 Swarm 成本的第一大头。slim 只保留 title/url/作者/赞评/类型/正文摘要(220 字),
体积约为完整版的 1/4-1/5, 是 subagent 的默认读物; 需要核对原文时才读完整归档。
"""
import argparse, json, os, re, subprocess, sys, time

# 基础技术栈适配层与本脚本同目录, 见 zhihu_env.py 的模块说明
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_profile as pf   # noqa: E402  L2 平台档案:默认检索库名
import zhihu_env  # noqa: E402

# slim 保留字段(其余字段一律丢弃: 头像/徽章/评论列表/排序分/内部 id 等)
SLIM_FIELDS = ("Title", "Url", "AuthorName", "VoteUpCount", "CommentCount",
               "ContentType", "ContentText")
SLIM_TEXT_MAX = 220


def slim_payload(d, rank, query, note, db, full_name):
    """把一次检索结果压成"只够判断"的精简版(不改变原归档)。"""
    items = ((d.get("Data") or {}).get("Items") or [])
    out = []
    for it in items:
        row = {k: it.get(k) for k in SLIM_FIELDS if it.get(k) not in (None, "")}
        if row.get("ContentText"):
            row["ContentText"] = str(row["ContentText"])[:SLIM_TEXT_MAX]
        out.append(row)
    return {"_meta": {"rank": rank, "query": query, "note": note, "db": db,
                      "slim": True, "full_archive": full_name, "items": len(out)},
            "Items": out}

def cli_path():
    """CLI 位置统一由适配层解析(与 run.py / fulltext.py 同一套规则)。"""
    try:
        return zhihu_env.require_cli()
    except RuntimeError as e:
        sys.exit(str(e))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queries", help="queries.json 路径")
    ap.add_argument("outdir", help="结果输出目录")
    ap.add_argument("--db", default=pf.get("source_db"),
                    choices=[pf.get("source_db"), "global"],
                    help="检索库: 平台库(默认, 取自平台档案)或 global(全站)")
    ap.add_argument("--delay", type=float, default=8.0)
    ap.add_argument("--count", type=int, default=4,
                    help="每次检索返回条数(默认 4: 实测 8 条里过半与想法无关, 只会撑大上下文)")
    args = ap.parse_args()

    cli = cli_path()
    os.makedirs(args.outdir, exist_ok=True)
    try:
        # utf-8-sig: 提示词让 subagent 用 write 工具落盘(无 BOM), 但人工/PS 手写时可能带 BOM
        # (PS 5.1 的 Set-Content -Encoding UTF8 必写 BOM) —— 读端宽容, 免得白跑一轮(坑 8/25)。
        queries = json.load(open(args.queries, encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit("[FAIL] queries.json 解析失败(%s): %s —— 检查是不是空文件或带了非法字符" % (e, args.queries))
    # 输出编号 = 目录中已有同 rank 的最大编号继续递增, 避免多轮同名静默覆盖。
    # (2026-09-12 实测: 每轮只写 1 条时旧逻辑使文件名恒为 rank_0N_1.json,
    #  第二轮起把上一轮的检索依据覆盖掉, 事后无法溯源)
    def next_index(outdir, rank):
        pat = re.compile(rf"^rank_{rank:02d}_(\d+)\.json$")
        mx = 0
        for fn in os.listdir(outdir):
            m = pat.match(fn)
            if m:
                mx = max(mx, int(m.group(1)))
        return mx + 1

    idx = {}
    for q in queries:
        rank = q["rank"]
        if rank not in idx:
            idx[rank] = next_index(args.outdir, rank) - 1
        idx[rank] += 1
        out = os.path.join(args.outdir, f"rank_{rank:02d}_{idx[rank]}.json")
        cmd = [cli, "search", args.db, "--query", q["query"], "--count", str(args.count)]
        if args.db == "global":
            cmd += ["--search-db", q.get("search_db", "all")]
            if q.get("filter"):
                cmd += ["--filter", q["filter"]]
        for attempt in range(3):
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            try:
                d = json.loads(r.stdout)
            except Exception:
                print(f"[{rank}] {q['query'][:20]} 解析失败")
                break
            if d.get("Data") is not None:
                d["_meta"] = {"rank": rank, "query": q["query"], "note": q.get("note", ""), "db": args.db}
                json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                slim_path = out[:-5] + ".slim.json"
                json.dump(slim_payload(d, rank, q["query"], q.get("note", ""), args.db,
                                       os.path.basename(out)),
                          open(slim_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print(f"[{rank:02d}] saved {os.path.basename(out)} + {os.path.basename(slim_path)}"
                      f" ({os.path.getsize(out)//1024}KB -> {os.path.getsize(slim_path)//1024}KB)")
                break
            print(f"[{rank:02d}] 限流, 15s后重试")
            time.sleep(15)
        time.sleep(args.delay)
    print("done:", len(queries), "queries")

if __name__ == "__main__":
    main()
