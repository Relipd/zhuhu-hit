# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 分页式 HTML 生成(索引页 + 每问题一页 + 翻页导航)。

结构:
  <root>/知乎热榜跟进-<date>.html          根入口(自动跳转)
  <root>/知乎热榜跟进-<date>/index.html   索引页: 4×5自适应网格卡片, 点击进入详情
  <root>/知乎热榜跟进-<date>/q01..q20.html 详情页: 每问题一页, 回答折叠扩展, 上一题/下一题翻页

用法: python gen_html.py --root <工作根目录> --date 2026-08-08 [--out <输出根文件>]
"""
import argparse, html, json, os, re

JUDGE_CLS = {"积极": "pos", "中立": "neu", "消极": "neg"}
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
.a-stance { color: var(--ink); font-size: 13px; flex: 1; min-width: 200px; font-weight: 600; }
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
.ext-head { font-weight: 700; color: #8a6d1a; margin-bottom: 7px; font-size: 14px; }
.ext-thinking { margin: 0 0 8px; color: #5b4a1a; line-height: 1.65; font-size: 13px; }
.ext-thinking b { color: #8a6d1a; }
.ext-item { margin: 5px 0; color: #444; font-size: 13px; }
.ext-item b { color: #8a6d1a; font-size: 12.5px; }
.ext-item a { color: var(--ink); text-decoration: none; font-size: 12.5px; }
.ext-item a:hover { text-decoration: underline; }
.ext-item .note { color: var(--muted); font-size: 12px; }
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
    jc = {"积极": 0, "中立": 0, "消极": 0}
    for s in summary:
        for i, _ in enumerate(s["answers"]):
            jc[an[str(s["rank"])]["answers"][i]["judge"]] += 1
    return jc

def mbar_html(jc, total, w=6):
    if total == 0:
        return '<div class="mbar"><i style="width:100%;background:var(--neu)"></i></div>'
    parts = []
    for key, color in (("积极", "var(--pos)"), ("中立", "var(--neu)"), ("消极", "var(--neg)")):
        if jc[key]:
            parts.append(f'<i style="width:{jc[key] * 100 // total}%;background:{color}"></i>')
    return f'<div class="mbar">{"".join(parts)}</div>'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="输出根文件(默认 <root>/知乎热榜跟进-<date>.html)")
    args = ap.parse_args()

    day = os.path.join(args.root, "raw", args.date)
    summary = json.load(open(os.path.join(day, "answers_summary.json"), encoding="utf-8"))
    an = json.load(open(os.path.join(day, "analysis.json"), encoding="utf-8"))
    ext_path = os.path.join(day, "extension.json")
    ext = json.load(open(ext_path, encoding="utf-8")) if os.path.exists(ext_path) else {}

    out = args.out or os.path.join(args.root, f"知乎热榜跟进-{args.date}.html")
    pages_dir = out.rsplit(".", 1)[0]  # <root>/知乎热榜跟进-<date>/  目录
    os.makedirs(pages_dir, exist_ok=True)
    idx_path = os.path.join(pages_dir, "index.html")

    jc = jc_stats(summary, an)
    total = sum(len(s["answers"]) for s in summary)
    n = len(summary)

    # ============ 索引页 ============
    cards = []
    for s in summary:
        rank = s["rank"]
        top = s["answers"][0]["likes"] if s["answers"] else "-"
        m = len(s["answers"])
        jc_q = {"积极": 0, "中立": 0, "消极": 0}
        for i, _ in enumerate(s["answers"]):
            jc_q[an[str(rank)]["answers"][i]["judge"]] += 1
        is_ext = rank <= 10 and str(rank) in ext
        cards.append(f"""<a class="card-link" href="q{rank:02d}.html">
<div class="card-top"><span class="rank">#{rank}</span>{'<span class="ext-tag">扩展</span>' if is_ext else ''}</div>
<div class="card-title">{html.escape(s['title'])}</div>
<div class="card-meta"><span>最高赞 <b>{top}</b></span><span>{m} 回答</span></div>
{mbar_html(jc_q, m)}</a>""")

    idx_html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>知乎热榜跟进 {args.date} · 索引</title><style>{CSS}</style></head><body>
<header><h1>知乎热榜跟进 · {args.date}</h1>
<p>数据来源：知乎开放平台 · 热榜前 {n} · 每问题多查询合并去重取前 10 回答 · 点击卡片进入详情页 · 前 10 含热点拓展</p>
<div class="stats"><span><b>{n}</b>问题</span><span><b>{total}</b>回答</span>
<span><b>{jc['积极']}</b>积极</span><span><b>{jc['中立']}</b>中立</span><span><b>{jc['消极']}</b>消极</span>
<span class="ebar"><i style="width:{jc['积极'] * 100 // max(total,1)}%;background:var(--pos)"></i>
<i style="width:{jc['中立'] * 100 // max(total,1)}%;background:var(--neu)"></i>
<i style="width:{jc['消极'] * 100 // max(total,1)}%;background:var(--neg)"></i></span></div>
</header><main class="idx">{"".join(cards)}
</main><footer>生成于 {args.date} · 原始数据与脚本见 raw/{args.date} · 四维分析基于回答原文归纳</footer></body></html>"""
    open(idx_path, "w", encoding="utf-8").write(idx_html)

    # ============ 详情页 ============
    def md_bold(s):
        """把分析文本中的 **加粗** 语法转成 <b> 标签(先转义 HTML 防注入)"""
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(s or ""))

    def answer_html(s, rank):
        parts = []
        for i, a in enumerate(s["answers"], 1):
            A = an[str(rank)]["answers"][i - 1]
            j = A["judge"]
            st = md_bold(A["stance"])
            parts.append(f"""<details class="a"><summary>
<span class="a-no">回答 {i}</span><span class="a-author">{html.escape(a['author']) or '匿名'}</span>
<span class="a-likes">👍 {a['likes']}</span>
<span class="judge {JUDGE_CLS.get(j, 'neu')}">{html.escape(j)}</span>
<span class="a-stance">{st}</span></summary>
<div class="a-body"><table class="analysis">
<tr><td class="k">立场</td><td>{st}</td></tr>
<tr><td class="k">解决思路</td><td>{md_bold(A['approach'])}</td></tr>
<tr><td class="k">判断逻辑</td><td>{md_bold(A['logic'])}</td></tr>
<tr><td class="k">情绪倾向</td><td>{md_bold(A['emotion'])}</td></tr></table>
<details class="a-text"><summary>查看原文全文（{len(a['text'])} 字）{('' if a.get('content_status') == 'full' else '· 接口摘要·全文需登录')}</summary>
<div>{html.escape(a['text'])}</div></details></div></details>""")
        return "".join(parts)

    def ext_html(rank):
        e = ext.get(str(rank))
        if not e or not (e.get("items") or e.get("thinking")):
            return ""
        parts = ['<div class="ext"><div class="ext-head">🧠 热点拓展思考（发散分析）</div>']
        if e.get("thinking"):
            parts.append(f'<div class="ext-thinking"><b>思考过程：</b>{html.escape(e["thinking"])}</div>')
        for it in e.get("items", []):
            url = it.get("url", "")
            link = f' <a href="{html.escape(url)}" target="_blank">[来源]</a>' if url else ""
            note = f' <span class="note">({html.escape(it["note"])})</span>' if it.get("note") else ""
            parts.append(f'<div class="ext-item"><b>[{html.escape(it["type"])}]</b> '
                         f'{html.escape(it["content"])}{link}{note}</div>')
        parts.append("</div>")
        return "".join(parts)

    for s in summary:
        rank = s["rank"]
        prev, nxt = f"q{rank - 1:02d}.html" if rank > 1 else None, f"q{rank + 1:02d}.html" if rank < n else None
        top = s["answers"][0]["likes"] if s["answers"] else "-"
        pager = f"""<div class="pager">
<a class="{'off' if not prev else ''}" href="{prev or '#'}">← 上一题</a>
<a href="index.html">返回索引</a>
<a class="{'off' if not nxt else ''}" href="{nxt or '#'}">下一题 →</a></div>"""
        page = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>#{rank} · 知乎热榜跟进 {args.date}</title><style>{CSS}</style></head><body>
<div class="topbar"><a href="index.html">☰ 索引</a>{pager.replace('<div class="pager">', '').replace('</div>', '')}</div>
<main class="detail">
<div class="q">
<div class="q-head"><span class="rank">#{rank}</span>
<a class="q-title" href="{html.escape(s['url'])}" target="_blank">{html.escape(s['title'])}</a>
<span class="badges"><span class="badge">最高赞 {top}</span><span class="badge">{len(s['answers'])} 回答</span></span></div>
<div class="essence"><b>问题本质：</b>{md_bold(an[str(rank)]['essence'])}</div>
{answer_html(s, rank)}
{ext_html(rank)}
</div>
{pager}
</main><footer>生成于 {args.date} · 四维分析基于回答原文归纳 · 热点拓展仅覆盖热榜前 10</footer></body></html>"""
        open(os.path.join(pages_dir, f"q{rank:02d}.html"), "w", encoding="utf-8").write(page)

    # ============ 根入口(自动跳转) ============
    rel = os.path.relpath(idx_path, os.path.dirname(out)).replace("\\", "/")
    open(out, "w", encoding="utf-8").write(
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" '
        f'content="0; url={rel}"><title>知乎热榜跟进 {args.date}</title></head>'
        f'<body style="font-family:sans-serif;padding:40px;text-align:center">正在进入索引页…'
        f'<br><a href="{rel}">点击进入</a></body></html>')
    print(f"saved: {idx_path} + {n} 详情页 + 入口 {out}")

if __name__ == "__main__":
    main()
