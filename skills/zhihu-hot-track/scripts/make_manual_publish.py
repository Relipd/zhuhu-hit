# -*- coding: utf-8 -*-
"""生成"待手动发布"清单: 把未发布的拟答稿整理成可直接复制粘贴的文档。

用法: python make_manual_publish.py --root R --date D --ranks 15,16,17,18,19 --out <md>
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--ranks", default=None,
                    help="要人工发的 rank; 省略则读发布台账, 取「应发但还没发」的"
                         "(blocked / blocked_limit / pending_manual 且 ≤ 每日上限)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--why", default="因平台发布频率限制未能自动发出")
    args = ap.parse_args()

    with io.open(contract.path_answers(args.root, args.date), encoding="utf-8-sig") as f:
        summary = {s["rank"]: s for s in json.load(f)}
    if args.ranks:
        ranks = [int(x) for x in args.ranks.split(",") if x.strip()]
    else:
        # 从台账取"应发但未发": blocked/blocked_limit/pending_manual, 且在前 PUBLISH_TOP_N 条内
        lp = os.path.join(contract.day_dir(args.root, args.date), contract.LEDGER_FILE)
        led = json.load(io.open(lp, encoding="utf-8-sig")) if os.path.exists(lp) else {"items": {}}
        ranks = sorted(int(k) for k, v in led.get("items", {}).items()
                       if v.get("status") in ("blocked", "blocked_limit", "pending_manual")
                       and int(k) <= contract.PUBLISH_TOP_N)
        if not ranks:
            print("台账显示没有待人工发布的条目(前 %d 条均已发布)" % contract.PUBLISH_TOP_N)
            return 0

    out = ["# 待手动发布（%d 篇）" % len(ranks), "",
           "说明：%s。" % args.why,
           "复制每个条目的「正文」到对应问题页的回答框即可；知乎「回答」没有标题字段，",
           "标题仅供你参考（也可自行决定要不要把标题当正文第一句）。", ""]
    for rk in ranks:
        s = summary.get(rk)
        if not s:
            continue
        p = contract.path_draft(args.root, args.date, rk)
        if not os.path.exists(p):
            out += ["---", "## rank %d · 缺拟答稿" % rk, ""]
            continue
        lines = io.open(p, encoding="utf-8-sig").read().strip().splitlines()
        title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else ""
        body = "\n".join(lines[1:]).strip()
        out += ["---", "",
                "## rank %d · %s" % (rk, s["title"]),
                "",
                "问题链接：%s" % s["url"],
                "",
                "标题（参考）：%s" % title,
                "",
                "正文（%d 字：%s）：" % (len(re.sub(r"\s", "", body)),
                                        "、".join("%d" % len(re.sub(r"\s", "", x))
                                                  for x in body.split("\n\n") if x.strip())),
                "", "```text", body, "```", ""]
    io.open(args.out, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print("已生成 %s（%d 篇）" % (args.out, len(ranks)))


if __name__ == "__main__":
    sys.exit(main())
