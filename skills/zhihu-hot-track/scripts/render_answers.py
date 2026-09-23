# -*- coding: utf-8 -*-
"""把当日回答渲染成**可安全阅读**的文本(主 Agent 四维分析前的固定动作)。

为什么需要它(2026-09-14 成本实测)
----------------------------------
1. `answers_summary.json` 里的长回答常远超 read 工具的**单行 2000 字符上限**, 直接读会被截断,
   于是要反复"补读尾部"——一个 rank 多花一轮(坑 49)。
2. 主 Agent 逐个 rank 读文件, 步数直接乘进缓存成本; **按 `--per` 批打包**能把步数降到 1/5。
3. 渲染时按 `--wrap` 硬换行并去掉平台跟踪参数, 读一次即可覆盖全文。

输出: `<root>/ext_search/<date>/_render/batch_<a>_<b>.md`(默认每批 5 个 rank)
      每个 rank 一段: 标题 / 原链 / 覆盖度 / 每条回答(序号·作者·赞·状态·链接·正文)

用法:
  python render_answers.py --root <ROOT> --date 2026-09-14 [--ranks 1-20] [--per 5] [--wrap 900]
"""
import argparse
import io
import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract   # noqa: E402  数据契约:文件名 / 字段 / 值域的单一定义处

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_ranks(spec):
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def render_rank(r, wrap):
    lines = ["# rank %s | %s" % (r.get("rank"), r.get("title", "")),
             "URL: %s" % r.get("url", ""),
             "总数 %s | 覆盖率 %s | 来源 %s" % (r.get("total_answers"), r.get("coverage"), r.get("source"))]
    for i, a in enumerate(r.get("answers") or [], 1):
        lines += ["",
                  "## 回答 %d | %s | 赞 %s | 评论 %s | 状态 %s" % (
                      i, a.get("author") or "匿名", a.get("likes"), a.get("comment_count"),
                      a.get("content_status")),
                  "URL: %s" % a.get("url", "")]
        for para in (a.get("text") or "").strip().split("\n"):
            para = para.strip()
            if para:
                lines.extend(textwrap.wrap(para, wrap) or [""])
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="把当日回答渲染成可按批阅读的文本(读前必做)")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True)
    ap.add_argument("--ranks", default=None, help="要渲染的 rank(如 1-20 / 1,5,7), 默认全部")
    ap.add_argument("--per", type=int, default=5, help="每个批次文件包含几个 rank(默认 5)")
    ap.add_argument("--wrap", type=int, default=900, help="硬换行宽度(默认 900, 低于 read 的 2000 上限)")
    args = ap.parse_args()

    with io.open(contract.path_answers(args.root, args.date), encoding="utf-8-sig") as f:
        rows = json.load(f)
    want = set(parse_ranks(args.ranks)) if args.ranks else None
    rows = [r for r in rows if isinstance(r.get("rank"), int) and (want is None or r["rank"] in want)]
    rows.sort(key=lambda r: r["rank"])
    if not rows:
        sys.exit("[FAIL] 没有可渲染的条目(检查 --ranks 与 answers_summary.json)")

    outdir = os.path.join(args.root, "ext_search", args.date, "_render")
    os.makedirs(outdir, exist_ok=True)
    per = max(1, args.per)
    made = []
    for i in range(0, len(rows), per):
        grp = rows[i:i + per]
        a, b = grp[0]["rank"], grp[-1]["rank"]
        p = os.path.join(outdir, "batch_%02d_%02d.md" % (a, b))
        txt = "".join(render_rank(r, args.wrap) + "\n" for r in grp)
        io.open(p, "w", encoding="utf-8", newline="\n").write(txt)
        made.append((p, len(txt)))

    print("渲染 %d 个 rank -> %d 个批次文件(建议整批 read, 不要逐 rank 读)" % (len(rows), len(made)))
    for p, n in made:
        print("   %s  (%d 字符)" % (p, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
