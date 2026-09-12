# -*- coding: utf-8 -*-
"""话题库维护:index.json(机读,唯一数据源) + 话题库.md(人读,派生物) + index.sqlite(加速索引,派生物)

数据模型(见 contract 的 LIB_* 常量):
  · 聚合维度到 type(案例/人物/链路) —— 3 个稳定取值, 全局一级索引;
  · cat 走受控词表(contract.LIB_CATS), 仅作二级标签;
  · date(首次收录)/last_seen(最近命中)只是条目属性, **不用时间做区隔** —— 一条 url 只一行。

用法:
  python topic_lib.py update  --root <ROOT> --date YYYY-MM-DD   # 增量收录 extension.json → 重建 md/sqlite
  python topic_lib.py search  --root <ROOT> [--url U | --type T | --cat C | --entity E | --keyword K]
                              [--since D] [--until D] [--json]
  python topic_lib.py rebuild --root <ROOT>                     # 从 index.json 重建 md
  python topic_lib.py reindex --root <ROOT>                     # 从 index.json 重建 sqlite 加速索引
  python topic_lib.py prune   --root <ROOT>                     # 全库一致性扫描(移除 url 已不在任何 extension.json 的条目)
"""
import argparse
import difflib
import io
import json
import os
import re
import sqlite3
import sys

import contract   # 数据契约:文件名 / 字段 / 值域的单一定义处

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ────────────────────────────── 读写与字段规整 ──────────────────────────────

def load_lib(path):
    """返回 (schema, items)。容忍旧格式(裸 {"items": [...]} 或裸数组)。"""
    if not os.path.exists(path):
        return contract.LIB_SCHEMA, []
    with io.open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, list):
        return 1, d
    return d.get("schema") or 1, d.get("items", [])


def atomic_write(path, text):
    """先写 .tmp 再 os.replace —— update 是全量重写, 写一半崩掉会毁库。"""
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def save_lib(path, items):
    atomic_write(path, json.dumps({"schema": contract.LIB_SCHEMA, "items": items},
                                  ensure_ascii=False, indent=1))


def norm_url(u):
    """去重键: 与 contract.canon_url 同源(去掉 ?/# 之后内容并去尾斜杠)。"""
    return contract.canon_url(u)


def cat_norm(raw):
    """自由文本 cat → 受控词。返回 (规范值, 是否命中词表)。"""
    c = (raw or "").strip()
    if c in contract.LIB_CATS:
        return c, True
    if c in contract.LIB_CAT_SYNONYMS:
        return contract.LIB_CAT_SYNONYMS[c], True
    return contract.LIB_CAT_FALLBACK, False


def shingles(text, n=3):
    """3-gram 字符集合 —— 中文按字切, 用于相似度比对的预筛。"""
    t = re.sub(r"\s+", "", text or "")
    return {t[i:i + n] for i in range(max(len(t) - n + 1, 0))} or {t}


def norm_item(it):
    """规整成契约字段: 核心字段补空串, 可选字段给默认值。"""
    rec = {k: (it.get(k) or "") for k in contract.LIB_FIELDS}
    rec["entities"] = [str(x) for x in (it.get("entities") or []) if str(x).strip()]
    rec["adopted"] = bool(it.get("adopted", True))
    for k in ("claim", "relation", "claim_source_url", "source_tier", "link_status"):
        rec[k] = it.get(k) or ""
    rec["corroborated"] = bool(it.get("corroborated")) or bool(
        ((it.get("corroboration") or {}).get("groups") or 0) >= contract.EXT_CORROBORATION_MIN)
    return rec


def normalize_items(items):
    return [norm_item(it) for it in items]


def item_key(it):
    return norm_url(it.get("url", ""))


# ────────────────────────────── 日期回填 / 同类体检 ──────────────────────────────

def scan_extensions(root):
    """扫所有 raw/<D>/extension.json → {norm_url: {"first":最早, "last":最近, "item":条目}}。

    item 用于回填论证层字段(claim/relation)与 entities —— 带 claim 的那份优先。
    """
    raw = os.path.join(root, contract.RAW_DIRNAME)
    seen = {}
    for d in sorted(os.listdir(raw)) if os.path.isdir(raw) else []:
        p = contract.path_extension(root, d)
        if not os.path.exists(p):
            continue
        with io.open(p, "r", encoding="utf-8-sig") as f:
            ext = json.load(f)
        for key in ext:
            block = ext[key] or {}
            for it in list(block.get("items") or []) + list(block.get("dropped") or []):
                u = norm_url(it.get("url", ""))
                if not u:
                    continue
                rec = seen.setdefault(u, {"first": d, "last": d, "item": it})
                rec["first"] = min(rec["first"], d)
                rec["last"] = max(rec["last"], d)
                if it.get("claim") and not rec["item"].get("claim"):
                    rec["item"] = it
    return seen


def backfill_dates(root, items):
    """补 date(首次收录)/last_seen(最近命中), 并回填论证层字段与 entities。

    时间只作属性, 不参与去重与分区; claim/relation/entities 让跨天复用不只停留在"事实"层面。
    """
    seen = scan_extensions(root)
    n_date = n_last = n_opt = 0
    for it in items:
        rec = seen.get(item_key(it))
        if not rec:
            continue
        if not it.get("date") and rec["first"]:
            it["date"] = rec["first"]
            n_date += 1
        if rec["last"] and rec["last"] != it.get("last_seen"):
            it["last_seen"] = rec["last"]
            n_last += 1
        src = rec["item"]
        for k in ("claim", "relation", "claim_source_url", "source_tier", "link_status"):
            if not it.get(k) and src.get(k):
                it[k] = src[k]
                n_opt += 1
        if not it.get("corroborated") and src.get("corroboration"):
            if (src["corroboration"].get("groups") or 0) >= contract.EXT_CORROBORATION_MIN:
                it["corroborated"] = True
                n_opt += 1
        if not it.get("entities") and src.get("entities"):
            it["entities"] = [str(x) for x in src["entities"] if str(x).strip()]
            n_opt += 1
    return n_date, n_last, n_opt


def similar_pairs(items, new_items, ratio_threshold, prefilter=contract.LIB_SHINGLE_JACCARD):
    """「疑似同类」体检: 同 type 内内容高度重叠的条目对。

    url 去重挡不住「同一件事被两个来源分别报道」。为避免 O(新增×存量) 次 difflib 全对比,
    先用 3-gram Jaccard 预筛(Jaccard < prefilter 直接跳过), 再对候选算序列相似度。
    只告警不自动合并 —— 是否算同一类由 Agent 按收敛性判断第 4 条裁定。
    """
    out = []
    by_type = {}
    for it in items:
        rec = (shingles(it.get("content")), it)
        by_type.setdefault(it.get("type") or "", []).append(rec)
    for n in new_items:
        ns = shingles(n.get("content"))
        for os_, o in by_type.get(n.get("type") or "", []):
            if not ns or not os_:
                continue
            j = len(ns & os_) / len(ns | os_)
            if j < prefilter:
                continue
            r = difflib.SequenceMatcher(None, n.get("content") or "", o.get("content") or "").ratio()
            if r >= ratio_threshold:
                out.append((round(r, 2), n, o))
    return out


# ────────────────────────────── 人读视图 ──────────────────────────────

def rebuild_md(items):
    """一级按 type(全局唯一索引), 二级按 cat(仅展示层父子)。"""
    gfield = contract.LIB_GROUP_FIELD
    groups = []
    for it in items:
        g = it.get(gfield) or "未分类"
        if g not in groups:
            groups.append(g)
    out = [
        "# 话题库(跨日期累积)", "",
        "机读索引: index.json(schema %d, url 唯一键去重)。加速索引: index.sqlite(FTS5/trigram, 派生物)。"
        % contract.LIB_SCHEMA,
        "维护: `topic_lib.py update / search / rebuild / reindex / prune`(见 skill scripts)。",
        "**筛选维度**: type(一级, %s)——全局唯一索引; cat(二级, 受控词表); "
        "entity(主体); date/last_seen(时间属性, 不分区)。" % " / ".join(contract.EXT_TYPES),
        "发散搜索前查重: 同一主题不重复搜索、同一类型案例 ≤3、已收录条目不重复收录。",
        "共 %d 条(%s) | %s" % (
            len(items),
            "含 %d 条未采用(adopted=false)" % sum(1 for x in items if not x.get("adopted"))
            if any(not x.get("adopted") for x in items) else "全部已采用",
            " / ".join("%s %d" % (g, sum(1 for x in items if (x.get(gfield) or "未分类") == g))
                       for g in groups)), ""]
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
            out.append("| 收录 | 最近 | 内容要点 | 来源 url |")
            out.append("|---|---|---|---|")
            for it in sub:
                t = it["content"] if len(it["content"]) <= 58 else it["content"][:58] + "…"
                if not it.get("adopted"):
                    t = "（未采用，仅备查）" + t
                out.append("| {d} | {l} | {c} | {u} |".format(
                    d=it.get("date") or "-", l=it.get("last_seen") or "-", c=t, u=it["url"]))
            out.append("")
    return "\n".join(out)


def parse_md(md_text):
    """从旧版话题库.md 解析条目(一次性迁移用)。旧表含 日期/rank 列, 迁移时丢弃 rank。"""
    items, cat = [], None
    for line in md_text.splitlines():
        if line.startswith("## "):
            cat = re.sub(r"[（(].*$", "", line[3:].strip()).strip()
        elif line.startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells[0] in ("日期", "类型", "收录", "---") or set(cells[0]) == {"-"}:
                continue
            if len(cells) >= 5:
                items.append({"date": cells[0], "type": cells[2], "cat": cat,
                              "content": cells[3], "url": cells[4]})
            elif len(cells) == 4:
                items.append({"date": cells[0], "type": cells[1] if cells[1] in contract.EXT_TYPES else "",
                              "cat": cat, "content": cells[2], "url": cells[3]})
            elif len(cells) == 3:
                items.append({"type": cells[0], "cat": cat, "content": cells[1], "url": cells[2]})
    for it in items:
        if not it.get("type"):
            it["type"] = "案例"
    return items


# ────────────────────────────── SQLite 加速索引(派生物) ──────────────────────────────

def sqlite_path(root):
    return os.path.join(contract.lib_dir(root), contract.LIB_SQLITE)


def build_sqlite(root, items, src_path):
    """从 index.json 重建加速索引。FTS5 用 trigram 分词 —— 中文子串检索必须用它
    (unicode61 会把整段中文当成一个词, 「洗衣机」查不到「家用洗衣机」, 实测 0 命中)。"""
    p = sqlite_path(root)
    tmp = p + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    try:
        con.executescript("""
            CREATE TABLE entries(
              url TEXT PRIMARY KEY, date TEXT, last_seen TEXT, type TEXT, cat TEXT,
              content TEXT, entities TEXT, adopted INTEGER, claim TEXT, relation TEXT,
              claim_source_url TEXT, source_tier TEXT, corroborated INTEGER, link_status TEXT);
            CREATE INDEX idx_type ON entries(type);
            CREATE INDEX idx_cat ON entries(cat);
            CREATE INDEX idx_dates ON entries(date, last_seen);
            CREATE INDEX idx_tier ON entries(source_tier);
            CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        rows = [(it["url"], it.get("date") or "", it.get("last_seen") or "", it.get("type") or "",
                 it.get("cat") or "", it.get("content") or "", " ".join(it.get("entities") or []),
                 1 if it.get("adopted", True) else 0, it.get("claim") or "",
                 it.get("relation") or "", it.get("claim_source_url") or "",
                 it.get("source_tier") or "", 1 if it.get("corroborated") else 0,
                 it.get("link_status") or "") for it in items]
        con.executemany("INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        try:
            con.execute("CREATE VIRTUAL TABLE fts USING fts5("
                        "url UNINDEXED, content, cat, entities, tokenize='trigram')")
            con.executemany("INSERT INTO fts(url, content, cat, entities) VALUES (?,?,?,?)",
                            [(r[0], r[5], r[4], r[6]) for r in rows])
        except sqlite3.OperationalError as e:      # 无 FTS5: 退化为 LIKE 检索
            print("[WARN] FTS5 不可用(%s), 关键词检索退化为 LIKE" % e)
        st = os.stat(src_path)
        con.execute("INSERT INTO meta VALUES ('src_mtime', ?)", (str(st.st_mtime),))
        con.execute("INSERT INTO meta VALUES ('src_size', ?)", (str(st.st_size),))
        con.execute("INSERT INTO meta VALUES ('schema', ?)", (str(contract.LIB_SCHEMA),))
        con.commit()
    finally:
        con.close()
    os.replace(tmp, p)
    return p


def sqlite_fresh(root, src_path):
    p = sqlite_path(root)
    if not (os.path.exists(p) and os.path.exists(src_path)):
        return False
    try:
        con = sqlite3.connect(p)
        m = dict(con.execute("SELECT k, v FROM meta").fetchall())
        con.close()
    except sqlite3.Error:
        return False
    st = os.stat(src_path)
    return (m.get("src_mtime") == str(st.st_mtime) and m.get("src_size") == str(st.st_size)
            and m.get("schema") == str(contract.LIB_SCHEMA))


def ensure_sqlite(root, items, src_path):
    if not sqlite_fresh(root, src_path):
        build_sqlite(root, items, src_path)
    return sqlite_path(root)


def sqlite_query(root, *, url=None, type_=None, cat=None, keyword=None, entity=None,
                 since=None, until=None, tier=None, include_unadopted=True):
    """用加速索引做筛选; 返回 (rows, mode)。rows 为 dict 列表。"""
    con = sqlite3.connect(sqlite_path(root))
    con.row_factory = sqlite3.Row
    try:
        where, args, mode = [], [], "sqlite"
        if url:
            where.append("e.url = ?")
            args.append(norm_url(url))
        if type_:
            where.append("e.type = ?")
            args.append(type_)
        if cat:
            where.append("e.cat = ?")
            args.append(cat)
        if tier:
            where.append("e.source_tier = ?")
            args.append(tier)
        if since:
            where.append("e.date >= ?")
            args.append(since)
        if until:
            where.append("e.date <= ?")
            args.append(until)
        if not include_unadopted:
            where.append("e.adopted = 1")
        join = ""
        if keyword or entity:
            q = keyword or entity
            if len(q) < 3:                      # trigram 至少要 3 个字符
                like = "%" + q + "%"
                col = "e.content" if keyword else "e.entities"
                where.append("%s LIKE ?" % col)
                args.append(like)
            else:
                try:
                    join = "JOIN fts f ON f.url = e.url"
                    where.append("fts MATCH ?" if keyword else "fts.entities MATCH ?")
                    args.append('"%s"' % q.replace('"', '""'))
                except sqlite3.Error:
                    where.append("e.content LIKE ?")
                    args.append("%" + q + "%")
                    mode = "sqlite+like"
        sql = ("SELECT e.* FROM entries e %s %s ORDER BY e.date DESC, e.type"
               % (join, ("WHERE " + " AND ".join(where)) if where else ""))
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
        return rows, mode
    finally:
        con.close()


# ────────────────────────────── 命令 ──────────────────────────────

def cmd_update(root, date):
    lib = contract.lib_dir(root)
    if not os.path.isdir(lib):
        os.makedirs(lib)
    ip = contract.lib_index(root)
    mp = contract.lib_md(root)
    schema, raw_items = load_lib(ip)
    if not raw_items and os.path.exists(mp):
        with io.open(mp, "r", encoding="utf-8") as f:
            raw_items = parse_md(f.read())
        print("index.json 为空, 已从现有 md 迁移", len(raw_items), "条")
    legacy = sum(1 for it in raw_items if set(it) - set(contract.LIB_FIELDS) - set(contract.LIB_OPT_FIELDS))
    items = normalize_items(raw_items)
    if schema != contract.LIB_SCHEMA or legacy:
        print("字段规整: schema %s -> %s, 规整 %d 条旧条目" % (schema, contract.LIB_SCHEMA, legacy))

    # cat 归一化到受控词表(存量条目也一起迁): 自由文本会持续分叉, 越晚归一越难合
    remapped, to_fallback = {}, set()
    for it in items:
        c, hit = cat_norm(it.get("cat"))
        if c != it.get("cat"):
            remapped[it["cat"]] = c
            it["cat"] = c
        if not hit and it.get("cat") == contract.LIB_CAT_FALLBACK:
            to_fallback.add(it.get("url", ""))
    if remapped:
        print("cat 归一化 %d 类: %s" % (len(remapped),
              ", ".join("%s→%s" % kv for kv in sorted(remapped.items()))))

    ext_path = contract.path_extension(root, date)
    added_items, unadopted, cat_miss = [], 0, set()
    if os.path.exists(ext_path):
        with io.open(ext_path, "r", encoding="utf-8-sig") as f:
            ext = json.load(f)
        seen = {item_key(it): it for it in items}
        added = upgraded = 0
        for key in sorted(ext, key=int):
            block = ext[key] or {}
            cat, hit = cat_norm(block.get("category"))
            if not hit and block.get("category"):
                cat_miss.add(block["category"])
            for it in block.get("items") or []:
                u = item_key(it)
                if not u:
                    continue
                if u in seen:
                    cur = seen[u]
                    if len(it.get("content") or "") > len(cur.get("content") or ""):
                        cur["content"] = it["content"]
                        upgraded += 1
                    cur["last_seen"] = max(cur.get("last_seen") or "", date)
                    continue
                rec = norm_item(dict(it, date=date, last_seen=date, cat=cat, adopted=True))
                items.append(rec)
                seen[u] = rec
                added_items.append(rec)
                added += 1
            # 未采用但值得记录: 不入交付物, 但要入库(adopted=false)以便后续查重命中
            for it in block.get("dropped") or []:
                u = item_key(it)
                if not u or u in seen:
                    continue
                rec = norm_item(dict(it, date=date, last_seen=date, cat=cat, adopted=False))
                items.append(rec)
                seen[u] = rec
                added_items.append(rec)
                unadopted += 1
        print("新增收录 %d 条(其中未采用 %d 条), 内容升级 %d 条" % (added, unadopted, upgraded))
    if cat_miss:
        print("[cat 未命中受控词表 %d 个] 已归入「%s」, 建议扩充 contract.LIB_CATS: %s"
              % (len(cat_miss), contract.LIB_CAT_FALLBACK, ", ".join(sorted(cat_miss))))

    n_date, n_last, n_opt = backfill_dates(root, items)
    if n_date or n_last or n_opt:
        print("回填: 首次收录 %d 条 / 最近命中 %d 条 / 论证层字段(claim·relation·entities) %d 项"
              % (n_date, n_last, n_opt))

    if added_items:
        sus = similar_pairs([it for it in items if it not in added_items], added_items,
                            contract.LIB_SIMILAR_RATIO)
        if sus:
            print("[疑似同类 %d 组] 同 type 内容高度重叠(相似度≥%.2f), 按收敛性判断第 4 条确认是否只留一条:"
                  % (len(sus), contract.LIB_SIMILAR_RATIO))
            for r, n, o in sus[:6]:
                print("  %.2f 新: %s" % (r, n["content"][:46]))
                print("       旧: %s" % o["content"][:46])
                print("       新 %s" % n["url"])
                print("       旧 %s" % o["url"])
        else:
            print("同类体检: 本批新增无高度重叠条目")

    save_lib(ip, items)
    atomic_write(mp, rebuild_md(items))
    build_sqlite(root, items, ip)
    cats = {it["cat"] for it in items}
    print("index.json: %d 条(schema %d) | md + sqlite 已重建 | cat %d 个" % (
        len(items), contract.LIB_SCHEMA, len(cats)))
    return 0


def cmd_search(root, url=None, keyword=None, cat=None, type_=None, entity=None,
               since=None, until=None, tier=None, as_json=False, include_unadopted=True):
    ip = contract.lib_index(root)
    schema, raw_items = load_lib(ip)
    items = normalize_items(raw_items)
    if not items:
        print("index.json 为空,先执行 topic_lib.py update")
        return 1
    ensure_sqlite(root, items, ip)
    rows, mode = sqlite_query(root, url=url, type_=type_, cat=cat, keyword=keyword,
                              entity=entity, since=since, until=until, tier=tier,
                              include_unadopted=include_unadopted)
    if as_json:
        print(json.dumps({"mode": mode, "count": len(rows), "items": rows},
                         ensure_ascii=False, indent=1))
        return 0
    conds = [x for x in (("url=%s" % url) if url else "",
                         ("type=%s" % type_) if type_ else "",
                         ("cat=%s" % cat) if cat else "",
                         ("entity=%s" % entity) if entity else "",
                         ("keyword=%s" % keyword) if keyword else "",
                         ("tier=%s" % tier) if tier else "",
                         ("since=%s" % since) if since else "",
                         ("until=%s" % until) if until else "") if x]
    print("筛选 %s 命中 %d 条 [%s]" % (" ".join(conds) or "(无条件)", len(rows), mode))
    if url:
        print("URL 查重:", "已收录(不重复搜索)" if rows else "未收录,可搜索")
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    if by_type:
        print("  按 type:", by_type)
    for r in rows[:20]:
        flag = "" if r.get("adopted") else "[未采用]"
        print("  [%s|%s] (%s) %s%s | %s" % (r["date"] or "-", r["cat"], r["type"], flag,
                                            r["content"][:50], r["url"]))
    if len(rows) > 20:
        print("  ... 共", len(rows), "条")
    return 0


def cmd_rebuild(root):
    schema, raw_items = load_lib(contract.lib_index(root))
    items = normalize_items(raw_items)
    atomic_write(contract.lib_md(root), rebuild_md(items))
    print("已从 index.json 重建 md,共", len(items), "条")


def cmd_reindex(root):
    ip = contract.lib_index(root)
    schema, raw_items = load_lib(ip)
    items = normalize_items(raw_items)
    p = build_sqlite(root, items, ip)
    print("已重建加速索引:", p, "| 条目", len(items))


def cmd_prune(root):
    """全库一致性扫描: 移除 url 已不在**任何** extension.json(含 dropped)里的条目。"""
    ip, mp = contract.lib_index(root), contract.lib_md(root)
    schema, raw_items = load_lib(ip)
    items = normalize_items(raw_items)
    keep = set(scan_extensions(root).keys())
    if not keep:
        print("扫描到 0 个 extension.json 的保留集合, 已中止(不改动 index.json)")
        return 1
    before = len(items)
    removed = [it for it in items if item_key(it) not in keep]
    items = [it for it in items if item_key(it) in keep]
    save_lib(ip, items)
    atomic_write(mp, rebuild_md(items))
    build_sqlite(root, items, ip)
    print("prune: 保留集合 %d 个 url | 移除 %d 条 | index.json %d -> %d 条 | md + sqlite 已重建"
          % (len(keep), len(removed), before, len(items)))
    for it in removed[:20]:
        print("  - [%s] (%s) %s | %s" % (it["cat"], it["type"], it["content"][:50], it["url"]))
    return 0


def main():
    ap = argparse.ArgumentParser(description="话题库维护(index.json + 话题库.md + index.sqlite)")
    sub = ap.add_subparsers(dest="cmd")
    u = sub.add_parser("update")
    u.add_argument("--root", required=True)
    u.add_argument("--date", required=True)
    s = sub.add_parser("search")
    s.add_argument("--root", required=True)
    s.add_argument("--url")
    s.add_argument("--keyword")
    s.add_argument("--cat", choices=list(contract.LIB_CATS) + [contract.LIB_CAT_FALLBACK])
    s.add_argument("--type", dest="type_", choices=list(contract.EXT_TYPES),
                   help="按一级维度筛选(案例/人物/链路)")
    s.add_argument("--entity", help="按主体筛选(机构/人物/案件名, 需条目带 entities)")
    s.add_argument("--tier", choices=list(contract.EXT_TIER_ORDER),
                   help="按信源等级筛选: A事实性/B待定/C不采信/D观点")
    s.add_argument("--since", help="首次收录日期 >= YYYY-MM-DD")
    s.add_argument("--until", help="首次收录日期 <= YYYY-MM-DD")
    s.add_argument("--json", dest="as_json", action="store_true", help="机读输出")
    s.add_argument("--adopted-only", action="store_true", help="排除未采用条目")
    r = sub.add_parser("rebuild")
    r.add_argument("--root", required=True)
    x = sub.add_parser("reindex")
    x.add_argument("--root", required=True)
    p = sub.add_parser("prune")
    p.add_argument("--root", required=True)
    p.add_argument("--date", default=None, help="已废弃: 一律做全库一致性扫描")
    a = ap.parse_args()
    if a.cmd == "update":
        return cmd_update(a.root, a.date)
    if a.cmd == "search":
        return cmd_search(a.root, a.url, a.keyword, a.cat, a.type_, a.entity,
                          a.since, a.until, a.tier, a.as_json, not a.adopted_only)
    if a.cmd == "rebuild":
        return cmd_rebuild(a.root)
    if a.cmd == "reindex":
        return cmd_reindex(a.root)
    if a.cmd == "prune":
        return cmd_prune(a.root)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
