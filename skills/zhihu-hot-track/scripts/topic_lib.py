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
    """把任意历史格式的条目规整成契约字段(date 缺失留空, 由 backfill_dates 补)。"""
    return {k: (it.get(k) or "") for k in contract.LIB_FIELDS}


def normalize_items(items):
    return [norm_item(it) for it in items]


def backfill_dates(root, items):
    """给缺 date 的条目补「首次收录日期」——扫所有 raw/<D>/extension.json, 取最早出现的日期。

    时间只是条目属性(见 contract.LIB_FIELDS 说明): 一条 url 只一行, 多日重复出现不重新入库、
    也不覆盖已有 date, 因此「时间」不会把同一条事实切成多份。
    """
    raw = os.path.join(root, contract.RAW_DIRNAME)
    first = {}
    for d in sorted(os.listdir(raw)) if os.path.isdir(raw) else []:
        p = contract.path_extension(root, d)
        if not os.path.exists(p):
            continue
        with io.open(p, "r", encoding="utf-8-sig") as f:
            ext = json.load(f)
        for key in ext:
            for it in ext[key].get("items", []):
                first.setdefault(norm_url(it["url"]), d)
    filled = 0
    for it in items:
        if not it.get("date"):
            d = first.get(norm_url(it["url"]))
            if d:
                it["date"] = d
                filled += 1
    return filled


def similar_pairs(items, new_items, ratio_threshold):
    """入库时的「疑似同类」体检: **同 type 内**内容高度重叠的条目对。

    话题库是「避免重复搜索」的库, 但 url 去重挡不住「同一件事被两个来源分别报道」
    (实测: 同一判决被不同自媒体各写一篇, url 不同、内容几乎一致)。
    按 type(而非 cat)比对: cat 是自由文本、同义分类已出现分叉, 按 cat 比对会漏。
    这里只做**告警不自动合并** —— 是否算同一类由 Agent 判定(见 SKILL.md 收敛性判断第 4 条)。
    """
    import difflib
    out = []
    by_type = {}
    for it in items:
        by_type.setdefault(it.get("type") or "", []).append(it)
    for n in new_items:
        for o in by_type.get(n.get("type") or "", []):
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
    """人读视图: 一级按 type 分组(全局唯一索引), 二级按 cat 分组(仅展示用的父子层)。

    筛选与匹配按**维度**做(见 contract.LIB_GROUP_FIELD): type 是 3 个稳定取值的全局桶,
    cat 是自由文本标签 —— 若把 type 做成 cat 的子节点, 同一维度会被复制 19 份(多次区隔)。
    """
    gfield = contract.LIB_GROUP_FIELD
    groups = []
    for it in items:
        g = it.get(gfield) or "未分类"
        if g not in groups:
            groups.append(g)
    out = ["# 话题库(跨日期累积)", "",
           "机读索引: index.json(url 唯一键去重)。维护: `topic_lib.py update / search / rebuild`(见 skill scripts)。",
           "筛选维度: **type**(一级, %s)——全局唯一索引; **cat**(主题标签, 仅展示层二级分组); "
           "**date**(首次收录日期, 只作属性, 不按日期分桶)。" % " / ".join(contract.EXT_TYPES),
           "发散搜索前查重: 同一主题不重复搜索、同一类型案例 ≤3、已收录条目不重复收录。",
           "共 %d 条 | %s" % (len(items), " / ".join(
               "%s %d" % (g, sum(1 for x in items if (x.get(gfield) or "未分类") == g)) for g in groups)), ""]
    for g in groups:
        rows = [x for x in items if (x.get(gfield) or "未分类") == g]
        out.append("## %s（%d）" % (g, len(rows)))
        out.append("")
        cats = []
        for it in rows:
            c = it.get("cat") or "未分类"
            if c not in cats:
                cats.append(c)
        for c in cats:
            sub = [x for x in rows if (x.get("cat") or "未分类") == c]
            out.append("### %s（%d）" % (c, len(sub)))
            out.append("")
            out.append("| 日期 | 内容要点 | 来源 url |")
            out.append("|---|---|---|")
            for it in sub:
                t = it["content"] if len(it["content"]) <= 58 else it["content"][:58] + "…"
                out.append("| {d} | {c} | {u} |".format(d=it.get("date") or "-", c=t, u=it["url"]))
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
    items = normalize_items(items)
    if legacy:
        print("已按契约字段规整 %d 条旧条目" % legacy)
    filled = backfill_dates(root, items)
    if filled:
        print("已补 %d 条缺失的首次收录日期(date 只作属性, 不影响去重)" % filled)

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
                rec = {"date": date, "type": it["type"], "cat": cat,
                       "content": it["content"], "url": it["url"]}
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


def cmd_search(root, url=None, keyword=None, cat=None, type_=None, since=None, until=None):
    """查重/筛选。维度可组合: --type(一级) + --cat(标签) + --since/--until(时间属性)。

    匹配优先按 type 收窄(3 个稳定值), cat 与日期只做过滤, 因为 cat 是自由文本(同义分叉),
    拿它当路由键会让误判的条目直接失联。
    """
    items = normalize_items(load_index(contract.lib_index(root)))
    if not items:
        print("index.json 为空,先执行 topic_lib.py update")
        return 1
    hits = items
    label = []
    if url:
        n = norm_url(url)
        hits = [it for it in hits if norm_url(it["url"]) == n]
        print("URL 查重:", ("命中 %d 条(已收录,不重复搜索)" % len(hits)) if hits else "未收录,可搜索")
        for it in hits:
            print("  [%s] (%s) %s | %s" % (it.get("date") or "-", it["type"], it["content"][:50], it["url"]))
        return 0
    if type_:
        hits = [it for it in hits if it["type"] == type_]
        label.append("type=%s" % type_)
    if cat:
        hits = [it for it in hits if it["cat"] == cat]
        label.append("cat=%s" % cat)
    if since:
        hits = [it for it in hits if (it.get("date") or "") >= since]
        label.append("since=%s" % since)
    if until:
        hits = [it for it in hits if (it.get("date") or "9999") <= until]
        label.append("until=%s" % until)
    if keyword:
        hits = [it for it in hits if keyword in it["content"] or keyword in it["cat"]]
        label.append("keyword=%s" % keyword)
    print("筛选 %s 命中 %d 条" % (" ".join(label) or "(无条件)", len(hits)))
    by_type = {}
    for it in hits:
        by_type[it["type"]] = by_type.get(it["type"], 0) + 1
    if by_type:
        print("  按 type:", by_type)
    for it in hits[:20]:
        print("  [%s] (%s) %s | %s" % (it.get("date") or "-", it["type"],
                                      it["content"][:50], it["url"]))
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
    s.add_argument("--type", dest="type_", choices=list(contract.EXT_TYPES),
                   help="按一级维度筛选(案例/人物/链路)")
    s.add_argument("--since", help="收录日期 >= YYYY-MM-DD")
    s.add_argument("--until", help="收录日期 <= YYYY-MM-DD")
    r = sub.add_parser("rebuild")
    r.add_argument("--root", required=True)
    p = sub.add_parser("prune")
    p.add_argument("--root", required=True)
    p.add_argument("--date", default=None,
                   help="已废弃(时间只作条目属性): 传入会被忽略, 一律做全库一致性扫描")
    a = ap.parse_args()
    if a.cmd == "update":
        cmd_update(a.root, a.date)
    elif a.cmd == "search":
        return cmd_search(a.root, a.url, a.keyword, a.cat, a.type_, a.since, a.until)
    elif a.cmd == "rebuild":
        cmd_rebuild(a.root)
    elif a.cmd == "prune":
        return cmd_prune(a.root, a.date)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
