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


def normalize(data, n, warnings, errors):
    items = data.get("items")
    if not isinstance(items, list) or not items:
        errors.append(f"rank_{n}: items 缺失或为空")
        items = []

    norm_items = []
    type_count = {}
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            errors.append(f"rank_{n}: items[{i}] 不是对象")
            continue
        missing = [k for k in ("type", "content", "url", "note") if not it.get(k)]
        if missing:
            errors.append(f"rank_{n}: items[{i}] 缺字段 {missing}")
        t = it.get("type")
        if t not in TYPES:
            errors.append(f"rank_{n}: items[{i}] type 非法: {t!r} (应为 案例/人物/链路)")
        else:
            type_count[t] = type_count.get(t, 0) + 1
        url = str(it.get("url") or "")
        if not url.startswith("http"):
            errors.append(f"rank_{n}: items[{i}] url 异常: {url!r}")
        content = str(it.get("content") or "")
        if content and not (LEN_WARN[0] <= len(content) <= LEN_WARN[1]):
            warnings.append(f"rank_{n}: items[{i}] content 长度 {len(content)} 字(建议 {LEN_WARN[0]}-{LEN_WARN[1]})")
        norm_items.append({"type": t, "content": content, "url": url, "note": str(it.get("note") or "")})

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
        "items": norm_items,
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
        for it in block["items"]:
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
        stats.append((k, len(b["items"]), tc, b["category"], bool(b["thinking"])))

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
    print(f"[OK] extension.json 写出: {out}")
    print(f"     {len(ext)} 个 rank, {total} 条 items, {len(url_owner)} 个唯一 URL, {len(dups)} 条跨 rank 复用")
    for k, cnt, tc, cat, has_th in stats:
        print(f"     rank{k}: {cnt} 条 {tc} | {cat} | thinking {'有' if has_th else '缺'}")
    print("     下一步: python scripts/topic_lib.py update --root <ROOT> --date <D>")


if __name__ == "__main__":
    main()
