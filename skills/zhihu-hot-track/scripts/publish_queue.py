# -*- coding: utf-8 -*-
"""前置判断 + 待发帖列(2026-09-16 新增; 同日**删除自动发帖三件套**)。

背景
----
自动发帖(publish_draft.py / publish_batch.py / make_manual_publish.py)已按用户要求整体删除
("目前来说收益太少")。流程不再驱动浏览器点击发布, 只产出**待发帖列**, 由人复制粘贴发布后回填。

三道闸门(顺序即优先级; 判定权在判定 subagent / 主 Agent, 本脚本只做兜底复核 —— 与信源门槛同一纪律):
  ① 是否时政 —— 非时政不进列(只出稿);
  ② 时政: swarm 发散是否拿到**评论区(或回答区)没有的增量信息** —— 只是复述已有观点则不进列;
  ③ 过①②者写 50–100 字短评, 再查**言语中庸** —— 命中黑名单即打回重写。
每日最多 contract.PUBLISH_MAX_PER_DAY(=3) 条入列, **可以少、不可以多**。
2026-09-21 起: 过闸条目**全部写稿**, 有效稿按 获赞性×情绪 排序 —— 推荐位=预算内,
其余=over_daily_cap(**备选**: 稿照常进待发帖列与 HTML, 人工终审可换发备选, --mark 同样回填)。

用法
----
  python publish_queue.py --root R --date D              # 汇总判定 → 闸门 → 排序 → 待发帖列
  python publish_queue.py --root R --date D --signal     # 只打印预计算信号(JSON), 判定 subagent 的输入
  python publish_queue.py --root R --date D --status     # 只看队列
  python publish_queue.py --root R --date D --mark "1=<answer url>"   # 人工发布后回填(校验链接归属)
  python publish_queue.py --root R --date D --sharp "3=false:依据"     # 犀利度复核回填(可重复), 随后自动重跑汇总
"""
import argparse
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract
import platform_profile as pf   # noqa: F401  平台文案(入口名/无标题说明)只从档案取, 不写死

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 文本重合度(增量信号, 零 token) ──────────────────────────────────────────

_PUNCT_RE = re.compile(r"[\s，。；：、！？“”‘’（）《》〈〉…—·\-.,;:!?\[\](){}\"']+")


def _shingles(text, n=3):
    """中文 3-gram 集合(去标点空白)。与 topic_lib 同思路的独立小实现, 避免拉入 sqlite 依赖。"""
    s = _PUNCT_RE.sub("", text or "")
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with io.open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


# ── 信号预计算 ──────────────────────────────────────────────────────────────

def compute_signals(root, date):
    """为每个 rank 预计算闸门信号(零 token; 判定 subagent 的输入之一, --signal 可直接查看)。

    baseline: raw/<D>/comments.json 存在则用评论区正文当基线, 否则**降级为回答区正文**
    (与 fulltext 的降级哲学一致); 用的是哪一种必须写进结果, 供判定与交付物标注。
    """
    answers = _load_json(contract.path_answers(root, date), [])
    ext = _load_json(contract.path_extension(root, date), {})
    comments = _load_json(contract.path_comments(root, date), None)
    if not isinstance(comments, dict):
        comments = None
    baseline_kind = "comments" if comments else "answers"
    sig = {}
    for s in answers:
        rk = s.get("rank")
        if not isinstance(rk, int):
            continue
        title = s.get("title") or ""
        hits = sorted({w for w in contract.POLITICAL_HINTS if w in title})
        cat_hit = [c for c in contract.POLITICAL_CATS if c in title]
        if comments:
            pool = [c.get("text") or "" for c in (comments.get(str(rk)) or [])]
        else:
            pool = [a.get("text") or "" for a in s.get("answers", [])]
        pool = [t for t in pool if t]
        pools = [_shingles(t) for t in pool]
        e = ext.get(str(rk)) or {}
        evid = [ev.get("content") or ""
                for ch in e.get("chains", []) for ev in ch.get("evidence", [])]
        ov = [max((_jaccard(_shingles(t), p) for p in pools), default=0.0) for t in evid]
        sig[rk] = {
            "rank": rk,
            "title": title,
            "political_hits": hits,
            "political_cat_hit": cat_hit,
            "political_signal": bool(cat_hit or len(hits) >= 2),
            "baseline": baseline_kind,
            "baseline_docs": len(pool),
            "chains": len(e.get("chains", [])),
            "evidence": len(evid),
            # overlap_max = 最"像复述"的证据重合度; overlap_min = 最"新"的证据重合度
            "overlap_max": round(max(ov), 3) if ov else None,
            "overlap_min": round(min(ov), 3) if ov else None,
            "repeat_hint": bool(ov) and min(ov) >= contract.GATE_REPEAT_JACCARD,
        }
    return sig


# ── 判定汇总与闸门 ──────────────────────────────────────────────────────────

def load_verdicts(root, date):
    return _load_json(contract.path_verdicts(root, date), [])


def _answer_intensity(a):
    """单条回答的情绪强度: 新模型 emotion_intensity, 兼容 legacy emotion.intensity。"""
    v = a.get("emotion_intensity")
    if isinstance(v, (int, float)):
        return int(v)
    e = a.get("emotion")
    if isinstance(e, dict):
        v = e.get("intensity")
        if isinstance(v, (int, float)):
            return int(v)
    return 0


def _draft_parts(path):
    """返回 (标题, 正文) — 首行 `# 标题` 不计入正文字数。"""
    raw = io.open(path, encoding="utf-8-sig").read().strip()
    lines = raw.splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].lstrip().startswith("#") else ""
    return title, "\n".join(lines[1:] if title else lines).strip()


def evaluate(root, date):
    """汇总判定 → 闸门 → 队列条目。返回 (items, problems); 不落盘。"""
    answers = {s.get("rank"): s for s in _load_json(contract.path_answers(root, date), [])
               if isinstance(s.get("rank"), int)}
    sig = compute_signals(root, date)
    verdicts, problems = {}, []
    for v in load_verdicts(root, date):
        rk = v.get("rank")
        if not isinstance(rk, int):
            problems.append("判定缺整数 rank: %r" % (rk,))
            continue
        if rk not in sig:
            problems.append("判定 rank %d 不在当日数据里" % rk)
            continue
        missing = [k for k in contract.VERDICT_REQUIRED if v.get(k) in (None, "")]
        if missing:
            problems.append("rank %d 判定缺字段: %s" % (rk, ",".join(missing)))
            continue
        if not isinstance(v.get("is_political"), bool) or not isinstance(v.get("has_increment"), bool):
            problems.append("rank %d is_political/has_increment 必须是布尔" % rk)
            continue
        if v.get("baseline") not in contract.VERDICT_BASELINES:
            problems.append("rank %d baseline 必须是 %s" % (rk, "/".join(contract.VERDICT_BASELINES)))
            continue
        verdicts[rk] = v
    queue = _load_json(contract.path_queue(root, date), {"date": date, "items": {}})
    items = queue.setdefault("items", {})
    gated = []
    for rk in sorted(sig):
        s, v = sig[rk], verdicts.get(rk)
        prev = items.get(str(rk), {})
        if prev.get("state") == "published":        # 人工回填的事实, 重跑不重判
            items[str(rk)] = dict(prev, title=s["title"], url=answers.get(rk, {}).get("url", ""))
            continue
        it = {"rank": rk, "title": s["title"], "url": answers.get(rk, {}).get("url", ""),
              "baseline": s["baseline"], "political_signal": s["political_signal"],
              "political_hits": s["political_hits"]}
        if v is None:
            it["state"] = "verdict_missing"
            items[str(rk)] = it
            continue
        it["why"] = v.get("why")
        it["political_basis"] = v.get("political_basis")
        it["increment_basis"] = v.get("increment_basis")
        # 分歧复核: 判定端说非时政, 脚本信号却命中 → 交主 Agent 复核(不硬拦, 判定权在判定端)
        if not v["is_political"] and s["political_signal"]:
            it["disagree"] = "判定=非时政, 但脚本信号命中(%s|%s) — 请复核" % (
                ",".join(s["political_cat_hit"]) or "-",
                ",".join(s["political_hits"][:6]) or "-")
        if not v["is_political"]:
            it["state"] = "skip_not_political"
        elif not v["has_increment"]:
            it["state"] = "skip_no_increment"
        else:
            gated.append((rk, it))
            continue
        items[str(rk)] = it
    # 每日上限与推荐排序(2026-09-21 起): 过闸条目**全部写稿**; 有效稿(过机检+犀利复核)按
    # 获赞性×情绪 排序 —— 情绪强度(analysis 最大值)降序 → 回答区最高赞降序 → rank 升序 ——
    # 前(上限−已发布)条 ready(推荐), 其余 over_daily_cap(备选: 稿照常展示, 人工终审可换,
    # 发布后同样 --mark 回填)。无稿/打回的过闸条目照常标 draft_pending/打回态。
    n_pub = sum(1 for it in items.values() if it.get("state") == "published")
    budget = max(contract.PUBLISH_MAX_PER_DAY - n_pub, 0)
    analysis = {}
    try:
        raw_analysis = _load_json(contract.path_analysis(root, date), None)
        pairs = (raw_analysis.items() if isinstance(raw_analysis, dict)
                 else [(a.get("rank"), a) for a in raw_analysis]
                 if isinstance(raw_analysis, list) else [])
        for k, a in pairs:
            try:
                analysis[int(k)] = a          # dict 键为 str(rank) / list 项自带 rank
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    valid = []
    for rk, it in gated:
        draft = contract.path_draft(root, date, rk)
        if not os.path.exists(draft):
            it["state"] = "draft_pending"
            items[str(rk)] = it
            continue
        _, body = _draft_parts(draft)
        n = len(re.sub(r"\s", "", body))
        lo, hi = contract.DRAFT_LEN
        hit = next((p for p in contract.MEDIOCRE_PATTERNS if re.search(p, body)), None)
        it["len"] = n
        if not (lo <= n <= hi):
            it["state"] = "len_out_of_range"
            it["reason"] = "正文 %d 字, 要求 %d–%d" % (n, lo, hi)
        elif hit:
            it["state"] = "mediocre"
            it["reason"] = "命中中庸句式: /%s/" % hit
        elif verdicts[rk].get("mediocre") is True:
            it["state"] = "mediocre"
            it["reason"] = "犀利度复核判定中庸: %s" % verdicts[rk].get("sharpness_why", "")
        elif verdicts[rk].get("mediocre") is None:
            it["state"] = "sharpness_unjudged"
        else:
            it["emotion_top"] = max([_answer_intensity(a)
                                     for a in analysis.get(rk, {}).get("answers", [])] or [0])
            it["top_like"] = max([int(a.get("likes") or 0)
                                  for a in answers.get(rk, {}).get("answers", [])] or [0])
            valid.append((rk, it))
            continue
        items[str(rk)] = it
    valid.sort(key=lambda t: (-t[1]["emotion_top"], -t[1]["top_like"], t[0]))
    for i, (rk, it) in enumerate(valid):
        it["priority"] = i + 1
        it["state"] = "ready" if i < budget else "over_daily_cap"
        items[str(rk)] = it
    return items, problems


# ── 渲染与落盘 ──────────────────────────────────────────────────────────────

def _save_queue(root, date, queue):
    p = contract.path_queue(root, date)
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(queue, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)          # 原子替换: 写一半崩掉不毁队列(与 topic_lib 同款)


def _save_verdicts(root, date, verdicts):
    """判定文件原子回写(与 _save_queue 同款), 供 --sharp 犀利度复核回填。"""
    p = contract.path_verdicts(root, date)
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(verdicts, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def render_md(root, date, items):
    """人读待发帖清单: 推荐+备选全文逐条可复制; 平台事实(入口名/无标题说明)全部取自档案。"""
    entry = pf.get("publish_editor_entry")
    no_title = pf.get("publish_no_title")
    ready = [it for it in items.values() if it.get("state") == "ready"]
    backup = [it for it in items.values() if it.get("state") == "over_daily_cap"]
    published = [it for it in items.values() if it.get("state") == "published"]
    out = ["# 待发帖列(%s)— 推荐 %d 条(每日上限 %d, 可以少不可以多)+ 备选 %d 条"
           % (date, len(ready), contract.PUBLISH_MAX_PER_DAY, len(backup)), "",
           "自动发帖已删除(收益太少), 本清单是唯一待发入口。排序(2026-09-21):"
           "情绪强度 → 回答区最高赞; 推荐位=预算内, 备选=超预算 —— **人工终审可换**:"
           "想发备选就直接发它并回填, 与推荐条目同等待遇。操作:点「%s」→ 粘贴正文 → 发布后回填:"
           % (entry or "写回答"), "",
           "  python scripts/publish_queue.py --root <ROOT> --date %s --mark \"<rank>=<回答链接>\"" % date,
           "", no_title or "", ""]
    def _entry(it, label):
        rk = it["rank"]
        dp = contract.path_draft(root, date, rk)
        title, body = _draft_parts(dp) if os.path.exists(dp) else ("", "")
        return ["---", "",
                "## %s · rank %d · %s" % (label, rk, it["title"]),
                "",
                "问题链接:%s" % it["url"],
                "标题(参考, 不发):%s" % title,
                "短评(%d 字):" % it.get("len", len(re.sub(r"\s", "", body))),
                "", "```text", body, "```", "",
                "入列依据:%s" % it.get("why", ""),
                "增量:%s" % it.get("increment_basis", ""),
                "基线:%s(评论区/回答区里没有的新东西)" % it.get("baseline", ""),
                ""]
    for it in sorted(ready, key=lambda x: x.get("priority", 999)):
        out += _entry(it, "推荐 #%d" % it.get("priority", 0))
    if backup:
        for it in sorted(backup, key=lambda x: x.get("priority", 999)):
            out += _entry(it, "备选 #%d(超今日建议上限)" % it.get("priority", 0))
    if published:
        out += ["---", "", "## 今日已发布(%d 条)" % len(published), ""]
        for it in sorted(published, key=lambda x: x["rank"]):
            out.append("- rank %d %s → %s" % (it["rank"], it["title"], it.get("answer_url", "")))
        out.append("")
    return "\n".join(out)


def _show(items):
    buckets = {}
    for it in items.values():
        buckets.setdefault(it.get("state", "?"), []).append(int(it.get("rank", 0)))
    for st in contract.QUEUE_STATES:
        if st in buckets:
            print("%-18s %s" % (st, sorted(buckets[st])))
    for st in sorted(buckets):
        if st not in contract.QUEUE_STATES:
            print("%-18s %s  (未知状态)" % (st, sorted(buckets[st])))


def main():
    ap = argparse.ArgumentParser(description="前置判断 + 待发帖列(自动发帖已删除)")
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--signal", action="store_true", help="只打印预计算信号(JSON), 不落盘")
    ap.add_argument("--status", action="store_true", help="只打印队列")
    ap.add_argument("--mark", action="append", default=[], help="人工发布后回填: N=<answer url>")
    ap.add_argument("--sharp", action="append", default=[],
                    help="犀利度复核回填: N=<true|false>:<依据> (true=判中庸打回); "
                         "可重复传; 回填后本命令继续重跑闸门汇总与渲染")
    args = ap.parse_args()

    if args.signal:
        print(json.dumps(list(compute_signals(args.root, args.date).values()),
                         ensure_ascii=False, indent=1))
        return 0

    if args.mark:
        queue = _load_json(contract.path_queue(args.root, args.date),
                           {"date": args.date, "items": {}})
        items = queue.setdefault("items", {})
        # 归属校验(2026-09-21 起): 发布的回答必须挂在该 rank 对应的问题下, 防贴错行
        answers = {s.get("rank"): s for s in _load_json(contract.path_answers(args.root, args.date), [])
                   if isinstance(s.get("rank"), int)}
        for kv in args.mark:
            k, _, u = kv.partition("=")
            rk = str(int(k))
            u = u.strip()
            m_new = re.search(r"/question/(\d+)", u)
            if not m_new or "/answer/" not in u:
                sys.exit('[FAIL] --mark 链接须形如 question/<qid>/answer/<aid>(站点域名从档案取, 不写死): %r' % u)
            m_src = re.search(r"/question/(\d+)", answers.get(int(rk), {}).get("url", "") or "")
            if m_src and m_new.group(1) != m_src.group(1):
                sys.exit("[FAIL] rank %s 的问题应是 question/%s, 回填链接却挂在 question/%s —— 贴错行了?"
                         % (rk, m_src.group(1), m_new.group(1)))
            it = items.setdefault(rk, {"rank": int(rk)})
            it["state"] = "published"
            it["answer_url"] = u
            it["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save_queue(args.root, args.date, queue)
        io.open(contract.queue_md_path(args.root, args.date), "w", encoding="utf-8", newline="\n") \
            .write(render_md(args.root, args.date, items))
        print("已回填 %d 条已发布" % len(args.mark))
        _show(items)
        return 0

    if args.status:
        queue = _load_json(contract.path_queue(args.root, args.date),
                           {"date": args.date, "items": {}})
        _show(queue.get("items", {}))
        return 0

    if args.sharp:
        vs = _load_json(contract.path_verdicts(args.root, args.date), None)
        if not vs:
            sys.exit("[FAIL] publish_verdicts.json 缺失 —— 先跑阶段1 判定再回填犀利度")
        idx = {int(v.get("rank")): v for v in vs if isinstance(v.get("rank"), int)}
        for kv in args.sharp:
            rk_s, _, rest = kv.partition("=")
            truth, _, why = rest.partition(":")
            try:
                rk = int(rk_s)
            except ValueError:
                sys.exit("[FAIL] --sharp rank 必须是整数: %r" % kv)
            if rk not in idx:
                sys.exit("[FAIL] publish_verdicts.json 里没有 rank %d" % rk)
            t = truth.strip().lower()
            if t not in ("true", "false"):
                sys.exit('[FAIL] --sharp 布尔须为 true/false(true=判中庸打回): %r' % kv)
            idx[rk]["mediocre"] = (t == "true")
            idx[rk]["sharpness_why"] = why.strip()
            print("[sharp] rank %d → mediocre=%s (%s)" % (rk, t, why.strip()[:60] or "-"))
        _save_verdicts(args.root, args.date, vs)

    items, problems = evaluate(args.root, args.date)
    queue = {"date": args.date, "max_per_day": contract.PUBLISH_MAX_PER_DAY,
             "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "items": items}
    _save_queue(args.root, args.date, queue)
    io.open(contract.queue_md_path(args.root, args.date), "w", encoding="utf-8", newline="\n") \
        .write(render_md(args.root, args.date, items))
    for p in problems:
        print("[WARN] %s" % p)
    dis = [it for it in items.values() if it.get("disagree")]
    if dis:
        print("[分歧复核] %d 条判定与脚本信号相反, 请主 Agent 逐条复核:" % len(dis))
        for it in dis:
            print("  rank %d: %s" % (it["rank"], it["disagree"]))
    _show(items)
    ready = [it for it in items.values() if it.get("state") == "ready"]
    backup = [it for it in items.values() if it.get("state") == "over_daily_cap"]
    print("待发帖列: %s (推荐 %d/%d + 备选 %d)"
          % (contract.queue_md_path(args.root, args.date), len(ready),
             contract.PUBLISH_MAX_PER_DAY, len(backup)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
