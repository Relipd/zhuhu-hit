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
    # entities(主体锚点, 供话题库 --entity 检索): 2026-09-13 修 —— 这里原先把返回值写死成
    # 固定 6 个键, **subagent 就算填了 entities 也会被静默丢掉**(与"没人填"叠加, 使该字段
    # 在实测中 0 条落库、--entity 检索彻底失效)。现原样保留并做规范化。
    ents = it.get("entities")
    if isinstance(ents, str):
        ents = [ents]
    ents = [str(x).strip() for x in (ents or []) if str(x).strip()][:contract.EXT_ENTITY_MAX]
    out = {"type": t, "content": content, "url": url, "note": str(it.get("note") or ""),
           "relation": rel, "claim": ""}
    if ents:
        out["entities"] = ents
    return out


def strip_label(text, labels=("落点", "想法", "结论")):
    """剥掉字段开头被照抄的标签前缀(『落点：』『想法：』…)。

    实测 2026-09-12(rank 21 单问题追加): subagent 把 schema 示例里的「落点：」当内容写进
    takeaway, 而 HTML 渲染时又加一次「落点：」→ 交付物出现「落点：落点：…」;
    note 也被写成「标「边界」：…」这种把 relation 说明当正文的形式。入库统一剥离, 只留正文。
    """
    t = (text or "").strip()
    for label in labels:
        m = re.match(r"^%s(?:\s*\d+)?\s*[：:]\s*" % re.escape(label), t)
        if m:
            return t[m.end():].strip()
    return t


def strip_note_label(note):
    """note 开头若是把 relation 说明当正文(「标「边界」：…」「标「印证」并给出机制锚点：…」), 剥掉前缀。

    实测 2026-09-12(rank 21): 7 条 note 被写成 schema 自述。模式要允许 relation 与冒号之间夹字,
    例如「标「印证」并给出机制锚点：」——第一版只匹配紧邻冒号, 漏掉了这一条。
    """
    t = (note or "").strip()
    m = re.match(r"^[（(]?\s*标\s*[「『\"']?(印证|反驳|边界)[」』\"']?[^：:]{0,24}[：:]\s*", t)
    if m:
        rest = t[m.end():].strip().rstrip("）)").strip()
        return rest or t
    m2 = re.match(r"^[（(]?\s*标\s*[「『\"']?(印证|反驳|边界)[」』\"']?\s*", t)
    if m2:
        rest = t[m2.end():].strip()
        return rest or t
    return t


def normalize_chains(chains, n, warnings, errors):
    """校验链式结构: 每条链 = 想法 + 证据[≥1] + 落点, 证据逐条带 relation。"""
    norm = []
    n_note_fixed = []
    for ci, ch in enumerate(chains, 1):
        if not isinstance(ch, dict):
            errors.append(f"rank_{n}: chains[{ci}] 不是对象")
            continue
        claim = strip_label(str(ch.get("claim") or ""), ("想法", "回答区判断", "判断"))
        takeaway = strip_label(str(ch.get("takeaway") or ""), ("落点", "结论", "说明"))
        if str(ch.get("claim") or "").strip() != claim:
            warnings.append(f"rank_{n}: chains[{ci}].claim 开头带了「想法：」类前缀, 已剥离")
        if str(ch.get("takeaway") or "").strip() != takeaway:
            warnings.append(f"rank_{n}: chains[{ci}].takeaway 开头带了「落点：」类前缀, 已剥离"
                            f"(否则交付物会显示成「落点：落点：」)")
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
            if strip_note_label(v["note"]) != v["note"]:
                v["note"] = strip_note_label(v["note"])
                n_note_fixed.append(f"rank_{n} chains[{ci}].evidence[{i}]")
            if norm_src:
                v["claim_source_url"] = norm_src["url"]      # 透传给展平后的证据, 供话题库入库
            evs.append(v)
        norm.append({"claim": claim, "takeaway": takeaway, "evidence": evs, "source": norm_src})
    if n_note_fixed:
        warnings.append("note 开头写成了 schema 自述(「标XX：」), 已剥离前缀: "
                        + ", ".join(n_note_fixed[:5])
                        + (" 等 %d 处" % len(n_note_fixed) if len(n_note_fixed) > 5 else ""))
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
        d_ents = it.get("entities")
        if isinstance(d_ents, str):
            d_ents = [d_ents]
        d_ents = [str(x).strip() for x in (d_ents or []) if str(x).strip()][:contract.EXT_ENTITY_MAX]
        rec = {"type": it["type"], "content": str(it["content"]),
               "url": str(it["url"]), "note": strip_note_label(str(it.get("note") or "")),
               "reason": str(it.get("reason") or "")}
        if d_ents:
            rec["entities"] = d_ents
        out.append(rec)
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

    # type 上限**只统计链内证据**(norm_items = chains 展平), dropped 不计入 ——
    # 实测 2026-09-13 有两个 subagent 误以为 dropped 也被计入, 于是把该留档的同类案例塞进
    # thinking、并连续失败 4 轮。故错误信息里直接点名"仅链内证据"并给出超限项落在哪几条链,
    # 让子 agent 不必猜(它自己数的口径容易把 dropped 一起数进去)。
    type_count, type_where = {}, {}
    for it in norm_items:
        if it["type"] in TYPES:
            type_count[it["type"]] = type_count.get(it["type"], 0) + 1
    for ci, ch in enumerate(chains, 1):
        for e in ch["evidence"]:
            if e["type"] in TYPES:
                type_where.setdefault(e["type"], []).append("chains[%d]" % ci)
    for t, c in type_count.items():
        if c > MAX_PER_TYPE:
            errors.append(f"rank_{n}: type「{t}」共 {c} 条, 超过上限 {MAX_PER_TYPE}"
                          f" —— 仅统计**链内证据**(chains[].evidence), dropped 与 thinking 都不计入; "
                          f"本 rank 的「{t}」落在 {', '.join(type_where.get(t, []))}, "
                          f"请把同类证据合并进已有条目、或改写进 dropped(in adopted=false 备查)")

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


def check_source_alignment(ext, root, date, warnings):
    """对账 chains[].source 与 answers_summary.json(2026-09-13 新增)。

    为什么需要: 实测 rank_3 与 rank_6 **各自独立**发现旧版所有链的 `source.answer_index`
    与 `likes` 错配(把低赞回答挂在别的序号上) —— 症状隐蔽: likes 对得上**某一条**回答、
    index 却对不上, 单看 JSON 看不出来。链的「想法出处」会被渲染成可点击的原答链接,
    序号错了读者点过去会看到另一条回答, 所以必须机器对账。
    只告警不失败(属元数据, 不阻塞交付)。
    """
    p = contract.path_answers(root, date)
    if not os.path.exists(p):
        return
    try:
        with io.open(p, encoding="utf-8-sig") as f:
            summary = {str(s["rank"]): s for s in json.load(f)}
    except Exception:
        return
    for rk, blk in ext.items():
        s = summary.get(str(rk))
        if not s:
            continue
        ans = s.get("answers") or []
        for ci, ch in enumerate(blk.get("chains") or [], 1):
            src = ch.get("source") or {}
            idx = src.get("answer_index")
            if not isinstance(idx, int) or not (1 <= idx <= len(ans)):
                warnings.append(f"rank_{rk}: chains[{ci}].source.answer_index={idx!r} 越界"
                                f"(该 rank 共 {len(ans)} 条回答)")
                continue
            real = ans[idx - 1]
            if src.get("likes") != real.get("likes"):
                warnings.append(f"rank_{rk}: chains[{ci}].source.likes={src.get('likes')!r} "
                                f"与第 {idx} 条回答实际 {real.get('likes')!r} 不符(出处指错了回答)")
            u1 = contract.canon_url(src.get("url") or "")
            u2 = contract.canon_url(real.get("url") or "")
            if u1 and u2 and u1 != u2 and "/answer/" in u1 and "/answer/" in u2:
                warnings.append(f"rank_{rk}: chains[{ci}].source.url 与第 {idx} 条回答不是同一条")


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
    # 只读校验(2026-09-13 新增): 给 subagent 用的权威校验器 —— 原来它们只能自己写脚本自查,
    # 实测自写的校验器会漏判(3 个 rank 自报合规, 实际 5 处硬错误), 而 merge_extension 又因
    # 子集运行会覆盖输出而不能让它们跑。--lint 只校验、绝不写文件, 单 rank 也能安全跑。
    ap.add_argument("--lint", action="store_true",
                    help="只校验不写出(可配 --ranks 单跑一个 rank); 有硬错误则退出码 1")
    ap.add_argument("--no-verify", action="store_true",
                    help="跳过事实性复核(信源等级/多源印证/链接探活), 只汇总")
    ap.add_argument("--no-links", action="store_true", help="复核时跳过链接探活(不联网)")
    ap.add_argument("--link-delay", type=float, default=contract.EXT_LINK_DELAY,
                    help="链接探活间隔秒")
    args = ap.parse_args()

    src = args.src or os.path.join(args.root, "ext_search", args.date)
    out = args.out or contract.path_extension(args.root, args.date)
    if not os.path.isdir(src):
        sys.exit(f"[FAIL] 拓展目录不存在: {src}")

    ranks = parse_ranks(args.ranks) or discover(src)
    if not ranks:
        sys.exit(f"[FAIL] 未在 {src} 发现 rank_* 目录")

    warnings, errors, ext = [], [], {}
    url_owner, url_content = {}, {}
    for n in ranks:
        try:
            data, path = load_rank(src, n)
        except Exception as e:
            errors.append(f"rank_{n}: 读取失败 - {e}")
            continue
        block = normalize(data, n, warnings, errors)
        ext[str(block["rank"] if isinstance(block["rank"], int) else n)] = block
        for it in list(block["items"]) + list(block.get("dropped") or []):
            # 必须用 canon_url 归一键: 实测澎湃占位链接一条带 query、一条不带, 用原始 url 分组
            # 就看不出"同一 url 多条不同内容"(而那正是复核按 url 串标的诱因)。
            u = contract.canon_url(it["url"])
            url_owner.setdefault(u, set()).add(f"rank{n}")
            url_content.setdefault(u, {}).setdefault(it.get("content") or "", set()).add(f"rank{n}")
        n_ev = len(block["items"])
        n_ent = sum(1 for it in block["items"] if it.get("entities"))
        if n_ev and n_ent < n_ev * 0.5:
            warnings.append(f"rank_{n}: {n_ev - n_ent}/{n_ev} 条证据缺 entities"
                            f"(话题库 --entity 检索将失效; 复核阶段会按主体形态兜底自动抽取)")

    # 同一 url 被多个 rank 复用: 可接受(有时一条来源同时支撑两处论点), 话题库按 url 去重
    dups = {u: sorted(rs) for u, rs in url_owner.items() if len(rs) > 1}
    for u, rs in dups.items():
        warnings.append(f"跨 rank 复用同一 URL({', '.join(rs)}): {u} —— 话题库按 url 去重, 确认是有意复用")
    # 链的「想法出处」与原答对账(2026-09-13: rank_3/rank_6 各自发现 answer_index 与 likes 错配)
    check_source_alignment(ext, args.root, args.date, warnings)
    # 同一 url 挂**多条不同 content**(2026-09-13 新增检查): 这不是"复用", 而是把占位/重定向链接
    # 当来源。危害有二: ① 事实性复核若按 url 缓存结论会互相串标(实测澎湃 wifiKey_detail.jsp 占位
    # 链接被 3 个 rank 的 6 条无关证据共用); ② 话题库按 url 去重会把不同事实压成一条。
    same_url_multi = {u: c for u, c in url_content.items() if len(c) > 1}
    for u, c in same_url_multi.items():
        where = sorted({r for rs in c.values() for r in rs})
        warnings.append(f"同一 URL 挂了 {len(c)} 条不同 content({', '.join(where)}): {u} "
                        f"—— 疑似占位/重定向链接, 请各用各自原始链接")

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

    if args.lint:                      # 只读模式: 任何情况下都不写文件
        print("[LINT] %s: %d 警告 / %d 错误 (%d 个 rank) —— 未写出任何文件" % (
            "通过" if not errors else "未通过", len(warnings), len(errors), len(ext)))
        sys.exit(1 if errors else 0)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(ext, f, ensure_ascii=False, indent=1)

    total = sum(len(b["items"]) for b in ext.values())
    n_chain = sum(len(b.get("chains") or []) for b in ext.values())
    n_drop = sum(len(b.get("dropped") or []) for b in ext.values())
    print(f"[OK] extension.json 写出: {out}")
    # 口径(2026-09-13 修): items 是 chains 的**展平镜像**(同一份内容两个对象, 见坑 39),
    # 旧输出把两者相加报出「183 条证据」, 而真实独立证据只有 items + dropped = 112 条。
    print(f"     {len(ext)} 个 rank, {n_chain} 条发散链, 独立证据 {total + n_drop} 条"
          f"(链内 {total} + 未采用 {n_drop}; items 为链内镜像不另计), "
          f"{len(url_owner)} 个唯一 URL, {len(dups)} 条跨 rank 复用, "
          f"{len(same_url_multi)} 条同 URL 多内容")
    for k, cnt, tc, cat, has_th, nch, ndp in stats:
        print(f"     rank{k}: {nch} 链 / {cnt} 条证据 {tc} | 未采用 {ndp} | {cat} | "
              f"thinking {'有' if has_th else '缺'}")
    print("     下一步: python scripts/topic_lib.py update --root <ROOT> --date <D>")

    # 事实性复核(2026-09-12 与汇总合并, 少一个"忘记执行"的失败点):
    # 必须在 extension.json 写出之后跑 —— 它按 url 给每条证据打信源等级、算多源印证、
    # 探活链接, 并同步写回 items 与 chains[].evidence(交付物读后者)。
    if not args.no_verify:
        try:
            import verify_ext
            if not args.quiet:
                print("\n===== 事实性复核(信源门槛 / 多源印证 / 链接探活) =====")
            verify_ext.run(args.root, args.date, no_links=args.no_links,
                           delay=args.link_delay, quiet=args.quiet)
        except Exception as e:
            print(f"[WARN] 复核未完成({type(e).__name__}: {e}); 汇总结果已写出, "
                  f"可单独跑 verify_ext.py 补齐")
    elif not args.quiet:
        print("     (--no-verify: 已跳过事实性复核)")


if __name__ == "__main__":
    main()
