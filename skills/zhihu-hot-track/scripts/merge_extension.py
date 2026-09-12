# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 热点拓展汇总(Agent Swarm 产出 -> extension.json)。

把各 subagent 产出的 ext_search/<D>/rank_<n>/rank_<n>.json 统一为
raw/<D>/extension.json, 并做 schema 强校验。存在的原因:
  - 各 subagent 的输出格式历史上出现过 3 种变体(顶层嵌套 {"7": {...}}、
    用 divergence_dirs 代替 thinking、缺 category), 主 Agent 每次手写兼容代码既慢又易错;
  - 字段静默丢失会直接让 Excel/HTML 的「思考过程」列为空, 必须显式报错而非默默通过。

用法:
  python merge_extension.py --root <ROOT> --date 2026-09-11
  python merge_extension.py --root <ROOT> --date 2026-09-11 --ranks 1-10
  python merge_extension.py --root <ROOT> --date 2026-09-11 --no-strict   # 只警告不失败

硬校验(失败即退出非 0): 顶层可解析 / items 非空 / 每条 item 含 type+content+url+note /
type 属于 {案例,人物,链路} / 同 rank 同 type ≤3 / url 以 http 开头 / content 非空。
软校验(仅警告): content 长度不在 60-300 字 / thinking 缺失 / category 缺失 /
跨 rank 复用同一 URL(话题库会去重, 但应确认是有意复用)。

输出 raw/<D>/extension.json: {"1": {rank,title,url,items,thinking,category}, ...}
"""
import argparse, io, json, os, re, sys

import contract   # 数据契约:文件名 / 字段 / 值域的单一定义处(见 contract.py)

TYPES = contract.EXT_TYPES
MAX_PER_TYPE = contract.EXT_MAX_PER_TYPE
LEN_WARN = contract.EXT_CONTENT_LEN
RELATIONS = contract.EXT_RELATIONS
EXT_REQUIRED = contract.EXT_REQUIRED

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_ranks(spec):
    """'1-10' / '1,3,5' / None(自动发现) -> [int]"""
    if not spec:
        return None
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


def discover(src):
    """自动发现 rank 目录"""
    ranks = []
    for name in os.listdir(src) if os.path.isdir(src) else []:
        m = re.fullmatch(r"rank_(\d+)", name)
        if m:
            ranks.append(int(m.group(1)))
    return sorted(ranks)


def load_rank(src, n):
    """读取单个 rank 的产出文件, 容忍多种历史格式"""
    d = os.path.join(src, f"rank_{n}")
    cand = [os.path.join(d, f"rank_{n}.json"), os.path.join(d, f"rank_{n:02d}.json")]
    path = next((p for p in cand if os.path.exists(p)), None)
    if path is None:
        others = [f for f in os.listdir(d) if f.lower().endswith(".json")] if os.path.isdir(d) else []
        exact = [f for f in others if re.fullmatch(rf"rank_0*{n}\.json", f)]
        if exact:
            path = os.path.join(d, exact[0])
        else:
            raise FileNotFoundError(f"rank_{n}: 未找到 rank_{n}.json (目录内容: {others or '目录不存在'})")
    with io.open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    # 容忍顶层嵌套 {"7": {...}}
    if isinstance(data, dict) and str(n) in data and "rank" not in data and isinstance(data[str(n)], dict):
        data = data[str(n)]
    if isinstance(data, list):
        raise ValueError(f"rank_{n}: 顶层必须是单个 JSON 对象, 实际是数组")
    if not isinstance(data, dict):
        raise ValueError(f"rank_{n}: 顶层必须是 JSON 对象, 实际是 {type(data).__name__}")
    return data, path


def check_item(it, n, where, old):
    """校验单条证据, 返回规范化后的 dict(或 None 表示结构性错误)。"""
    if not isinstance(it, dict):
        old.append(f"rank_{n}: {where} 不是对象")
        return None
    missing = [k for k in EXT_REQUIRED if not it.get(k)]
    if missing:
        old.append(f"rank_{n}: {where} 缺字段 {missing}")
    t = it.get("type")
    if t not in TYPES:
        old.append(f"rank_{n}: {where} type 非法: {t!r} (应为 案例/人物/链路)")
    url = str(it.get("url") or "")
    if not url.startswith("http"):
        old.append(f"rank_{n}: {where} url 异常: {url!r}")
    content = str(it.get("content") or "")
    if content and not (LEN_WARN[0] <= len(content) <= LEN_WARN[1]):
        old.append(f"rank_{n}: {where} content 长度 {len(content)} 字(建议 {LEN_WARN[0]}-{LEN_WARN[1]})")
    rel = str(it.get("relation") or "").strip()
    if rel and rel not in RELATIONS:
        old.append(f"rank_{n}: {where} relation 非法: {rel!r} (应为 印证/反驳/边界)")
    return {"type": t, "content": content, "url": url, "note": str(it.get("note") or ""),
            "relation": rel, "claim": ""}


def normalize_chains(chains, n, warnings, errors):
    """校验链式结构: 每条链 = 想法 + 证据[≥1] + 落点, 证据逐条带 relation。"""
    norm = []
    for ci, ch in enumerate(chains, 1):
        if not isinstance(ch, dict):
            errors.append(f"rank_{n}: chains[{ci}] 不是对象")
            continue
        claim = str(ch.get("claim") or "").strip()
        takeaway = str(ch.get("takeaway") or "").strip()
        ev = ch.get("evidence")
        if not claim:
            errors.append(f"rank_{n}: chains[{ci}] 缺 claim(想法)")
        if not isinstance(ev, list) or not ev:
            errors.append(f"rank_{n}: chains[{ci}] 缺 evidence(证据列表为空)")
            ev = []
        if not takeaway:
            warnings.append(f"rank_{n}: chains[{ci}] 缺 takeaway(落点, HTML 会少一行结论)")
        # 想法出处(可选): 提炼该想法的回答 → 附链接与序号, 便于读者回原答核对
        src = ch.get("source")
        norm_src = None
        if isinstance(src, dict) and str(src.get("url") or "").startswith("http"):
            norm_src = {"answer_index": src.get("answer_index"),
                        "likes": src.get("likes"),
                        "url": str(src["url"])}
        elif src:
            warnings.append(f"rank_{n}: chains[{ci}].source 格式不对(应为 "
                            f"{{\"answer_index\":N,\"likes\":N,\"url\":\"http...\"}}), 已忽略")
        evs = []
        for i, it in enumerate(ev, 1):
            v = check_item(it, n, f"chains[{ci}].evidence[{i}]", errors)
            if v is None:
                continue
            if not v["relation"]:
                v["relation"] = contract.EXT_RELATION_DEFAULT
                warnings.append(f"rank_{n}: chains[{ci}].evidence[{i}] 未标 relation, 默认「{v['relation']}」")
            v["claim"] = claim
            if norm_src:
                v["claim_source_url"] = norm_src["url"]      # 透传给展平后的证据, 供话题库入库
            evs.append(v)
        norm.append({"claim": claim, "takeaway": takeaway, "evidence": evs, "source": norm_src})
    return norm


def normalize_dropped(dropped, n, warnings, errors):
    """未采用但值得记录: 被「同类案例只取一条」收敛掉的案例。

    不进 items(因此不进 Excel/HTML), 但会写进 extension.json 的 `dropped`, 由
    topic_lib 以 adopted=false 入库 —— 这样后续发散查重能命中「已知同类、已判定不采用」。
    """
    out = []
    for i, it in enumerate(dropped or [], 1):
        if not isinstance(it, dict):
            errors.append(f"rank_{n}: dropped[{i}] 不是对象")
            continue
        missing = [k for k in ("type", "content", "url") if not it.get(k)]
        if missing:
            errors.append(f"rank_{n}: dropped[{i}] 缺字段 {missing}")
            continue
        if it.get("type") not in TYPES:
            errors.append(f"rank_{n}: dropped[{i}] type 非法: {it.get('type')!r}")
            continue
        if not str(it.get("url") or "").startswith("http"):
            errors.append(f"rank_{n}: dropped[{i}] url 异常: {it.get('url')!r}")
            continue
        if not it.get("reason"):
            warnings.append(f"rank_{n}: dropped[{i}] 缺 reason(说明为何归为同类而不单列)")
        out.append({"type": it["type"], "content": str(it["content"]),
                    "url": str(it["url"]), "note": str(it.get("note") or ""),
                    "reason": str(it.get("reason") or "")})
    return out


def normalize(data, n, warnings, errors):
    items = data.get("items")
    chains_raw = data.get("chains")
    chains = []
    if isinstance(chains_raw, list) and chains_raw:
        # 链式(现行格式): items 由 chains 展平得出
        chains = normalize_chains(chains_raw, n, warnings, errors)
        norm_items = [e for c in chains for e in c["evidence"]]
        if isinstance(items, list) and items and len(items) != len(norm_items):
            warnings.append(f"rank_{n}: 同时给了 chains({len(norm_items)} 证据) 与 items({len(items)} 条), "
                            f"以 chains 为准(items 会被展平结果覆盖)")
    else:
        # 扁平(历史格式): 无链结构, 全部证据归为一条未标注想法的链
        if not isinstance(items, list) or not items:
            errors.append(f"rank_{n}: 既没有 chains 也没有 items")
            items = []
        norm_items = []
        for i, it in enumerate(items, 1):
            v = check_item(it, n, f"items[{i}]", errors)
            if v is not None:
                norm_items.append(v)

    type_count = {}
    for it in norm_items:
        if it["type"] in TYPES:
            type_count[it["type"]] = type_count.get(it["type"], 0) + 1
    for t, c in type_count.items():
        if c > MAX_PER_TYPE:
            errors.append(f"rank_{n}: type「{t}」共 {c} 条, 超过上限 {MAX_PER_TYPE}")

    thinking = data.get("thinking") or ""
    if not thinking and data.get("divergence_dirs"):
        # 兼容历史变体: 用 divergence_dirs 合成 thinking
        thinking = "发散方向:" + "、".join(map(str, data["divergence_dirs"]))
        warnings.append(f"rank_{n}: 缺 thinking, 已用 divergence_dirs 合成(建议 subagent 统一用 thinking)")
    if not thinking:
        warnings.append(f"rank_{n}: thinking 缺失(Excel/HTML 的思考过程列将为空)")
    if not data.get("category"):
        warnings.append(f"rank_{n}: category 缺失(话题库将归入未分类)")

    if not data.get("title"):
        errors.append(f"rank_{n}: title 缺失")
    if not str(data.get("url") or "").startswith("http"):
        errors.append(f"rank_{n}: 问题 url 缺失或非法: {data.get('url')!r}")

    return {
        "rank": data.get("rank", n),
        "title": data.get("title", ""),
        "url": data.get("url", ""),
        "chains": chains,
        "items": norm_items,
        "dropped": normalize_dropped(data.get("dropped"), n, warnings, errors),
        "thinking": thinking,
        "category": data.get("category") or "未分类",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--ranks", default=None, help="如 1-10 或 1,3,5; 默认自动发现 rank_* 目录")
    ap.add_argument("--src", default=None, help="拓展产出目录, 默认 <root>/ext_search/<date>")
    ap.add_argument("--out", default=None, help="输出路径, 默认 <root>/raw/<date>/extension.json")
    ap.add_argument("--no-strict", action="store_true", help="硬校验失败也只警告, 仍写出文件")
    ap.add_argument("--force-overwrite", action="store_true",
                    help="--ranks 为子集时也整体重写输出(默认保留未处理 rank 的旧块, 防误覆盖丢失)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    src = args.src or os.path.join(args.root, "ext_search", args.date)
    out = args.out or contract.path_extension(args.root, args.date)
    if not os.path.isdir(src):
        sys.exit(f"[FAIL] 拓展目录不存在: {src}")

    ranks = parse_ranks(args.ranks) or discover(src)
    if not ranks:
        sys.exit(f"[FAIL] 未在 {src} 发现 rank_* 目录")

    warnings, errors, ext = [], [], {}
    url_owner = {}
    for n in ranks:
        try:
            data, path = load_rank(src, n)
        except Exception as e:
            errors.append(f"rank_{n}: 读取失败 - {e}")
            continue
        block = normalize(data, n, warnings, errors)
        ext[str(block["rank"] if isinstance(block["rank"], int) else n)] = block
        for it in list(block["items"]) + list(block.get("dropped") or []):
            url_owner.setdefault(it["url"], []).append(f"rank{n}")

    dups = {u: rs for u, rs in url_owner.items() if len(rs) > 1}
    for u, rs in dups.items():
        warnings.append(f"跨 rank 复用同一 URL({', '.join(rs)}): {u} —— 话题库按 url 去重, 确认是有意复用")

    # 防误覆盖(2026-09-12 实测教训): 若本次只处理部分 rank(--ranks 为子集)而输出文件已存在,
    # 直接整体写出会**丢掉其他 rank 的块**(实测 subagent 自校验跑 --ranks 9-10, 使 extension.json
    # 只剩 3 个 rank)。默认保留输出文件中未处理 rank 的旧块, 除非显式 --force-overwrite。
    if args.ranks and os.path.exists(out) and not args.force_overwrite:
        try:
            with io.open(out, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}
        kept = sorted((k for k in existing if k not in ext),
                      key=lambda x: int(x) if str(x).isdigit() else 0)
        if kept:
            for k in kept:
                ext[k] = existing[k]
            warnings.append("--ranks 为子集: 已保留输出文件中未处理 rank 的旧块 "
                            f"{kept}(整体重写请加 --force-overwrite)")

    stats = []
    for k in sorted(ext, key=lambda x: int(x)):
        b = ext[k]
        tc = {}
        for it in b["items"]:
            tc[it["type"]] = tc.get(it["type"], 0) + 1
        stats.append((k, len(b["items"]), tc, b["category"], bool(b["thinking"]),
                      len(b.get("chains") or []), len(b.get("dropped") or [])))

    if warnings and not args.quiet:
        print(f"[WARN] {len(warnings)} 条警告:")
        for w in warnings:
            print("  -", w)
    if errors:
        print(f"[FAIL] {len(errors)} 条硬校验错误:")
        for e in errors:
            print("  -", e)
        if args.no_strict:
            print("  (--no-strict: 仍然写出文件, 请自行确认后果)")
        else:
            print("  未写出 extension.json。修正后重跑; 或加 --no-strict 强制写出。")
            sys.exit(1)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(ext, f, ensure_ascii=False, indent=1)

    total = sum(len(b["items"]) for b in ext.values())
    n_chain = sum(len(b.get("chains") or []) for b in ext.values())
    n_drop = sum(len(b.get("dropped") or []) for b in ext.values())
    print(f"[OK] extension.json 写出: {out}")
    print(f"     {len(ext)} 个 rank, {total} 条 items, {n_chain} 条发散链, "
          f"{n_drop} 条未采用(adopted=false), {len(url_owner)} 个唯一 URL, {len(dups)} 条跨 rank 复用")
    for k, cnt, tc, cat, has_th, nch, ndp in stats:
        print(f"     rank{k}: {nch} 链 / {cnt} 条证据 {tc} | 未采用 {ndp} | {cat} | "
              f"thinking {'有' if has_th else '缺'}")
    print("     下一步: python scripts/topic_lib.py update --root <ROOT> --date <D>")


if __name__ == "__main__":
    main()
