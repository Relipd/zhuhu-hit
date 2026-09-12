# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 分页式 HTML 生成(索引页 + 每问题一页 + 翻页导航)。

结构:
  <root>/知乎热榜跟进-<date>.html          根入口(自动跳转)
  <root>/知乎热榜跟进-<date>/index.html   索引页: 4×5自适应网格卡片, 点击进入详情
  <root>/知乎热榜跟进-<date>/q01..q20.html 详情页: 每问题一页, 回答折叠扩展, 上一题/下一题翻页

用法: python gen_html.py --root <工作根目录> --date 2026-08-08 [--out <输出根文件>]
"""
import argparse, html, json, os, re

import contract   # 数据契约:文件名 / 字段 / 值域的单一定义处(见 contract.py)

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

def jc_stats(summary, an):
    # 情绪统计口径由契约定义(与 Excel 下拉、verify_html 校验同源)
    jc = {e: 0 for e in contract.EMOTIONS}
    for s in summary:
        for i, _ in enumerate(s["answers"]):
            jc[an[str(s["rank"])]["answers"][i]["judge"]] += 1
    return jc

def mbar_html(jc, total, w=6):
    if total == 0:
        return '<div class="mbar"><i style="width:100%;background:var(--neu)"></i></div>'
    parts = []
    for key in contract.EMOTIONS:
        color = f"var(--{contract.EMOTION_CSS_CLASS[key]})"
        if jc[key]:
            parts.append(f'<i style="width:{jc[key] * 100 // total}%;background:{color}"></i>')
    return f'<div class="mbar">{"".join(parts)}</div>'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="输出根文件(默认 <root>/知乎热榜跟进-<date>.html)")
    args = ap.parse_args()

    summary = json.load(open(contract.path_answers(args.root, args.date), encoding="utf-8"))
    an = json.load(open(contract.path_analysis(args.root, args.date), encoding="utf-8"))
    ext_path = contract.path_extension(args.root, args.date)
    ext = json.load(open(ext_path, encoding="utf-8")) if os.path.exists(ext_path) else {}

    out = args.out or contract.report_entry(args.root, args.date)
    pages_dir = out.rsplit(".", 1)[0]  # <root>/知乎热榜跟进-<date>/  目录
    os.makedirs(pages_dir, exist_ok=True)
    idx_path = os.path.join(pages_dir, contract.HTML_INDEX_NAME)

    jc = jc_stats(summary, an)
    total = sum(len(s["answers"]) for s in summary)
    n = len(summary)

    # ============ 索引页 ============
    cards = []
    for s in summary:
        rank = s["rank"]
        top = s["answers"][0]["likes"] if s["answers"] else "-"
        m = len(s["answers"])
        jc_q = {e: 0 for e in contract.EMOTIONS}
        for i, _ in enumerate(s["answers"]):
            jc_q[an[str(rank)]["answers"][i]["judge"]] += 1
        is_ext = rank <= 10 and str(rank) in ext
        # 覆盖度: 让读者知道"抓到的 5 条"是该问题的多少(见 SKILL.md 热点拓展/数据源说明)
        cov_html = f"<span>覆盖 {m}/{s['total_answers']}</span>" if s.get("total_answers") else ""
        cards.append(f"""<a class="card-link" href="{contract.page_name(rank)}">
<div class="card-top"><span class="rank">#{rank}</span>{'<span class="ext-tag">扩展</span>' if is_ext else ''}</div>
<div class="card-title">{html.escape(s['title'])}</div>
<div class="card-meta"><span>最高赞 <b>{top}</b></span><span>{m} 回答</span>{cov_html}</div>
{mbar_html(jc_q, m)}</a>""")

    # 情绪统计条: 标签与配色均按契约值域生成, 不硬编码具体情绪词
    emo_stats = "".join(f"<span><b>{jc[e]}</b>{e}</span>" for e in contract.EMOTIONS)
    emo_bar = "\n".join(
        f'<i style="width:{jc[e] * 100 // max(total,1)}%;'
        f'background:var(--{contract.EMOTION_CSS_CLASS[e]})"></i>'
        for e in contract.EMOTIONS)

    idx_html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{contract.REPORT_TITLE} {args.date} · 索引</title><style>{CSS}</style></head><body>
<header><h1>{contract.REPORT_TITLE} · {args.date}</h1>
<p>数据来源：知乎开放平台热榜 · 每问题数据 =「问题维度网页接口(按赞取前 N)」∪「关键词搜索召回」并集 · 点击卡片进入详情页 · 前 10 含热点拓展</p>
<div class="stats"><span><b>{n}</b>问题</span><span><b>{total}</b>回答</span>
{emo_stats}
<span class="ebar">{emo_bar}</span></div>
</header><main class="idx">{"".join(cards)}
</main><footer>生成于 {args.date} · 原始数据与脚本见 {contract.RAW_DIRNAME}/{args.date} · 四维分析基于回答原文归纳</footer></body></html>"""
    open(idx_path, "w", encoding="utf-8").write(idx_html)

    # ============ 详情页 ============
    def answer_html(s, rank):
        parts = []
        for i, a in enumerate(s["answers"], 1):
            A = an[str(rank)]["answers"][i - 1]
            j = A["judge"]
            st = html.escape(A["stance"])
            parts.append(f"""<details class="{contract.HTML_ANSWER_DETAIL_CLASS}"><summary>
<span class="a-no">回答 {i}</span><span class="a-author">{html.escape(a['author']) or '匿名'}</span>
<span class="a-likes">👍 {a['likes']}</span>
<span class="judge {JUDGE_CLS.get(j, 'neu')}">{html.escape(j)}</span>
<span class="a-stance">{st}</span></summary>
<div class="a-body"><table class="analysis">
<tr><td class="k">立场</td><td>{st}</td></tr>
<tr><td class="k">解决思路</td><td>{html.escape(A['approach'])}</td></tr>
<tr><td class="k">判断逻辑</td><td>{html.escape(A['logic'])}</td></tr>
<tr><td class="k">情绪倾向</td><td>{html.escape(A['emotion'])}</td></tr></table>
<details class="{contract.HTML_TEXT_DETAIL_CLASS}"><summary>查看原文全文（{len(a['text'])} 字）{('' if a.get('content_status') == 'full' else '· ' + contract.HTML_SUMMARY_TAG + '·全文需登录')}</summary>
<div>{html.escape(a['text'])}</div></details></div></details>""")
        return "".join(parts)

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
                if it.get("link_status") and str(it["link_status"]) != "200":
                    tier_html += (f'<span class="dead">来源已失效 {html.escape(str(it["link_status"]))}'
                                  f'</span>')
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
</div>
{pager}
</main><footer>生成于 {args.date} · 四维分析基于回答原文归纳 · 热点拓展仅覆盖热榜前 10</footer></body></html>"""
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
