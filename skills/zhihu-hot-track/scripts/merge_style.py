# -*- coding: utf-8 -*-
"""汇总书写逻辑提取结果 → 候选池(供主 Agent 用奥卡姆剃刀汇编成 书写skill.md)。

为什么需要它: 提取是分批并行做的(每批 5 个 rank 一个 subagent), 同一维度会出现**大量近义重复**
(如"开头直接给判断"会被不同批次各写一遍)。主 Agent 汇编前要先把重复折叠、按维度归类、
并给出**跨批出现频次**, 否则"剃刀"没有依据 —— 频次低且与高频项重复的, 就是该被剃掉的部分。

  python merge_style.py --root <ROOT> --date D            # 只汇总并打印候选池
  python merge_style.py --root <ROOT> --date D --write    # 写出 ext_search/<D>/style_merge.json
"""
import argparse
import glob
import io
import json
import os
import re
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SIM = 0.62          # 近义判定阈值(3-gram Jaccard + 序列相似度取大者)


def sig(text):
    t = re.sub(r"[\s，。、；：（）()「」『』\"'—…·,.;:!?！？]", "", text or "")
    return {"3g": {t[i:i + 3] for i in range(max(len(t) - 2, 1))}, "s": t}


def similar(a, b):
    A, B = sig(a), sig(b)
    j = len(A["3g"] & B["3g"]) / max(len(A["3g"] | B["3g"]), 1)
    return max(j, SequenceMatcher(None, A["s"], B["s"]).ratio())


def main():
    ap = argparse.ArgumentParser(description="汇总书写逻辑提取片段为候选池")
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(contract.ext_search_dir(args.root, args.date),
                                          "style", "style_batch_*.json")))
    if not files:
        sys.exit("[FAIL] 没找到 style_batch_*.json")

    rows, avoids, notes, bad = [], [], [], []
    for fp in files:
        try:
            d = json.load(io.open(fp, encoding="utf-8-sig"))
        except Exception as e:
            bad.append("%s 读取失败 %s" % (os.path.basename(fp), e))
            continue
        tag = os.path.basename(fp).replace("style_batch_", "").replace(".json", "")
        for p in d.get("patterns") or []:
            if p.get("dim") not in contract.STYLE_DIMS:
                bad.append("%s: dim 非法 %r" % (tag, p.get("dim")))
                continue
            rows.append({"dim": p["dim"], "rule": (p.get("rule") or "").strip(),
                         "why": (p.get("why") or "").strip(),
                         "scope": p.get("scope") or "个别",
                         "freq": p.get("freq") or 1,
                         "form": (p.get("example_form") or "").strip(),
                         "batch": tag})
        for a in d.get("avoid") or []:
            avoids.append({"rule": (a.get("rule") or "").strip(),
                           "why": (a.get("why") or "").strip(),
                           "freq": a.get("freq") or 1, "batch": tag})
        if d.get("notes"):
            notes.append({"batch": tag, "notes": d["notes"]})

    # 折叠近义: 同维度内相似度超阈值的合成一条(保留 freq 大的, 合并来源批次)
    merged, dropped = [], []
    for r in sorted(rows, key=lambda x: (-(x["freq"] or 0), x["dim"])):
        for m in merged:
            if m["dim"] == r["dim"] and r["rule"] and similar(m["rule"], r["rule"]) >= SIM:
                m["freq"] = max(m["freq"], r["freq"])
                m["from"].append(r["batch"])
                dropped.append(r)
                break
        else:
            merged.append(dict(r, **{"from": [r["batch"]]}))
    mavoid = []
    for a in sorted(avoids, key=lambda x: -(x["freq"] or 0)):
        for m in mavoid:
            if a["rule"] and similar(m["rule"], a["rule"]) >= SIM:
                m["freq"] = max(m["freq"], a["freq"])
                m["from"].append(a["batch"])
                break
        else:
            mavoid.append(dict(a, **{"from": [a["batch"]]}))

    pool = {"date": args.date, "batches": [os.path.basename(f) for f in files],
            "dims": contract.STYLE_DIMS, "patterns": merged, "avoid": mavoid,
            "notes": notes, "dropped_duplicates": len(dropped), "errors": bad}
    if args.write:
        p = os.path.join(contract.ext_search_dir(args.root, args.date), contract.STYLE_MERGE)
        tmp = p + ".tmp"
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(pool, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        print("候选池写出: %s" % p)
    print("批次 %d 个 | 原始 pattern %d 条 → 折叠后 %d 条(去掉近义重复 %d) | avoid %d 条"
          % (len(files), len(rows), len(merged), len(dropped), len(mavoid)))
    if bad:
        print("[WARN] %d 处结构问题: %s" % (len(bad), bad[:5]))
    for dim in contract.STYLE_DIMS:
        g = [m for m in merged if m["dim"] == dim]
        if not g:
            continue
        print("\n【%s】%d 条" % (dim, len(g)))
        for m in g:
            print("  ·[%s×%d] %s" % (m["scope"], m["freq"], m["rule"][:88]))
    if mavoid:
        print("\n【避免的写法】%d 条" % len(mavoid))
        for a in mavoid:
            print("  × [×%d] %s" % (a["freq"], a["rule"][:88]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
