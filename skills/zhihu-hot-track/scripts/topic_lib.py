# -*- coding: utf-8 -*-
"""话题库双轨维护:index.json(机读,url 唯一键去重)+ 话题库.md(人读展示,由 index 重建)

用法:
  python topic_lib.py update --root <ROOT> --date YYYY-MM-DD   # 增量收录 extension.json → 重建 md
  python topic_lib.py search --root <ROOT> --url <url>          # URL 查重(收录与否)
  python topic_lib.py search --root <ROOT> --keyword <词>       # 内容/分类关键词命中
  python topic_lib.py search --root <ROOT> --cat <分类>         # 列出某分类全部条目
  python topic_lib.py rebuild --root <ROOT>                     # 从 index.json 重建 md(修复用)
"""
import argparse
import io
import json
import os
import re
import sys


def load_index(path):
    if not os.path.exists(path):
        return []
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("items", [])


def save_index(path, items):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"items": items}, ensure_ascii=False, indent=1))


def norm_url(u):
    return re.sub(r"\?.*$", "", u).rstrip("/")


def parse_md(md_text):
    """从旧版纯文本话题库.md 解析条目(一次性迁移用)"""
    items, cat = [], None
    for line in md_text.splitlines():
        if line.startswith("## "):
            cat = re.sub(r"\(.*\)$", "", line[3:].strip()).strip()
        elif line.startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 5 and cells[0] not in ("日期", "---"):
                items.append({"date": cells[0], "rank": cells[1], "cat": cat,
                              "type": cells[2], "content": cells[3], "url": cells[4]})
    return items


def rebuild_md(items):
    cats = []
    for it in items:
        if it["cat"] not in cats:
            cats.append(it["cat"])
    out = ["# 话题库(跨日期累积)", "",
           "机读索引: index.json(url 唯一键去重)。维护: `topic_lib.py update / search / rebuild`(见 skill scripts)。",
           "分类按热点主题归纳;发散搜索前查重:同一主题不重复搜索、同一类型案例 ≤3、已收录条目不重复收录。", ""]
    for cat in cats:
        out.append("## " + cat)
        out.append("")
        out.append("| 日期 | rank | 类型 | 内容要点 | 来源 url |")
        out.append("|---|---|---|---|---|")
        for it in [x for x in items if x["cat"] == cat]:
            c = it["content"] if len(it["content"]) <= 58 else it["content"][:58] + "…"
            out.append("| {d} | {r} | {t} | {c} | {u} |".format(
                d=it["date"], r=it["rank"], t=it["type"], c=c, u=it["url"]))
        out.append("")
    return "\n".join(out)


def cmd_update(root, date):
    lib = os.path.join(root, "话题库")
    if not os.path.isdir(lib):
        os.makedirs(lib)
    ip, mp = os.path.join(lib, "index.json"), os.path.join(lib, "话题库.md")
    items = load_index(ip)
    if not items and os.path.exists(mp):
        with io.open(mp, "r", encoding="utf-8") as f:
            items = parse_md(f.read())
        print("index.json 为空,已从现有 md 迁移", len(items), "条")
    ext_path = os.path.join(root, "raw", date, "extension.json")
    if os.path.exists(ext_path):
        with io.open(ext_path, "r", encoding="utf-8-sig") as f:
            ext = json.load(f)
        seen = {norm_url(it["url"]): it for it in items}
        added = upgraded = 0
        for key in sorted(ext, key=int):
            e = ext[key]
            cat = e.get("category", "")
            for it in e["items"]:
                n = norm_url(it["url"])
                if n in seen:
                    # 已收录:若 extension 里 content 更完整则升级(旧迁移条目是截断版)
                    if len(it["content"]) > len(seen[n]["content"]):
                        seen[n]["content"] = it["content"]
                        upgraded += 1
                    continue
                items.append({"date": date, "rank": key, "cat": cat,
                              "type": it["type"], "content": it["content"], "url": it["url"]})
                seen[n] = items[-1]
                added += 1
        print("新增收录", added, "条, 内容升级", upgraded, "条")
    save_index(ip, items)
    with io.open(mp, "w", encoding="utf-8") as f:
        f.write(rebuild_md(items))
    cats = {it["cat"] for it in items}
    print("index.json:", len(items), "条 | 话题库.md 已重建 | 分类:", len(cats), "个:", ", ".join(sorted(cats)))


def cmd_search(root, url=None, keyword=None, cat=None):
    lib = os.path.join(root, "话题库")
    items = load_index(os.path.join(lib, "index.json"))
    if not items:
        print("index.json 为空,先执行 topic_lib.py update")
        return 1
    hits = []
    if url:
        n = norm_url(url)
        hits = [it for it in items if norm_url(it["url"]) == n]
        print("URL 查重:", ("命中 " + str(len(hits)) + " 条(已收录,不重复搜索)") if hits else "未收录,可搜索")
    elif keyword:
        hits = [it for it in items if keyword in it["content"] or keyword in it["cat"]]
        print("关键词「" + keyword + "」命中 " + str(len(hits)) + " 条")
    elif cat:
        hits = [it for it in items if it["cat"] == cat]
        print("分类「" + cat + "」共 " + str(len(hits)) + " 条")
    for it in hits[:20]:
        print("  [{d} r{r}] ({t}) {c} | {u}".format(d=it["date"], r=it["rank"],
              t=it["type"], c=it["content"][:50], u=it["url"]))
    if len(hits) > 20:
        print("  ... 共", len(hits), "条")
    return 0


def cmd_rebuild(root):
    lib = os.path.join(root, "话题库")
    items = load_index(os.path.join(lib, "index.json"))
    with io.open(os.path.join(lib, "话题库.md"), "w", encoding="utf-8") as f:
        f.write(rebuild_md(items))
    print("已从 index.json 重建 md,共", len(items), "条")


def main():
    ap = argparse.ArgumentParser(description="话题库双轨维护(index.json + 话题库.md)")
    sub = ap.add_subparsers(dest="cmd")
    u = sub.add_parser("update")
    u.add_argument("--root", required=True)
    u.add_argument("--date", required=True)
    s = sub.add_parser("search")
    s.add_argument("--root", required=True)
    s.add_argument("--url")
    s.add_argument("--keyword")
    s.add_argument("--cat")
    r = sub.add_parser("rebuild")
    r.add_argument("--root", required=True)
    a = ap.parse_args()
    if a.cmd == "update":
        cmd_update(a.root, a.date)
    elif a.cmd == "search":
        return cmd_search(a.root, a.url, a.keyword, a.cat)
    elif a.cmd == "rebuild":
        cmd_rebuild(a.root)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
