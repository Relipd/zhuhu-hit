# -*- coding: utf-8 -*-
"""批量执行扩展搜索(Agent 发散分析用)。

用法: python search_many.py <queries.json> <输出目录> [--db zhihu|global] [--delay 8]
queries.json 格式: [{"rank": 1, "query": "...", "note": "发散维度"}, ...]
输出: <输出目录>/rank_<n>_<idx>.json + queries 元信息写回
"""
import argparse, json, os, subprocess, sys, time

def cli_path():
    env = os.environ.get("ZHIHU_CLI")
    if env and os.path.exists(env):
        return env
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ZhihuCLI", "current", "zhihu-cli.exe")
    if os.path.exists(local):
        return local
    sys.exit("未找到 zhihu-cli")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queries", help="queries.json 路径")
    ap.add_argument("outdir", help="结果输出目录")
    ap.add_argument("--db", default="zhihu", choices=["zhihu", "global"])
    ap.add_argument("--delay", type=float, default=8.0)
    ap.add_argument("--count", type=int, default=8)
    args = ap.parse_args()

    cli = cli_path()
    os.makedirs(args.outdir, exist_ok=True)
    queries = json.load(open(args.queries, encoding="utf-8"))
    idx = {}
    for q in queries:
        rank = q["rank"]
        idx[rank] = idx.get(rank, 0) + 1
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
                print(f"[{rank:02d}] saved rank_{rank:02d}_{idx[rank]}.json")
                break
            print(f"[{rank:02d}] 限流, 15s后重试")
            time.sleep(15)
        time.sleep(args.delay)
    print("done:", len(queries), "queries")

if __name__ == "__main__":
    main()
