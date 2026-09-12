# -*- coding: utf-8 -*-
"""话题库双轨维护:index.json(机读,url 唯一键去重)+ 话题库.md(人读展示,由 index 重建)

用法:
  python topic_lib.py update --root <ROOT> --date YYYY-MM-DD   # 增量收录 extension.json → 重建 md
  python topic_lib.py search --root <ROOT> --url <url>          # URL 查重(收录与否)
  python topic_lib.py search --root <ROOT> --keyword <词>       # 内容/分类关键词命中
  python topic_lib.py search --root <ROOT> --cat <分类>         # 列出某分类全部条目
  python topic_lib.py rebuild --root <ROOT>                     # 从 index.json 重建 md(修复用)
  python topic_lib.py prune --root <ROOT> --date YYYY-MM-DD     # 移除该日期中已不在当日 extension.json 的条目
"""
import argparse
import io
import json
import os
import re
import sys

import contract   # 数据契约:文件名 / 字段 / 值域的单一定义处(见 contract.py)


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


def norm_item(it):
    """把任意历史格式的条目规整成契约字段(丢弃 date/rank 等运行期元数据)。"""
    return {k: (it.get(k) or "") for k in contract.LIB_FIELDS}


def normalize_items(items):
    return [norm_item(it) for it in items]


def similar_pairs(items, new_items, ratio_threshold):
    """入库时的「疑似同类」体检: 同分类内内容高度重叠的条目对。

    话题库是「避免重复搜索」的库, 但 url 去重挡不住「同一件事被两个来源分别报道」
    (实测: 同一判决被不同自媒体各写一篇, url 不同、内容几乎一致)。
    这里只做**告警不自动合并** —— 是否算同一类由 Agent 判定(见 SKILL.md 收敛性判断第 4 条)。
    """
    import difflib
    out = []
    by_cat = {}
    for it in items:
        by_cat.setdefault(it.get("cat") or "", []).append(it)
    for n in new_items:
        for o in by_cat.get(n.get("cat") or "", []):
            r = difflib.SequenceMatcher(None, n.get("content") or "", o.get("content") or "").ratio()
            if r >= ratio_threshold:
                out.append((round(r, 2), n, o))
    return out


def parse_md(md_text):
    """从旧版纯文本话题库.md 解析条目(一次性迁移用)。

    旧表是「日期 | rank | 类型 | 内容要点 | 来源 url」, 迁移时只取后三项 + 当前分类,
    日期与 rank 直接丢弃(见 contract.LIB_FIELDS 的说明)。
    """
    items, cat = [], None
    for line in md_text.splitlines():
        if line.startswith("## "):
            cat = re.sub(r"[（(].*$", "", line[3:].strip()).strip()
        elif line.startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 5 and cells[0] not in ("日期", "---"):
                items.append({"cat": cat, "type": cells[2],
                              "content": cells[3], "url": cells[4]})
            elif len(cells) == 3 and cells[0] not in ("类型", "---"):
                items.append({"cat": cat, "type": cells[0],
                              "content": cells[1], "url": cells[2]})
    return items


def rebuild_md(items):
    cats = []
    for it in items:
        if it["cat"] not in cats:
            cats.append(it["cat"])
    out = ["# 话题库(跨日期累积)", "",
           "机读索引: index.json(url 唯一键去重)。维护: `topic_lib.py update / search / rebuild`(见 skill scripts)。",
           "条目字段: 分类 / 类型 / 内容 / 来源链接(不记日期与榜位 —— 本库用于「这条线索是否已查过」,"
           "收录时间无判定价值)。发散搜索前查重: 同一主题不重复搜索、同一类型案例 ≤3、已收录条目不重复收录。", ""]
    for cat in cats:
        rows = [x for x in items if x["cat"] == cat]
        out.append("## %s（%d）" % (cat, len(rows)))
        out.append("")
        out.append("| 类型 | 内容要点 | 来源 url |")
        out.append("|---|---|---|")
        for it in rows:
            c = it["content"] if len(it["content"]) <= 58 else it["content"][:58] + "…"
            out.append("| {t} | {c} | {u} |".format(t=it["type"], c=c, u=it["url"]))
        out.append("")
    return "\n".join(out)


def cmd_update(root, date):
    lib = contract.lib_dir(root)
    if not os.path.isdir(lib):
        os.makedirs(lib)
    ip, mp = contract.lib_index(root), contract.lib_md(root)
    items = load_index(ip)
    if not items and os.path.exists(mp):
        with io.open(mp, "r", encoding="utf-8") as f:
            items = parse_md(f.read())
        print("index.json 为空,已从现有 md 迁移", len(items), "条")
    legacy = sum(1 for it in items if set(it) - set(contract.LIB_FIELDS))
    items = normalize_items(items)          # 迁移: 丢掉 date/rank 等运行期元数据
    if legacy:
        print("已按新字段规整 %d 条旧条目(丢弃 date/rank)" % legacy)

    ext_path = contract.path_extension(root, date)
    added_items = []
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
                rec = {"cat": cat, "type": it["type"], "content": it["content"], "url": it["url"]}
                items.append(rec)
                seen[n] = rec
                added_items.append(rec)
                added += 1
        print("新增收录", added, "条, 内容升级", upgraded, "条")
    if added_items:
        # url 去重挡不住「同一件事被两个来源分别报道」, 入库时做一次同类体检(只告警)
        sus = similar_pairs([it for it in items if it not in added_items], added_items,
                            contract.LIB_SIMILAR_RATIO)
        if sus:
            print("[疑似同类 %d 组] 内容高度重叠(相似度≥%.2f), 按收敛性判断第 4 条确认是否只留一条:"
                  % (len(sus), contract.LIB_SIMILAR_RATIO))
            for r, n, o in sus[:6]:
                print("  %.2f 新: %s" % (r, n["content"][:46]))
                print("       旧: %s" % o["content"][:46])
                print("       新 %s" % n["url"])
                print("       旧 %s" % o["url"])
        else:
            print("同类体检: 本批新增无高度重叠条目")
    save_index(ip, items)
    with io.open(mp, "w", encoding="utf-8") as f:
        f.write(rebuild_md(items))
    cats = {it["cat"] for it in items}
    print("index.json:", len(items), "条 | 话题库.md 已重建 | 分类:", len(cats), "个:",
          ", ".join(sorted(cats)))


def cmd_search(root, url=None, keyword=None, cat=None):
    items = load_index(contract.lib_index(root))
    if not items:
        print("index.json 为空,先执行 topic_lib.py update")
        return 1
    hits = []
    if url:
        n = norm_url(url)
        hits = [it for it in items if norm_url(it["url"]) == n]
        print("URL 查重:", ("命中 " + str(len(hits)) + " 条(已收录,不重复搜索)") if hits else "未收录,可搜索")
    elif keyword:
        # 子串匹配, 只扫 content 与 cat(库是查重用的, 不做全文检索)
        hits = [it for it in items if keyword in it["content"] or keyword in it["cat"]]
        print("关键词「" + keyword + "」命中 " + str(len(hits)) + " 条")
    elif cat:
        hits = [it for it in items if it["cat"] == cat]
        print("分类「" + cat + "」共 " + str(len(hits)) + " 条")
    for it in hits[:20]:
        print("  [{c}] ({t}) {x} | {u}".format(c=it["cat"], t=it["type"],
              x=it["content"][:50], u=it["url"]))
    if len(hits) > 20:
        print("  ... 共", len(hits), "条")
    return 0


def cmd_prune(root, date=None):
    """全库一致性扫描: 移除 url 已不在**任何**当日 extension.json 里的条目。

    条目不再记日期, 因此无法按日期界定"这条是哪天收的"; 改为以「保留集合 = 所有
    raw/<D>/extension.json 里出现过的 url 并集」判定 —— 只有被后续收敛/合并删掉的
    条目才会被移除, 其余一律保留。重建 md 由本命令自动完成。
    """
    ip, mp = contract.lib_index(root), contract.lib_md(root)
    items = normalize_items(load_index(ip))
    raw = os.path.join(root, contract.RAW_DIRNAME)
    keep, scanned = set(), []
    for d in sorted(os.listdir(raw)) if os.path.isdir(raw) else []:
        ext_path = contract.path_extension(root, d)
        if not os.path.exists(ext_path):
            continue
        scanned.append(d)
        with io.open(ext_path, "r", encoding="utf-8-sig") as f:
            ext = json.load(f)
        for key in ext:
            for it in ext[key].get("items", []):
                keep.add(norm_url(it["url"]))
    if not keep:
        print("扫描到 0 个 extension.json 的保留集合, 已中止(不改动 index.json)")
        return 1
    before = len(items)
    removed = [it for it in items if norm_url(it["url"]) not in keep]
    items = [it for it in items if norm_url(it["url"]) in keep]
    save_index(ip, items)
    with io.open(mp, "w", encoding="utf-8") as f:
        f.write(rebuild_md(items))
    print("prune: 扫描 %s 的 extension.json(%d 天) | 保留集合 %d 个 url | "
          "移除 %d 条 | index.json %d -> %d 条 | md 已重建"
          % (contract.RAW_DIRNAME, len(scanned), len(keep), len(removed), before, len(items)))
    for it in removed[:20]:
        print("  - [{c}] ({t}) {x} | {u}".format(c=it["cat"], t=it["type"],
              x=it["content"][:50], u=it["url"]))
    return 0


def cmd_rebuild(root):
    items = load_index(contract.lib_index(root))
    with io.open(contract.lib_md(root), "w", encoding="utf-8") as f:
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
    p = sub.add_parser("prune")
    p.add_argument("--root", required=True)
    p.add_argument("--date", default=None,
                   help="已废弃(条目不再记日期): 传入会被忽略, 一律做全库一致性扫描")
    a = ap.parse_args()
    if a.cmd == "update":
        cmd_update(a.root, a.date)
    elif a.cmd == "search":
        return cmd_search(a.root, a.url, a.keyword, a.cat)
    elif a.cmd == "rebuild":
        cmd_rebuild(a.root)
    elif a.cmd == "prune":
        return cmd_prune(a.root, a.date)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
