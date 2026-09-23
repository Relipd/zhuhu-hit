# -*- coding: utf-8 -*-
"""热榜跟进 - 分页式 HTML 生成(索引页 + 每问题一页 + 翻页导航)。

结构:
  <root>/<报告前缀>-<date>.html          根入口(自动跳转)
  <root>/<报告前缀>-<date>/index.html   索引页: 4×5自适应网格卡片, 点击进入详情
  <root>/<报告前缀>-<date>/q01..q20.html 详情页: 每问题一页, 回答折叠扩展, 上一题/下一题翻页

用法: python gen_html.py --root <工作根目录> --date 2026-08-08 [--out <输出根文件>]
"""
import argparse, html, io, json, os, re

import contract   # 数据契约:文件名 / 字段 / 值域的单一定义处(见 contract.py)
import platform_profile as pf   # L2 平台档案:交付物文案(平台名/来源说明)的取值处

JUDGE_CLS = contract.EMOTION_CSS_CLASS   # 情绪 -> 配色 class(与 verify_html 共用同一值域)
CSS = """
:root {
  --ink: #1f3a5f; --paper: #f5f3ee; --card: #ffffff; --line: #e8e4da;
  --gold: #b08d2e; --gold-bg: #faf6ea; --muted: #7c7a72;
  --pos: #2f7d4f; --neu: #8a8a8a; --neg: #c0493a;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  background: var(--paper); margin: 0; color: #23241f; line-height: 1.6; }
header { background: linear-gradient(135deg, #16283f, #1f3a5f); color: #fff;
  padding: 22px 40px 18px; }
header h1 { margin: 0; font-size: 23px; letter-spacing: .5px; }
header p { margin: 5px 0 0; opacity: .8; font-size: 13px; }
.stats { display: flex; gap: 28px; margin-top: 12px; font-size: 13.5px; align-items: center; flex-wrap: wrap; }
.stats b { font-size: 19px; margin-right: 4px; font-variant-numeric: tabular-nums; }
.ebar { display: flex; width: 220px; height: 8px; border-radius: 4px; overflow: hidden; background: rgba(255,255,255,.18); }
.ebar i { display: block; }
/* ---------- 索引页 ---------- */
main.idx { max-width: 1720px; margin: 20px auto; padding: 0 20px;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 14px; }
.card-link { text-decoration: none; color: inherit; background: var(--card);
  border: 1px solid var(--line); border-radius: 12px; padding: 14px 14px 12px;
  box-shadow: 0 1px 2px rgba(31,58,95,.05); transition: all .2s; position: relative; }
.card-link:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(31,58,95,.12);
  border-color: #c8c2b2; }
.card-top { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.rank { background: var(--ink); color: #fff; font-weight: 700; border-radius: 6px;
  padding: 2px 9px; font-size: 13px; font-variant-numeric: tabular-nums; }
.ext-tag { background: var(--gold); color: #fff; font-size: 10.5px; border-radius: 10px;
  padding: 1px 7px; font-weight: 700; }
.add-tag { background: #2f6f8f; color: #fff; font-size: 10.5px; border-radius: 10px;
  padding: 1px 7px; font-weight: 700; margin-left: 5px; }
.card-title { font-size: 14.5px; font-weight: 700; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  margin-bottom: 8px; }
.card-meta { display: flex; gap: 10px; font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.card-meta b { color: #555; font-variant-numeric: tabular-nums; }
.mbar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: #eee9dd; }
.mbar i { display: block; }
/* ---------- 详情页 ---------- */
.topbar { position: sticky; top: 0; z-index: 20; background: rgba(245,243,238,.95);
  backdrop-filter: blur(6px); border-bottom: 1px solid var(--line);
  display: flex; align-items: center; gap: 10px; padding: 9px 24px; font-size: 13px; }
.topbar a { color: var(--ink); text-decoration: none; padding: 2px 12px;
  border: 1px solid var(--line); background: var(--card); border-radius: 18px;
  transition: all .15s; }
.topbar a:hover { border-color: var(--ink); }
.topbar .spacer { flex: 1; }
.topbar .cur { color: var(--muted); font-size: 12px; }
main.detail { max-width: 900px; margin: 22px auto; padding: 0 24px; }
.q { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  box-shadow: 0 1px 3px rgba(31,58,95,.06); overflow: hidden; }
.q-head { display: flex; align-items: baseline; gap: 12px; padding: 18px 24px 12px;
  background: #f1f4f9; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.q-title { font-size: 19px; font-weight: 700; color: var(--ink); text-decoration: none; line-height: 1.5; }
.q-title:hover { text-decoration: underline; }
.badges { margin-left: auto; display: flex; gap: 8px; flex-shrink: 0; }
.badge { font-size: 12px; color: #555; background: #fff; border: 1px solid var(--line);
  border-radius: 12px; padding: 1px 9px; white-space: nowrap; }
.essence { padding: 12px 24px 14px; font-size: 14px; color: #4a463d; }
.essence b { color: var(--ink); }
.a { border-top: 1px dashed var(--line); }
.a summary { display: flex; align-items: baseline; gap: 10px; padding: 12px 24px;
  font-size: 14px; cursor: pointer; list-style: none; transition: background .15s; flex-wrap: wrap; }
.a summary::-webkit-details-marker { display: none; }
.a summary:hover { background: #faf9f5; }
.a summary::before { content: "▸"; color: var(--gold); font-size: 13px; transition: transform .2s; }
.a[open] summary::before { transform: rotate(90deg); }
.a-no { color: var(--ink); font-weight: 700; font-size: 13px; }
.a-author { color: var(--muted); font-size: 12.5px; }
.a-likes { color: #b45309; font-weight: 700; font-size: 13px; font-variant-numeric: tabular-nums; }
.judge { border-radius: 4px; padding: 0 9px; font-size: 12px; font-weight: 700; color: #fff; }
.pos { background: var(--pos); } .neu { background: var(--neu); } .neg { background: var(--neg); }
/* 多元化情绪(2026-09-13 起): 多标签 chips + 强度点 + 指向小签 */
.emo { border-radius: 4px; padding: 1px 8px; font-size: 11.5px; font-weight: 700; color: #fff;
  white-space: nowrap; }
.t-hot { background: #c0493a; } .t-cold { background: #5b7c99; } .t-warm { background: #2f7d4f; }
.t-up { background: #b08d2e; } .t-wry { background: #8a6f9e; } .t-dry { background: #8a8a8a; }
.emo-up { color: #b45309; font-size: 12px; letter-spacing: 1.5px; }
.emo-up i { font-style: normal; color: #ded8c8; }
.emo-tgt { color: var(--muted); font-size: 11.5px; border: 1px solid var(--line);
  border-radius: 4px; padding: 1px 6px; background: #fbfaf6; }
.legend { font-size: 12px; color: var(--muted); line-height: 1.9; }
.legend .emo, .legend .emo-tgt { margin-right: 3px; }
/* 发帖短评块: 与热点拓展的金色区分开, 用墨蓝纸感, 提示"这是给人改的短评" */
.draft { background: #f2f5f8; border-top: 2px solid #9fb3c8; padding: 14px 24px 18px; font-size: 13.5px; }
.draft .ext-head { color: #2c4a68; }
.draft .draft-title { font-weight: 700; font-size: 15px; color: #16283f; margin: 2px 0 9px; }
.draft p { margin: 0 0 9px; line-height: 1.85; color: #2f3a44; }

/* ---------- 索引页·今日短评挑选面板 ---------- */
.dpanel { background: #f2f5f8; border: 1px solid #9fb3c8; border-radius: 10px;
          padding: 12px 18px 8px; margin: 0 0 20px; }
.dpanel h2 { margin: 0 0 6px; font-size: 14.5px; color: #16283f; }
.dpanel .drow { display: flex; gap: 10px; align-items: baseline; padding: 7px 0;
                border-top: 1px dashed #c3d0dd; font-size: 13px; flex-wrap: wrap; }
.dpanel .drow:first-of-type { border-top: none; }
.dpanel .dbadge { flex: 0 0 auto; font-size: 12px; font-weight: 700; color: #fff;
                  background: #2c4a68; border-radius: 4px; padding: 2px 8px; }
.dpanel .dbadge.alt { background: #8a6d3b; }
.dpanel .drank { flex: 0 0 auto; color: #5b6b7c; font-weight: 700; }
.dpanel a.dlink { color: #16283f; font-weight: 600; text-decoration: none; }
.dpanel a.dlink:hover { text-decoration: underline; }
.dpanel .dsnip { color: #5b6b7c; flex: 1 1 220px; min-width: 0;
                 overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dpanel .dlen { flex: 0 0 auto; color: #8a97a5; font-size: 12px; }
.a-stance { color: var(--muted); font-size: 13px; flex: 1; min-width: 200px; }
.a-body { padding: 2px 24px 16px; }
table.analysis { width: 100%; border-collapse: collapse; font-size: 13px; margin: 6px 0 10px; }
table.analysis td { border: 1px solid #eee9dd; padding: 7px 11px; vertical-align: top; }
table.analysis td.k { background: #f7f5ee; color: var(--ink); font-weight: 700;
  white-space: nowrap; width: 76px; font-size: 12.5px; }
details.a-text { font-size: 13px; }
details.a-text summary { cursor: pointer; color: var(--gold); font-size: 12.5px; padding: 2px 0; }
details.a-text div { background: #fafaf7; border: 1px solid var(--line); border-radius: 8px;
  padding: 12px 14px; margin-top: 6px; white-space: pre-wrap; line-height: 1.7; color: #3a372f; }
.ext { background: var(--gold-bg); border-top: 2px solid #d9c68a; padding: 14px 24px 16px; font-size: 13.5px; }
.ext-head { font-weight: 700; color: #8a6d1a; margin-bottom: 9px; font-size: 14px; }
.ext-tierline { color: #6b5518; font-size: 12px; margin: -4px 0 9px;
  background: #fdfaf0; border: 1px dashed #e6dbc0; border-radius: 6px; padding: 5px 9px; }
.ext-thinking { margin: 0 0 8px; color: #5b4a1a; line-height: 1.65; font-size: 13px; }
.ext-thinking b { color: #8a6d1a; }
.ext-item { margin: 5px 0; color: #444; font-size: 13px; }
.ext-item b { color: #8a6d1a; font-size: 12.5px; }
.ext-item a { color: var(--ink); text-decoration: none; font-size: 12.5px; }
.ext-item a:hover { text-decoration: underline; }
.ext-item .note { color: var(--muted); font-size: 12px; }
/* 发散链: 想法 → 证据(印证/反驳/边界) → 落点 */
.chain { background: #fffdf6; border: 1px solid #e6dbc0; border-left: 3px solid var(--gold);
  border-radius: 8px; padding: 10px 14px 11px; margin: 0 0 10px; }
.chain-claim { color: #6b5518; font-weight: 700; font-size: 13.5px; line-height: 1.6; margin-bottom: 6px; }
.chain-claim a.src { color: var(--ink); font-weight: 400; font-size: 12px; text-decoration: none; }
.chain-claim a.src:hover { text-decoration: underline; }
details.think a { color: var(--ink); }
.chain-no { display: inline-block; background: var(--gold); color: #fff; border-radius: 4px;
  padding: 1px 6px; font-size: 11.5px; margin-right: 7px; vertical-align: 1px; font-weight: 700; }
.chain-ev { color: #444; font-size: 13px; line-height: 1.65; margin: 4px 0 4px 22px;
  padding-left: 9px; border-left: 2px solid #efe7d2; }
.chain-ev b { color: #8a6d1a; font-size: 12.5px; }
.chain-ev a { color: var(--ink); text-decoration: none; font-size: 12.5px; }
.chain-ev a:hover { text-decoration: underline; }
.chain-ev .note { color: var(--muted); font-size: 12px; }
.chain-ev-c { border-left-color: #d9a6a0; background: #fdf7f6; }
.tier { display: inline-block; border-radius: 4px; padding: 0 5px; margin-right: 5px;
  font-size: 11px; font-weight: 700; color: #fff; vertical-align: 1px; }
.tier.tA { background: #2f7d4f; } .tier.tB { background: #b08d2e; }
.tier.tC { background: #b4453a; } .tier.tD { background: #8a8a8a; }
.kind, .corr { display: inline-block; font-size: 11px; color: var(--muted);
  border: 1px solid var(--line); border-radius: 4px; padding: 0 4px; margin-right: 5px; }
.corr { color: #2f7d4f; border-color: #bcd8c5; }
.dead { display: inline-block; font-size: 11px; color: #b4453a; margin-right: 5px; }
.rel { display: inline-block; border-radius: 4px; padding: 0 5px; margin-right: 6px;
  font-size: 11.5px; font-weight: 700; color: #fff; vertical-align: 1px; }
.rel.ok { background: #2f7d4f; }
.rel.no { background: #b4453a; }
.rel.mid { background: #b08d2e; }
.chain-take { margin: 7px 0 0 22px; color: #4a4335; font-size: 13px; line-height: 1.6;
  background: #f6f1e2; border-radius: 6px; padding: 6px 10px; }
.chain-take b { color: #8a6d1a; }
details.think { margin-top: 10px; }
details.think summary { cursor: pointer; color: #8a6d1a; font-size: 12.5px; font-weight: 700; }
details.think div { background: #fffdf6; border: 1px solid #e6dbc0; border-radius: 8px;
  padding: 10px 12px; margin-top: 6px; white-space: pre-wrap; line-height: 1.65;
  color: #5b5545; font-size: 12.5px; }
.pager { display: flex; gap: 12px; margin: 20px 0 8px; }
.pager a { flex: 1; text-align: center; background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 10px; text-decoration: none; color: var(--ink); font-size: 13.5px;
  transition: all .15s; }
.pager a:hover { border-color: var(--ink); box-shadow: 0 3px 10px rgba(31,58,95,.08); }
.pager a.off { opacity: .4; pointer-events: none; }
footer { text-align: center; color: #9b978c; font-size: 12.5px; padding: 24px; }
@media (max-width: 720px) {
  header, .topbar { padding-left: 16px; padding-right: 16px; }
  main.idx, main.detail { padding: 0 12px; }
  .a-stance { display: none; }
}
"""

def emotions_of(A):
    """一条回答的情绪 → [(标签, tone)]。兼容两套模型:

    新(2026-09-13 起) = emotion_tags 多标签 + 强度 + 指向;
    旧(历史日期) = judge 三元, 用旧配色渲染, 不混进新标签的统计语义。
    """
    tags = A.get("emotion_tags")
    if tags:
        return [(t, contract.EMOTION_TAG_TONE.get(t, "dry")) for t in tags]
    j = A.get("judge")
    if j:
        return [(j, contract.EMOTION_CSS_CLASS.get(j, "neu"))]
    return []


def color_of(tone):
    return (contract.EMOTION_TONE_COLOR.get(tone)
            or contract.EMOTION_LEGACY_COLOR.get(tone) or "#8a8a8a")


def tag_stats(summary, an):
    """情绪标签频次(全站)。旧三元会以「积极/中立/消极」三个键混入, 属预期。"""
    c = {}
    for s in summary:
        for i, _ in enumerate(s["answers"]):
            for t, _tone in emotions_of(an[str(s["rank"])]["answers"][i]):
                c[t] = c.get(t, 0) + 1
    return c


def mbar_html(counter, total):
    """按标签频次堆叠的迷你条: 主色调在前, 悬停显示标签与次数(可容纳 12 种标签)。"""
    if total == 0 or not counter:
        return '<div class="mbar"><i style="width:100%;background:var(--neu)"></i></div>'
    items = sorted(counter.items(), key=lambda kv: -kv[1])
    parts = []
    for tag, cnt in items:
        tone = contract.EMOTION_TAG_TONE.get(tag, contract.EMOTION_CSS_CLASS.get(tag, "dry"))
        parts.append(f'<i style="width:{max(cnt * 100 // total, 2)}%;background:{color_of(tone)}"'
                     f' title="{html.escape(tag)} {cnt}/{total}"></i>')
    return f'<div class="mbar">{"".join(parts)}</div>'


def emo_chips(A, with_meta=True):
    """情绪标签 chips + 强度点 + 指向(详情页与索引图例共用)。"""
    tags = A.get("emotion_tags")
    if not tags:
        j = A.get("judge")
        if not j:
            return ""
        return f'<span class="judge {contract.EMOTION_CSS_CLASS.get(j, "neu")}">{html.escape(j)}</span>'
    out = "".join('<span class="emo t-%s">%s</span>'
                  % (contract.EMOTION_TAG_TONE.get(t, "dry"), html.escape(t)) for t in tags)
    if with_meta:
        k = A.get("emotion_intensity")
        if k:
            k = int(k)
            out += ('<span class="emo-up" title="情绪强度 %d/5">%s<i>%s</i></span>'
                    % (k, "●" * k, "●" * (5 - k)))
        tgt = A.get("emotion_target")
        if tgt:
            out += '<span class="emo-tgt">指向 %s</span>' % html.escape(tgt)
    return out


def emo_legend_html():
    """图例: 说明标签配色基调、强度点与指向的含义(交付物自解释, 不靠外部文档)。"""
    tones = []
    for tone, label in contract.EMOTION_TONE_LABEL.items():
        words = "、".join(t for t in contract.EMOTION_TAGS
                         if contract.EMOTION_TAG_TONE.get(t) == tone)
        tones.append('<span class="emo t-%s">%s</span>%s（%s）'
                     % (tone, words.split("、")[0], label, words))
    return ('<div class="legend">情绪标签：' + " · ".join(tones)
            + '<br>情绪强度：●●●●● = 1→5 级（1 极淡、5 极强）　情绪指向：'
            + "、".join(contract.EMOTION_TARGETS) + '</div>')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="输出根文件(默认 <root>/<报告前缀>-<date>.html)")
    args = ap.parse_args()

    summary = json.load(open(contract.path_answers(args.root, args.date), encoding="utf-8"))
    an = json.load(open(contract.path_analysis(args.root, args.date), encoding="utf-8"))
    ext_path = contract.path_extension(args.root, args.date)
    ext = json.load(open(ext_path, encoding="utf-8")) if os.path.exists(ext_path) else {}

    out = args.out or contract.report_entry(args.root, args.date)
    pages_dir = out.rsplit(".", 1)[0]  # <root>/<报告前缀>-<date>/  目录
    os.makedirs(pages_dir, exist_ok=True)
    idx_path = os.path.join(pages_dir, contract.HTML_INDEX_NAME)

    tag_c = tag_stats(summary, an)
    total = sum(len(s["answers"]) for s in summary)
    n = len(summary)

    def draft_panel_html():
        """索引页「今日短评」挑选面板(2026-09-21 起): 推荐/备选按 priority 一屏排列。

        数据源与详情页短评块一致(publish_queue.json 的 ready/over_daily_cap + draft 文件);
        队列缺失或无稿时整块不出现(历史日期不受影响)。"""
        qp = contract.path_queue(args.root, args.date)
        if not os.path.exists(qp):
            return ""
        try:
            qitems = json.load(io.open(qp, encoding="utf-8-sig")).get("items", {})
        except Exception:
            return ""
        rows = []
        for q in qitems.values():
            if q.get("state") not in ("ready", "over_daily_cap"):
                continue
            rk = q.get("rank")
            dp = contract.path_draft(args.root, args.date, rk) if isinstance(rk, int) else ""
            if not dp or not os.path.exists(dp):
                continue
            try:
                raw = io.open(dp, encoding="utf-8-sig").read().strip()
            except Exception:
                continue
            lines0 = raw.splitlines()
            t0 = lines0[0].lstrip("# ").strip() if lines0 and lines0[0].lstrip().startswith("#") else ""
            body0 = "\n".join(lines0[1:] if t0 else lines0).strip()
            if not body0:
                continue
            rows.append((q.get("priority") or 999, 0 if q.get("state") == "ready" else 1,
                         rk, t0, body0, q.get("len")))
        if not rows:
            return ""
        rows.sort(key=lambda t: (t[0], t[1]))
        out = ['<section class="dpanel"><h2>✍️ 今日短评 · 挑稿面板'
               '（推荐位=每日上限内；备选=超预算，人工终审可换发）</h2>']
        for prio, _ord, rk, t0, body0, ln in rows:
            badge = "推荐 #%d" % prio
            cls = ""
            if _ord:
                badge = "备选 #%d" % prio
                cls = " alt"
            snip = re.sub(r"\s+", "", body0)[:42]
            n_len = ln if ln else len(re.sub(r"\s", "", body0))
            out.append(
                f'<div class="drow"><span class="dbadge{cls}">{badge}</span>'
                f'<span class="drank">#{rk}</span>'
                f'<a class="dlink" href="{contract.page_name(rk)}#draft">{html.escape(t0 or "(无标题)")}</a>'
                f'<span class="dsnip">{html.escape(snip)}…</span>'
                f'<span class="dlen">{n_len} 字</span></div>')
        out.append("</section>")
        return "".join(out)

    # ============ 索引页 ============
    cards = []
    for s in summary:
        rank = s["rank"]
        top = s["answers"][0]["likes"] if s["answers"] else "-"
        m = len(s["answers"])
        c_q = {}
        for i, _ in enumerate(s["answers"]):
            for t, _tone in emotions_of(an[str(rank)]["answers"][i]):
                c_q[t] = c_q.get(t, 0) + 1
        is_ext = str(rank) in ext
        # 覆盖度: 让读者知道"抓到的 5 条"是该问题的多少(见 SKILL.md 热点拓展/数据源说明)
        cov_html = f"<span>覆盖 {m}/{s['total_answers']}</span>" if s.get("total_answers") else ""
        cards.append(f"""<a class="card-link" href="{contract.page_name(rank)}">
<div class="card-top"><span class="rank">#{rank}</span>{'<span class="ext-tag">扩展</span>' if is_ext else ''}{'<span class="add-tag">追加</span>' if s.get('extra') else ''}</div>
<div class="card-title">{html.escape(s['title'])}</div>
<div class="card-meta"><span>最高赞 <b>{top}</b></span><span>{m} 回答</span>{cov_html}</div>
{mbar_html(c_q, m)}</a>""")

    # 情绪统计: 按标签频次(新模型 12 类标签)出条; 历史日期则是旧三值, 同一条逻辑渲染
    top_tags = sorted(tag_c.items(), key=lambda kv: -kv[1])[:8]
    emo_stats = "".join(f"<span><b>{c}</b>{html.escape(t)}</span>" for t, c in top_tags)
    emo_bar = "\n".join(
        f'<i style="width:{c * 100 // max(total, 1)}%;background:'
        f'{color_of(contract.EMOTION_TAG_TONE.get(t, contract.EMOTION_CSS_CLASS.get(t, "dry")))}"'
        f' title="{html.escape(t)} {c}"></i>' for t, c in
        sorted(tag_c.items(), key=lambda kv: -kv[1]))

    idx_html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{contract.REPORT_TITLE} {args.date} · 索引</title><style>{CSS}</style></head><body>
<header><h1>{contract.REPORT_TITLE} · {args.date}</h1>
<p>{pf.get('source_bar')}</p>
<div class="stats"><span><b>{n}</b>问题</span><span><b>{total}</b>回答</span>
{emo_stats}
<span class="ebar">{emo_bar}</span></div>
{emo_legend_html()}
</header><main class="idx">{draft_panel_html()}{"".join(cards)}
</main><footer>生成于 {args.date} · 原始数据与脚本见 {contract.RAW_DIRNAME}/{args.date} · 四维分析基于回答原文归纳 · 情绪为「多标签＋强度＋指向」, 由 Agent 阅读原文判定</footer></body></html>"""
    open(idx_path, "w", encoding="utf-8").write(idx_html)

    # ============ 详情页 ============
    def answer_html(s, rank):
        parts = []
        for i, a in enumerate(s["answers"], 1):
            A = an[str(rank)]["answers"][i - 1]
            st = html.escape(A["stance"])
            rows = [("立场", st),
                    ("解决思路", html.escape(A["approach"])),
                    ("判断逻辑", html.escape(A["logic"])),
                    ("情绪倾向", html.escape(A["emotion"]))]
            # 多元化情绪三行(仅新模型; 历史日期没有这三列, 只出「情绪倾向」)
            if A.get("emotion_tags"):
                k = int(A.get("emotion_intensity") or 0)
                rows.append(("情绪标签", "、".join(html.escape(t) for t in A["emotion_tags"])))
                rows.append(("情绪强度", f"{'●' * k}{'○' * (5 - k)}　{k}/5（1 极淡 → 5 极强）"))
                rows.append(("情绪指向", html.escape(A.get("emotion_target") or "")))
            table = "".join(f'<tr><td class="k">{k2}</td><td>{v}</td></tr>' for k2, v in rows)
            parts.append(f"""<details class="{contract.HTML_ANSWER_DETAIL_CLASS}"><summary>
<span class="a-no">回答 {i}</span><span class="a-author">{html.escape(a['author']) or '匿名'}</span>
<span class="a-likes">👍 {a['likes']}</span>
{emo_chips(A)}
<span class="a-stance">{st}</span></summary>
<div class="a-body"><table class="analysis">{table}</table>
<details class="{contract.HTML_TEXT_DETAIL_CLASS}"><summary>查看原文全文（{len(a['text'])} 字）{('' if a.get('content_status') == 'full' else '· ' + contract.HTML_SUMMARY_TAG + '·全文需登录')}</summary>
<div>{html.escape(a['text'])}</div></details></div></details>""")
        return "".join(parts)

    def draft_html(rank):
        """发帖短评(ext_search/<D>/rank_<n>/draft_<n>.md, 50–100 字犀利短评)。

        稿子是给人改语言用的: 原样展示、不做 markdown 渲染(只处理首行 # 标题与段落切分),
        避免转义/加粗把内容改样。文件不存在就整块不出现(历史日期都有旧长稿, 照常展示)。
        待发帖状态徽标取自 publish_queue.json(缺队列文件就不显示)。
        """
        p = contract.path_draft(args.root, args.date, rank)
        if not os.path.exists(p):
            return ""
        try:
            raw = io.open(p, encoding="utf-8-sig").read().strip()
        except Exception:
            return ""
        if not raw:
            return ""
        lines = raw.splitlines()
        title = ""
        if lines and lines[0].lstrip().startswith("#"):
            title = lines[0].lstrip("# ").strip()
            lines = lines[1:]
        paras = [x.strip() for x in "\n".join(lines).split("\n\n") if x.strip()]
        body = "".join("<p>%s</p>" % html.escape(x).replace("\n", "<br>") for x in paras)
        st = ""
        qp = contract.path_queue(args.root, args.date)
        if os.path.exists(qp):
            try:
                q = json.load(io.open(qp, encoding="utf-8-sig")).get("items", {}).get(str(rank), {})
                lbl = {"ready": "推荐", "published": "已发布", "mediocre": "打回·中庸",
                       "len_out_of_range": "打回·字数", "draft_pending": "过闸待写",
                       "over_daily_cap": "备选·超今日建议", "sharpness_unjudged": "待复核"}.get(q.get("state"))
                if lbl:
                    prio = q.get("priority")
                    st = " · " + (("%s #%d" % (lbl, prio))
                                  if (prio and q.get("state") in ("ready", "over_daily_cap")) else lbl)
            except Exception:
                st = ""
        n = len(re.sub(r"\s", "", "\n".join(lines)))   # 与队列口径一致: 只数正文(标题行不算, 2026-09-21 修)
        head = ('<div class="ext-head">✍️ %s（%d 字 · 50–100 字犀利向%s）</div>'
                % (contract.DRAFT_SHEET, n, st))
        t = f'<div class="draft-title">{html.escape(title)}</div>' if title else ""
        return f'<div class="draft" id="draft">{head}{t}{body}</div>'

    def ext_html(rank):
        e = ext.get(str(rank))
        if not e or not (e.get("items") or e.get("chains") or e.get("thinking")):
            return ""
        parts = [f'<div class="ext"><div class="ext-head">🧠 {contract.HTML_EXT_MARK}（发散分析）</div>']
        chains = e.get("chains") or []

        def ev_html(it):
            rel = it.get("relation") or ""
            badge = ""
            if rel:
                cls = contract.EXT_RELATION_CSS.get(rel, "mid")
                badge = f'<span class="rel {cls}">{html.escape(rel)}</span>'
            # 信源等级(由 verify_ext.py 复核写入): A 事实性 / B 待定 / C 不采信 / D 观点
            tier = it.get("source_tier") or ""
            tier_html = ""
            if tier in contract.EXT_SOURCE_TIERS:
                label = contract.EXT_SOURCE_TIERS[tier]
                tier_html = (f'<span class="tier t{tier}" title="{html.escape(label)}">'
                             f'{tier}</span>')
                kind = it.get("source_kind") or ""
                if kind:
                    tier_html += f'<span class="kind">{html.escape(kind)}</span>'
                ls = str(it.get("link_status") or "")
                if ls in contract.EXT_LINK_DEAD:
                    tier_html += f'<span class="dead">来源已失效 {html.escape(ls)}</span>'
                elif ls and ls not in ("200", "skipped"):
                    # 5xx/超时/连接错误 = 未探明(站点限流), 不能当死链 —— 否则一次 522 成片
                    # 就会给几十条活链接贴上「来源已失效」(2026-09-13 实测)。
                    tier_html += (f'<span class="kind" title="探活未成功，非确定性失效">'
                                  f'探活未成功 {html.escape(ls)}</span>')
                corr = (it.get("corroboration") or {}).get("groups") or 0
                if corr >= contract.EXT_CORROBORATION_MIN:
                    hosts = (it.get("corroboration") or {}).get("hosts") or []
                    tier_html += (f'<span class="corr" title="独立来源组 {corr}：'
                                  f'{html.escape("、".join(hosts))}">多源印证</span>')
            url = it.get("url", "")
            link = f' <a href="{html.escape(url)}" target="_blank">[来源]</a>' if url else ""
            note = f' <span class="note">({html.escape(it["note"])})</span>' if it.get("note") else ""
            cls = " chain-ev-c" if tier == "C" else ""
            return (f'<div class="chain-ev{cls}">{badge}{tier_html}'
                    f'<b>[{html.escape(it["type"])}]</b> '
                    f'{html.escape(it["content"])}{link}{note}</div>')

        if chains:
            # 结构化: 每条链 = 想法(可附原答链接) → 证据(印证/反驳/边界) → 落点
            tiers = {}
            for ch0 in chains:
                for it0 in ch0.get("evidence", []):
                    t0 = it0.get("source_tier")
                    if t0:
                        tiers[t0] = tiers.get(t0, 0) + 1
            if tiers:
                parts.append('<div class="ext-tierline">信源等级：' + " · ".join(
                    f'{t} {contract.EXT_SOURCE_TIERS[t]} {tiers[t]} 条'
                    for t in contract.EXT_TIER_ORDER if t in tiers) + '</div>')
            for ci, ch in enumerate(chains, 1):
                parts.append('<div class="chain">')
                src = ch.get("source") or {}
                src_link = ""
                if src.get("url"):
                    bits = []
                    if src.get("answer_index"):
                        bits.append(f"回答 {src['answer_index']}")
                    if src.get("likes") not in (None, ""):
                        bits.append(f"{src['likes']} 赞")
                    label = "·".join(bits) or "原答"
                    src_link = (f' <a class="src" href="{html.escape(src["url"])}"'
                                f' target="_blank">［出处：{html.escape(label)}］</a>')
                parts.append(f'<div class="chain-claim"><span class="chain-no">'
                             f'{contract.HTML_EXT_CLAIM_PREFIX} {ci}</span>'
                             f'{html.escape(ch.get("claim", ""))}{src_link}</div>')
                for it in ch.get("evidence", []):
                    parts.append(ev_html(it))
                if ch.get("takeaway"):
                    parts.append(f'<div class="chain-take"><b>落点：</b>'
                                 f'{html.escape(ch["takeaway"])}</div>')
                parts.append('</div>')
        else:
            # 兼容历史格式(无 chains): 退回扁平条目列表
            for it in e.get("items", []):
                parts.append(ev_html(it))
        if e.get("thinking"):
            # 思考过程里的裸链接直接变成可点击(否则读者没法顺着检索路径回源)
            think = re.sub(r'(https?://[^\s，。；：）)]+)',
                           r'<a href="\1" target="_blank">\1</a>',
                           html.escape(e["thinking"]))
            parts.append('<details class="think"><summary>思考过程（检索路径与收敛依据）</summary>'
                         f'<div>{think}</div></details>')
        parts.append("</div>")
        return "".join(parts)

    for s in summary:
        rank = s["rank"]
        prev = contract.page_name(rank - 1) if rank > 1 else None
        nxt = contract.page_name(rank + 1) if rank < n else None
        top = s["answers"][0]["likes"] if s["answers"] else "-"
        cov_badge = (f'<span class="badge">覆盖 {len(s["answers"])}/{s["total_answers"]}</span>'
                     if s.get("total_answers") else "")
        pager = f"""<div class="pager">
<a class="{'off' if not prev else ''}" href="{prev or '#'}">← 上一题</a>
<a href="{contract.HTML_INDEX_NAME}">返回索引</a>
<a class="{'off' if not nxt else ''}" href="{nxt or '#'}">下一题 →</a></div>"""
        page = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>#{rank} · {contract.REPORT_TITLE} {args.date}</title><style>{CSS}</style></head><body>
<div class="topbar"><a href="{contract.HTML_INDEX_NAME}">☰ 索引</a>{pager.replace('<div class="pager">', '').replace('</div>', '')}</div>
<main class="detail">
<div class="q">
<div class="q-head"><span class="rank">#{rank}</span>
<a class="q-title" href="{html.escape(s['url'])}" target="_blank">{html.escape(s['title'])}</a>
<span class="badges"><span class="badge">最高赞 {top}</span><span class="badge">{len(s['answers'])} 回答</span>{cov_badge}</span></div>
<div class="essence"><b>问题本质：</b>{html.escape(an[str(rank)]['essence'])}</div>
{answer_html(s, rank)}
{ext_html(rank)}
{draft_html(rank)}
</div>
{pager}
</main><footer>生成于 {args.date} · 四维分析基于回答原文归纳 · {'本页为单问题追加追踪（非榜单条目）' if s.get('extra') else '热点拓展覆盖全部条目'}</footer></body></html>"""
        # 详情页目录跟随 --out 推导出的 pages_dir(不直接用契约默认目录, 以兼容自定义 --out)
        open(os.path.join(pages_dir, contract.page_name(rank)), "w", encoding="utf-8").write(page)

    # ============ 根入口(自动跳转) ============
    rel = os.path.relpath(idx_path, os.path.dirname(out)).replace("\\", "/")
    open(out, "w", encoding="utf-8").write(
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" '
        f'content="0; url={rel}"><title>{contract.REPORT_TITLE} {args.date}</title></head>'
        f'<body style="font-family:sans-serif;padding:40px;text-align:center">正在进入索引页…'
        f'<br><a href="{rel}">点击进入</a></body></html>')
    print(f"saved: {idx_path} + {n} 详情页 + 入口 {out}")

if __name__ == "__main__":
    main()
