# -*- coding: utf-8 -*-
"""为热榜 rank 生成 subagent 提示词(取代一次性临时脚本)。

用法:
  # 拓展提示词(每个 rank 一份 PROMPT.md)
  python gen_prompts.py --root <ROOT> --date D --ranks 1-20
  # 复合提示词(情绪标注 + 书写逻辑提取, 一次读两份产出; 推荐)
  python gen_prompts.py --root <ROOT> --date D --ranks 1-20 --combo --per 5
  # 只跑其中一路(补跑/单独重跑时用)
  python gen_prompts.py --root <ROOT> --date D --ranks 1-20 --emotion --per 5
  python gen_prompts.py --root <ROOT> --date D --ranks 1-20 --style --per 5
  # 前置判断提示词(时政 + 增量 → publish_verdicts.json; 一份, 覆盖全部 rank)
  python gen_prompts.py --root <ROOT> --date D --gate
  # 写稿提示词(默认只给过闸 rank 写, 上限 = 每日待发帖上限; 省略 --ranks 即走闸门结果)
  python gen_prompts.py --root <ROOT> --date D --write [--top N] [--ranks 3,7]

产出位置(与 rank 的工作目录约定一致, 见 SKILL.md):
  <root>/ext_search/<D>/rank_<n>/PROMPT.md
  <root>/ext_search/<D>/combo/COMBO_PROMPT_<tag>.md
  <root>/ext_search/<D>/emotion/EMOTION_PROMPT_<tag>.md
  <root>/ext_search/<D>/style/STYLE_PROMPT_<tag>.md
  <root>/ext_search/<D>/gate/GATE_PROMPT.md
  <root>/ext_search/<D>/rank_<n>/WRITE_PROMPT.md
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract
import platform_profile as pf

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.environ.get("DSH_PYTHON") or sys.executable
# 平台注入项(2026-09-14: 取值收敛到 platform_profile.py 的单一档案,
# 这里只做"取出来传给模板"的动作; 环境变量覆盖由档案统一处理)
PLATFORM = pf.get("name")
UNIT = pf.get("unit")
PLATFORM_NOTES = pf.get("notes")
SOURCE_DB = pf.get("source_db")
SWARM_TPL = os.path.join(HERE, "prompt_swarm.md")
EMOTION_TPL = os.path.join(HERE, "prompt_emotion.md")
STYLE_TPL = os.path.join(HERE, "prompt_style.md")
WRITE_TPL = os.path.join(HERE, "prompt_write.md")
GATE_TPL = os.path.join(HERE, "prompt_gate.md")
GATE_PRE_TPL = os.path.join(HERE, "prompt_gate_pre.md")   # 阶段0 预闸门(检索前只判时政)


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
                         url=r["url"], scripts=HERE, cats=cats, platform=PLATFORM,
                         unit=UNIT, platform_notes=PLATFORM_NOTES, source_db=SOURCE_DB)
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
                         out=frag, scripts=HERE, tag=tag, platform=PLATFORM, unit=UNIT,
                         platform_notes=PLATFORM_NOTES, source_db=SOURCE_DB)
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


def build_combo(root, date, rows, per, quiet=False):
    """**复合子任务**(2026-09-14 成本实测后新增): 情绪标注 + 书写逻辑提取一次读、两份产出。

    为什么能合: 两件事读的是**同一批回答**, 彼此无依赖(都不需要对方的结果), 却各自要
    "把 5 个 rank 的回答读一遍"——纯重复。合并后同一批回答只读一次, 直接省掉一半读答成本。
    为什么**不能**把"写稿"(prompt_write)也塞进来: 写稿依赖**汇编好的书写 skill**(先提取→再汇编→后应用,
    见坑 68), 必须在 `merge_style` + 主编译之后才能派, 顺序上无法与提取同批。

    产出: <root>/ext_search/<D>/combo/COMBO_PROMPT_<tag>.md
    期望落盘: emotion/emotion_batch_<tag>.json 与 style/style_batch_<tag>.json(路径与分开跑时一致,
    因此 merge_emotion / merge_style 无需改动)。
    """
    etpl = io.open(EMOTION_TPL, encoding="utf-8-sig").read()
    stpl = io.open(STYLE_TPL, encoding="utf-8-sig").read()
    ranks = [r["rank"] for r in rows if isinstance(r["rank"], int)]
    emo_dir = os.path.join(root, "ext_search", date, "emotion")
    sty_dir = os.path.join(root, "ext_search", date, "style")
    combo_dir = os.path.join(root, "ext_search", date, "combo")
    for d in (emo_dir, sty_dir, combo_dir):
        os.makedirs(d, exist_ok=True)
    made = []
    for i in range(0, len(ranks), per):
        grp = ranks[i:i + per]
        tag = "%02d" % (i // per + 1)
        emo_frag = os.path.join(emo_dir, "emotion_batch_%s.json" % tag)
        sty_frag = os.path.join(sty_dir, contract.STYLE_POOL_FMT % tag)
        common = dict(py=PY, root=root, date=date, ranks=",".join(str(x) for x in grp),
                      scripts=HERE, tag=tag, platform=PLATFORM, unit=UNIT,
                      platform_notes=PLATFORM_NOTES, source_db=SOURCE_DB)
        body_a = etpl.format(out=emo_frag, **common)
        body_b = stpl.format(out=sty_frag, **common)
        head = (
            "# 复合子任务：情绪标注 + 书写逻辑提取（一次读、两份产出）\n\n"
            "本文件把**两个互不依赖**的读答任务合并到同一次阅读里，目的是**避免把同一批回答读两遍**。\n"
            "请先通读任务 A 与任务 B 的完整指令，再统一执行；**两份产出必须分别落盘**：\n"
            "- 任务 A 输出 → `%s`\n- 任务 B 输出 → `%s`\n\n"
            "纪律：两个任务的字段口径**互不借用**（情绪标签不得写进书写规律，书写规律不得写进情绪 why）；\n"
            "任何一个任务发现回答正文被截断/缺失，都要在产出里如实标注，不要凭猜测补齐。\n\n"
            "===================== 任务 A：情绪标注 =====================\n\n"
        ) % (emo_frag, sty_frag)
        mid = "\n\n===================== 任务 B：书写逻辑提取 =====================\n\n"
        p = os.path.join(combo_dir, "COMBO_PROMPT_%s.md" % tag)
        io.open(p, "w", encoding="utf-8", newline="\n").write(head + body_a + mid + body_b)
        made.append((p, emo_frag, sty_frag, grp))
    if not quiet:
        print("复合提示词 %d 份(每批 %d 个 rank: 情绪 + 书写提取)" % (len(made), per))
        for p, e, s, grp in made:
            print("   %s  ← ranks %s" % (p, grp))
            print("      → %s" % e)
            print("      → %s" % s)
    return made


def build_gate(root, date, rows, quiet=False):
    """前置判断提示词(**一份**, 覆盖全部指定 rank): 时政 + 增量两道闸门。

    脚本先把预计算信号表嵌进提示词(零 token), 判定 subagent 据此 + 读 chains/基线做语义判定,
    直接写 `raw/<D>/publish_verdicts.json`(判定权在判定端, `publish_queue.py` 之后做兜底复核)。
    """
    import publish_queue as pq     # 同目录; 只取其纯函数, 不触发任何写盘
    tpl = io.open(GATE_TPL, encoding="utf-8-sig").read()
    ranks = sorted(r["rank"] for r in rows if isinstance(r["rank"], int))
    sig = pq.compute_signals(root, date)
    lines = ["| rank | 标题 | 时政信号 | 命中词 | 基线 | 基线文档 | 链/证据 | 重合 max/min | 复述信号 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for rk in ranks:
        s = sig.get(rk)
        if not s:
            continue
        lines.append("| %d | %s | %s | %s | %s | %d | %d/%d | %s/%s | %s |" % (
            rk, s["title"][:24], "命中" if s["political_signal"] else "-",
            ",".join(s["political_hits"][:6]) or "-", s["baseline"], s["baseline_docs"],
            s["chains"], s["evidence"],
            s["overlap_max"] if s["overlap_max"] is not None else "-",
            s["overlap_min"] if s["overlap_min"] is not None else "-",
            "疑似复述" if s["repeat_hint"] else "-"))
    outdir = contract.gate_dir(root, date)
    os.makedirs(outdir, exist_ok=True)
    out = contract.path_verdicts(root, date)
    txt = tpl.format(py=PY, root=root, date=date, out=out, platform=PLATFORM, unit=UNIT,
                     max_per_day=contract.PUBLISH_MAX_PER_DAY,
                     repeat_jaccard=contract.GATE_REPEAT_JACCARD,
                     signals_table="\n".join(lines))
    p = os.path.join(outdir, "GATE_PROMPT.md")
    io.open(p, "w", encoding="utf-8", newline="\n").write(txt)
    if not quiet:
        print("前置判断提示词 1 份(覆盖 %d 个 rank) → %s" % (len(ranks), p))
        print("   判定产出 → %s" % out)
    return [p]


def build_gate_pre(root, date, rows, quiet=False):
    """阶段0 预闸门提示词(2026-09-21 起, 一份覆盖全部 rank): 检索**前**只判时政。

    信号表需要 extension.json(还没生成), 所以这里不嵌信号表 —— 判定只看题目与回答区。
    产出 publish_verdicts_pre.json, 供 build_swarm 默认模式过滤派发名单(宁多搜不误杀)。
    """
    ranks = sorted(r["rank"] for r in rows if isinstance(r["rank"], int))
    lines = ["| rank | 标题 | 问题摘要(前 60 字) | 最高赞 |", "|---|---|---|---|"]
    for r in rows:
        if not isinstance(r.get("rank"), int):
            continue
        top = max([int(a.get("likes") or 0) for a in r.get("answers", [])] or [0])
        lines.append("| %d | %s | %s | %s |" % (
            r["rank"], (r.get("title") or "")[:40], (r.get("summary") or "")[:60], top))
    outdir = contract.gate_dir(root, date)
    os.makedirs(outdir, exist_ok=True)
    out = contract.path_verdicts_pre(root, date)
    tpl = io.open(GATE_PRE_TPL, encoding="utf-8-sig").read()
    txt = tpl.format(py=PY, root=root, date=date, out=out, platform=PLATFORM,
                     max_per_day=contract.PUBLISH_MAX_PER_DAY,
                     ranks_table="\n".join(lines))
    p = os.path.join(outdir, "GATE_PROMPT_PRE.md")
    io.open(p, "w", encoding="utf-8", newline="\n").write(txt)
    if not quiet:
        print("阶段0 预闸门提示词 1 份(覆盖 %d 个 rank) → %s" % (len(ranks), p))
        print("   判定产出 → %s" % out)
    return [p]


def gated_ranks(root, date, cap=None):
    """从判定结果里取过闸(时政+增量)的 rank, 升序; cap=None = 全部过闸 rank。

    2026-09-21 起(用户指令): 过闸条目**全部写稿**, 排序与「建议只发 3 条」由
    publish_queue.py 的推荐/备选机制裁决 —— 写稿不再按上限预裁剪,
    备选稿同样进待发帖列与 HTML 供人工挑选。
    """
    import publish_queue as pq
    vs = pq.load_verdicts(root, date)
    gated = sorted(v["rank"] for v in vs
                   if v.get("is_political") is True and v.get("has_increment") is True)
    return gated[:max(int(cap), 0)] if cap is not None else gated


def pregated_ranks(root, date, rows):
    """阶段0 预闸门名单: publish_verdicts_pre.json 里 is_political=true 的 rank(升序)。

    pre 文件缺失 = 没跑预闸门 → 返回全部 rank(行为与旧版一致, 宁多搜不误杀)。
    2026-09-21 起 swarm 派发默认只搜这份名单(省约 70-80% 检索), 显式 --ranks 可覆盖。
    """
    try:
        with io.open(contract.path_verdicts_pre(root, date), encoding="utf-8-sig") as f:
            vs = json.load(f)
    except Exception:
        return sorted(r["rank"] for r in rows if isinstance(r.get("rank"), int))
    return sorted(int(v["rank"]) for v in vs
                  if isinstance(v.get("rank"), int) and v.get("is_political") is True)


def build_write(root, date, rows, quiet=False, top=None):
    """发帖短评书写提示词(每个 rank 一份, 指向汇编好的书写 skill)。

    `top`: 传 N 则只给前 N 个过闸 rank 出稿(None = 全部过闸); rows 已由调用方按闸门结果裁剪。
    2026-09-16 起: 稿体 = 50–100 字犀利短评; 2026-09-21 起默认全部过闸都写(推荐/备选由队列裁决)。
    """
    tpl = io.open(WRITE_TPL, encoding="utf-8-sig").read()
    made, skipped, cleaned = [], [], []
    for r in rows:
        rk = r["rank"]
        if not isinstance(rk, int):
            continue
        if top and rk > top:
            skipped.append(rk)
            # 清掉历史遗留的 WRITE_PROMPT.md:留着会让人误以为"这条也该写稿"
            stale = os.path.join(root, "ext_search", date, "rank_%d" % rk, "WRITE_PROMPT.md")
            if os.path.exists(stale):
                os.remove(stale)
                cleaned.append(rk)
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
        print("发帖短评书写提示词 %d 份%s%s" % (
            len(made),
            ("（跳过 rank %s：超过 --top 写稿上限 %d）" % (skipped, top)) if skipped else "",
            ("（已清理 %s 的历史 WRITE_PROMPT.md）" % cleaned) if cleaned else ""))
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--ranks", default=None,
                    help="rank 范围(默认 1-20; --write 模式省略 = 只给过闸 rank 写)")
    ap.add_argument("--combo", action="store_true",
                    help="生成复合提示词(情绪标注 + 书写逻辑提取, 一次读两份产出)——默认推荐方式")
    ap.add_argument("--emotion", action="store_true", help="只生成情绪判断提示词(按批)")
    ap.add_argument("--style", action="store_true", help="只生成书写逻辑提取提示词(按批)")
    ap.add_argument("--gate", action="store_true",
                    help="生成前置判断提示词(时政 + 增量判定 → publish_verdicts.json)")
    ap.add_argument("--stage0", action="store_true",
                    help="与 --gate 同用: 生成**阶段0 预闸门**提示词(检索前只判时政 → "
                         "publish_verdicts_pre.json), 供 swarm 只搜过预闸的 rank")
    ap.add_argument("--write", action="store_true", help="生成发帖短评书写提示词(每 rank)")
    ap.add_argument("--per", type=int, default=5, help="批次每份包含几个 rank(默认 5)")
    ap.add_argument("--top", type=int, default=None,
                    help="写稿条数上限(2026-09-21 起默认不限: 全部过闸 rank 都写;"
                         "传 N = 只给前 N 个过闸 rank 写, 恢复旧的按上限裁剪)")
    ap.add_argument("--all", action="store_true",
                    help="生成 拓展 + 复合(情绪+书写提取) + 前置判断 + 发帖短评 四类提示词")
    args = ap.parse_args()

    with io.open(contract.path_answers(args.root, args.date), encoding="utf-8-sig") as f:
        summary = json.load(f)
    ranks_explicit = args.ranks is not None
    want = set(parse_ranks(args.ranks or "1-20"))
    rows = [s for s in summary if s["rank"] in want]
    if not rows:
        sys.exit("[FAIL] 指定 rank 不在 answers_summary.json 里: %s" % sorted(want))

    top = args.top or None
    did = False
    if args.emotion:
        build_emotion(args.root, args.date, rows, args.per); did = True
    if args.style:
        build_style(args.root, args.date, rows, args.per); did = True
    if args.combo or args.all:
        build_combo(args.root, args.date, rows, args.per); did = True
    if args.gate and args.stage0:
        build_gate_pre(args.root, args.date, rows); did = True
    elif args.gate or args.all:
        build_gate(args.root, args.date, rows); did = True
    if args.write or args.all:
        wrows = rows
        if not ranks_explicit:
            # 省略 --ranks = 走闸门结果: **全部过闸 rank** 都写稿(2026-09-21 起,
            # 推荐位/备选由 publish_queue 排序裁决; --top N 可显式回到按上限裁剪)
            g = set(gated_ranks(args.root, args.date, top))
            wrows = [s for s in summary if s["rank"] in g]
            if not wrows:
                print("[WARN] 判定结果里没有过闸 rank(publish_verdicts.json 缺失或两关全否) — "
                      "不生成写稿提示词; 先跑 --gate 判定。")
        build_write(args.root, args.date, wrows, top=top); did = True
    if not did:
        srows = rows
        if not ranks_explicit:
            # 2026-09-21 起: 阶段0 预闸门在检索前挡掉明显非时政的 rank ——
            # swarm 默认只派发过预闸名单; 显式 --ranks 可全量(宁多搜不误杀的原则在预闸门端执行)
            pre = pregated_ranks(args.root, args.date, rows)
            all_ranks = sorted(r["rank"] for r in rows if isinstance(r.get("rank"), int))
            if pre != all_ranks:
                srows = [r for r in rows if r.get("rank") in set(pre)]
                print("[预闸门] 过闸 rank: %s(已挡在检索外: %s; 显式 --ranks 可全量)"
                      % (pre, sorted(set(all_ranks) - set(pre))))
        build_swarm(args.root, args.date, srows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
