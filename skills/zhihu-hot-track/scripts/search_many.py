# -*- coding: utf-8 -*-
"""批量执行扩展搜索(Agent 发散分析用)。

用法: python search_many.py <queries.json> <输出目录> [--db zhihu|global] [--delay 8]
queries.json 格式: [{"rank": 1, "query": "...", "note": "发散维度"}, ...]
输出: <输出目录>/rank_<n>_<idx>.json + queries 元信息写回
"""
import argparse, json, os, re, subprocess, sys, time

# 基础技术栈(zhihu skill)适配层与本脚本同目录, 见 zhihu_env.py 的模块说明
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zhihu_env  # noqa: E402

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
    ap.add_argument("--db", default="zhihu", choices=["zhihu", "global"])
    ap.add_argument("--delay", type=float, default=8.0)
    ap.add_argument("--count", type=int, default=8)
    args = ap.parse_args()

    cli = cli_path()
    os.makedirs(args.outdir, exist_ok=True)
    queries = json.load(open(args.queries, encoding="utf-8"))
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
                print(f"[{rank:02d}] saved rank_{rank:02d}_{idx[rank]}.json")
                break
            print(f"[{rank:02d}] 限流, 15s后重试")
            time.sleep(15)
        time.sleep(args.delay)
    print("done:", len(queries), "queries")

if __name__ == "__main__":
    main()
