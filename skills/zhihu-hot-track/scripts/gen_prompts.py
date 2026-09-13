# -*- coding: utf-8 -*-
"""为热榜 rank 生成 subagent 提示词(取代一次性临时脚本)。

用法:
  # 拓展+拟答稿提示词(每个 rank 一份 PROMPT.md)
  python gen_prompts.py --root <ROOT> --date D --ranks 1-20
  # 情绪判断提示词(按批次, 每批 N 个 rank 一份 EMOTION_PROMPT_<tag>.md)
  python gen_prompts.py --root <ROOT> --date D --ranks 1-20 --emotion --per 5

产出位置(与 rank 的工作目录约定一致, 见 SKILL.md):
  <root>/ext_search/<D>/rank_<n>/PROMPT.md
  <root>/ext_search/<D>/emotion/EMOTION_PROMPT_<tag>.md
"""
import argparse
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

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.environ.get("DSH_PYTHON") or sys.executable
# 平台注入项(2026-09-13: 把"通用件"落到实处 —— 书写类模板不再硬编码知乎,
# 换平台只改这三个默认值, 模板与 method 文档不动)
PLATFORM = os.environ.get("TRACK_PLATFORM", "知乎")
UNIT = os.environ.get("TRACK_UNIT", "回答")
PLATFORM_NOTES = os.environ.get(
    "TRACK_PLATFORM_NOTES",
    "知乎「回答」没有标题字段（只有「文章」有），所以稿子只发正文、不发标题；"
    "标题仅用于我们自己的交付物（Excel「拟答参考」sheet 与 HTML 页内块）。")
SWARM_TPL = os.path.join(HERE, "prompt_swarm.md")
EMOTION_TPL = os.path.join(HERE, "prompt_emotion.md")
STYLE_TPL = os.path.join(HERE, "prompt_style.md")
WRITE_TPL = os.path.join(HERE, "prompt_write.md")


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


def build_swarm(root, date, rows, quiet=False):
    tpl = io.open(SWARM_TPL, encoding="utf-8-sig").read()
    cats = "/".join(contract.LIB_CATS)
    made = []
    for r in rows:
        rk = r["rank"]
        if not isinstance(rk, int):
            continue
        d = os.path.join(root, "ext_search", date, "rank_%d" % rk)
        os.makedirs(d, exist_ok=True)
        # 查询文件(与历史约定一致: 不补零; 目录内的检索留档才是 rank_0N_*.json)
        qf = os.path.join(root, "ext_search", date, "queries_rank_%d.json" % rk)
        if not os.path.exists(qf):
            io.open(qf, "w", encoding="utf-8", newline="\n").write("[]")
        txt = tpl.format(py=PY, root=root, date=date, rank=rk, title=r["title"],
                         url=r["url"], scripts=HERE, cats=cats)
        p = os.path.join(d, "PROMPT.md")
        io.open(p, "w", encoding="utf-8", newline="\n").write(txt)
        made.append(p)
    if not quiet:
        print("拓展提示词 %d 份" % len(made))
        for p in made:
            print("  ", p)
    return made


def build_emotion(root, date, rows, per, quiet=False):
    tpl = io.open(EMOTION_TPL, encoding="utf-8-sig").read()
    ranks = [r["rank"] for r in rows if isinstance(r["rank"], int)]
    outdir = os.path.join(root, "ext_search", date, "emotion")
    os.makedirs(outdir, exist_ok=True)
    made = []
    for i in range(0, len(ranks), per):
        grp = ranks[i:i + per]
        tag = "%02d" % (i // per + 1)
        frag = os.path.join(outdir, "emotion_batch_%s.json" % tag)
        txt = tpl.format(py=PY, root=root, date=date, ranks=",".join(str(x) for x in grp),
                         out=frag, scripts=HERE, tag=tag)
        p = os.path.join(outdir, "EMOTION_PROMPT_%s.md" % tag)
        io.open(p, "w", encoding="utf-8", newline="\n").write(txt)
        made.append((p, frag, grp))
    if not quiet:
        print("情绪提示词 %d 份(每批 %d 个 rank)" % (len(made), per))
        for p, frag, grp in made:
            print("   %s  ← ranks %s → %s" % (p, grp, frag))
    return made


def build_style(root, date, rows, per, quiet=False):
    """书写逻辑提取提示词(按批, 只提"怎么写"不提"写了什么")。"""
    tpl = io.open(STYLE_TPL, encoding="utf-8-sig").read()
    ranks = [r["rank"] for r in rows if isinstance(r["rank"], int)]
    outdir = os.path.join(root, "ext_search", date, "style")
    os.makedirs(outdir, exist_ok=True)
    made = []
    for i in range(0, len(ranks), per):
        grp = ranks[i:i + per]
        tag = "%02d" % (i // per + 1)
        frag = os.path.join(outdir, contract.STYLE_POOL_FMT % tag)
        txt = tpl.format(py=PY, root=root, date=date, ranks=",".join(str(x) for x in grp),
                         out=frag, tag=tag, platform=PLATFORM, unit=UNIT,
                         platform_notes=PLATFORM_NOTES)
        p = os.path.join(outdir, "STYLE_PROMPT_%s.md" % tag)
        io.open(p, "w", encoding="utf-8", newline="\n").write(txt)
        made.append((p, frag, grp))
    if not quiet:
        print("书写逻辑提示词 %d 份(每批 %d 个 rank)" % (len(made), per))
        for p, frag, grp in made:
            print("   %s  ← ranks %s → %s" % (p, grp, frag))
    return made


def build_write(root, date, rows, quiet=False):
    """回答书写提示词(每个 rank 一份, 指向汇编好的书写 skill)。"""
    tpl = io.open(WRITE_TPL, encoding="utf-8-sig").read()
    made = []
    for r in rows:
        rk = r["rank"]
        if not isinstance(rk, int):
            continue
        d = os.path.join(root, "ext_search", date, "rank_%d" % rk)
        os.makedirs(d, exist_ok=True)
        txt = tpl.format(py=PY, root=root, date=date, rank=rk,
                         styledir=contract.STYLE_DIR, stylefile=contract.STYLE_FILE,
                         platform=PLATFORM, unit=UNIT, platform_notes=PLATFORM_NOTES)
        p = os.path.join(d, "WRITE_PROMPT.md")
        io.open(p, "w", encoding="utf-8", newline="\n").write(txt)
        made.append(p)
    if not quiet:
        print("回答书写提示词 %d 份" % len(made))
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--ranks", default="1-20")
    ap.add_argument("--emotion", action="store_true", help="生成情绪判断提示词(按批)")
    ap.add_argument("--style", action="store_true", help="生成书写逻辑提取提示词(按批)")
    ap.add_argument("--write", action="store_true", help="生成回答书写提示词(每 rank)")
    ap.add_argument("--per", type=int, default=5, help="批次每份包含几个 rank(默认 5)")
    ap.add_argument("--all", action="store_true",
                    help="生成拓展+情绪+书写逻辑+回答书写 四种提示词")
    args = ap.parse_args()

    with io.open(contract.path_answers(args.root, args.date), encoding="utf-8-sig") as f:
        summary = json.load(f)
    want = set(parse_ranks(args.ranks))
    rows = [s for s in summary if s["rank"] in want]
    if not rows:
        sys.exit("[FAIL] 指定 rank 不在 answers_summary.json 里: %s" % sorted(want))

    if args.emotion or args.all:
        build_emotion(args.root, args.date, rows, args.per)
    if args.style or args.all:
        build_style(args.root, args.date, rows, args.per)
    if args.write or args.all:
        build_write(args.root, args.date, rows)
    if not args.emotion and not args.style and not args.write:
        build_swarm(args.root, args.date, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
