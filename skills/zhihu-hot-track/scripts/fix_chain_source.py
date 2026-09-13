# -*- coding: utf-8 -*-
"""修复 chains[].source 的 answer_index / url 错配(2026-09-13 新增)。

为什么能自动修: 实测 3 个 rank 的链出处把「哪条回答」写错了(含写 0 基的 answer_index=0 越界),
但 `source.likes` 与 `source.url` 之一通常是**从真实回答抄来的** —— 于是可以用 likes(必要时配合
url)在 answers_summary.json 里反查出正确序号并回填。修不了(对不上任何回答)的一条条列出来交人处理。

用法:
  python fix_chain_source.py --root <ROOT> --date D            # 只报告
  python fix_chain_source.py --root <ROOT> --date D --write    # 回填
"""
import argparse
import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="用 likes/url 反查并回填 chains[].source 的正确序号")
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    with io.open(contract.path_answers(args.root, args.date), encoding="utf-8-sig") as f:
        summary = {str(s["rank"]): s for s in json.load(f)}

    src_dir = contract.ext_search_dir(args.root, args.date)
    fixed, unresolved, files = [], [], 0
    for d in sorted(glob.glob(os.path.join(src_dir, "rank_*")), key=lambda p: int(p.split("_")[-1])):
        rk = d.split("_")[-1]
        fp = os.path.join(d, "rank_%s.json" % rk)
        if not os.path.exists(fp) or rk not in summary:
            continue
        with io.open(fp, encoding="utf-8-sig") as f:
            data = json.load(f)
        ans = summary[rk].get("answers") or []
        changed = False
        for ci, ch in enumerate(data.get("chains") or [], 1):
            src = ch.get("source")
            if not isinstance(src, dict):
                continue
            idx, likes = src.get("answer_index"), src.get("likes")
            ok = (isinstance(idx, int) and 1 <= idx <= len(ans)
                  and (likes is None or ans[idx - 1].get("likes") == likes))
            if ok:
                continue
            # 用 likes 反查(唯一命中才算), likes 缺失/重复时再用 url
            cand = [i for i, a in enumerate(ans, 1) if likes is not None and a.get("likes") == likes]
            if len(cand) != 1:
                u = contract.canon_url(src.get("url") or "")
                cand = [i for i, a in enumerate(ans, 1)
                        if u and contract.canon_url(a.get("url") or "") == u]
            if len(cand) == 1:
                good = cand[0]
                fixed.append((rk, ci, idx, likes, good, ans[good - 1].get("likes")))
                if args.write:
                    src["answer_index"] = good
                    src["likes"] = ans[good - 1].get("likes")
                    src["url"] = ans[good - 1].get("url")
                    changed = True
            else:
                unresolved.append((rk, ci, idx, likes, len(cand)))
        if changed:
            tmp = fp + ".tmp"
            with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, fp)
            files += 1

    print("可修复 %d 处 | 无法自动判定 %d 处 | 已改写 %d 个文件(写=%s)"
          % (len(fixed), len(unresolved), files, args.write))
    for rk, ci, bad, likes, good, gl in fixed:
        print("  rank%-3s chains[%d] answer_index %s→%d (likes %s→%s)"
              % (rk, ci, bad, good, likes, gl))
    for rk, ci, bad, likes, n in unresolved:
        print("  [需人工] rank%-3s chains[%d] answer_index=%s likes=%s —— 候选命中 %d 条"
              % (rk, ci, bad, likes, n))
    return 0 if not unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
