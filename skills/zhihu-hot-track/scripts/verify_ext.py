# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 发散证据的事实性复核(信源门槛兜底 + 多源印证 + 链接探活)。

为什么需要它
------------
本流程信源集中在知乎, 交付的其实是**「知乎平台公众言论」的事实性提炼**, 不是已核实的事实。
用户 2026-09-12 明令: 匿名口述(如「有从业者对比称, 2000粉博主月入3000-4000元」)
不值得采信, 获取帖子时要有**信源门槛**。

三道复核(全部为后处理, 不增加 subagent 成本):
  1. **信源等级(source_tier)** —— 兜底打标, 不硬拦截(实测纯正则识别具名主体误杀率过高):
       C 匿名归属(不可作事实采信) / D 无锚点(观点)
       A 具名主体+可核锚点 / B 有锚点但未见具名主体
     另一条升级路径: **多源独立印证**可把 B 升到 A。
  2. **多源印证(corroboration)** —— 用当日检索归档池(ext_search/<D>/rank_<N>/rank_0N_*.json),
     按关键数字找同数出现, 并做**同源折叠**(洗稿转载视为同一来源, 3-gram Jaccard ≥ 阈值),
     统计「独立来源组」数。不做折叠的话, 中文自媒体大量转载会让"多源"变成自欺。
  3. **链接探活(link_status)** + **归档核对(in_archive)** —— 链接是否还活着、url 是否真出自检索结果
     (后者把「必须取自搜索结果」这条纪律从 subagent 自述变成脚本强制)。

用法:
  python verify_ext.py --root <ROOT> --date YYYY-MM-DD [--no-links] [--delay 0.4] [--json]

结果就地写回 raw/<D>/extension.json(每条证据/未采用条目的 source_tier/source_kind/
link_status/in_archive/corroboration), 并另写报告 raw/<D>/ext_verify.json。
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

import contract

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

NUM_RE = re.compile(contract.EXT_NUM_UNIT)
EXTRA_RE = re.compile(contract.EXT_ANCHOR_EXTRA)
HEARSAY_RE = re.compile(contract.EXT_HEARSAY)
NAMED_RE = re.compile(contract.EXT_NAMED)
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def host_of(url):
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def source_kind(url):
    h = host_of(url)
    for suf in contract.EXT_OFFICIAL_HOSTS:
        if h.endswith(suf):
            return "官方"
    for suf in contract.EXT_MEDIA_HOSTS:
        if h.endswith(suf):
            return "一手媒体"
    for host, name in contract.EXT_HOST_KINDS:
        if h.endswith(host):
            return name
    return "其他"


def shingles(text, n=3):
    t = re.sub(r"\s+", "", text or "")
    return {t[i:i + n] for i in range(max(len(t) - n + 1, 0))} or {t}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def key_numbers(content):
    """抽出可核数字键。

    两个实测教训(初版翻车):
      · 不能按**裸数字**匹配 —— `60` 会在几百条搜索片段里命中, 印证数直接变成 243 这种垃圾;
        必须用**完整 token**(带单位)去匹配;
      · 不能用 `len(digit)>=2` 过滤 —— 会把「定损4万至5万」的 `4万` 丢掉(那是一等一的锚点)。
    规则: 强单位(金额/百分比)保留 1 位数; 弱单位(台/份/人/岁/楼…)要求 ≥2 位; 纯年份丢弃。
    """
    strong = ("元", "万元", "亿元", "亿美元", "万", "亿", "%", "‰")
    out, seen = [], set()
    for m in NUM_RE.finditer(content or ""):
        token = re.sub(r"\s+", "", m.group(0))
        core = re.sub(r"[^\d.]", "", token)
        unit = token[len(core):] if core else ""
        if not core or YEAR_RE.match(core) and len(core) == 4:
            continue
        ok = (any(unit.startswith(s) for s in strong) and len(core) >= 1) or len(core) >= 2
        # 印证需要"特异数字": 3 位以上, 或强单位(金额/百分比)
        distinctive = len(core) >= 3 or any(unit.startswith(s) for s in strong)
        if ok and core not in seen:
            seen.add(core)
            out.append((token, core, distinctive))
    return out


def load_archive(root, date):
    """当日检索归档池: ext_search/<D>/rank_<N>/rank_0N_*.json 里的原始搜索结果。"""
    base = os.path.join(root, "ext_search", date)
    pool = []
    if not os.path.isdir(base):
        return pool
    for d in sorted(os.listdir(base)):
        if not re.fullmatch(r"rank_\d+", d):
            continue
        sub = os.path.join(base, d)
        for fn in sorted(os.listdir(sub)):
            if not re.fullmatch(r"rank_\d+_\d+\.json", fn):
                continue
            try:
                data = json.load(io.open(os.path.join(sub, fn), encoding="utf-8-sig"))
            except Exception:
                continue
            items = ((data or {}).get("Data") or {}).get("Items") or []
            for it in items:
                u = it.get("Url") or ""
                text = (it.get("Title") or "") + " " + (it.get("ContentText") or "")
                if u:
                    pool.append({"url": u, "host": host_of(u), "text": text})
    return pool


def fold_sources(hits, threshold):
    """同源折叠: 内容 shingle 高度重叠的命中项归为一组(识别洗稿转载)。"""
    clusters = []
    for h in hits:
        hs = shingles(h["text"][:600])
        for c in clusters:
            if jaccard(hs, c["shingles"]) >= threshold:
                c["members"].append(h)
                break
        else:
            clusters.append({"shingles": hs, "members": [h]})
    return clusters


def corroborate(content, pool, threshold):
    """按**完整数字 token** 在归档池里找独立来源组。

    只采信"特异数字"(3 位以上或带金额/百分比单位), 并用同源折叠把洗稿转载合成一个来源。
    返回 (groups, hosts, matched)。
    """
    best = (0, set(), [])
    for token, core, distinctive in key_numbers(content):
        if not distinctive:
            continue
        hits = [p for p in pool if token in p["text"]]
        if not hits:
            continue
        clusters = fold_sources(hits, threshold)
        hosts = {c["members"][0]["host"] for c in clusters}
        if len(clusters) > best[0]:
            best = (len(clusters), hosts, [token])
        elif len(clusters) == best[0] and best[0]:
            best[2].append(token)
    return best


def anchor_count(content):
    """锚点数 = 带单位的数字 + 法规条号/案号。"""
    return len(key_numbers(content)) + len(EXTRA_RE.findall(content or ""))


def tier_of(content, corroborated, named_hint):
    anchors = anchor_count(content)
    hearsay = bool(HEARSAY_RE.search(content or ""))
    named = named_hint or bool(NAMED_RE.search(content or ""))
    if hearsay and not named:
        return "C", anchors, named
    if named and anchors >= contract.EXT_NUM_MIN:
        return "A", anchors, named
    if corroborated and anchors >= contract.EXT_NUM_MIN:
        return "A", anchors, named          # 多源独立印证 → 事实性
    if anchors >= contract.EXT_NUM_MIN:
        return "B", anchors, named
    return "D", anchors, named


def probe(url, cookie):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://www.zhihu.com/",
        **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=contract.EXT_LINK_TIMEOUT) as r:
            return str(r.status)
    except urllib.error.HTTPError as e:
        return "HTTP %d" % e.code
    except Exception as e:
        return type(e).__name__


def main():
    ap = argparse.ArgumentParser(description="发散证据事实性复核(信源门槛兜底/多源印证/链接探活)")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True)
    ap.add_argument("--no-links", action="store_true", help="跳过链接探活(纯本地, 零请求)")
    ap.add_argument("--delay", type=float, default=contract.EXT_LINK_DELAY)
    ap.add_argument("--json", action="store_true", help="只输出机读报告")
    args = ap.parse_args()

    path = contract.path_extension(args.root, args.date)
    if not os.path.exists(path):
        sys.exit("[FAIL] 未找到 %s" % path)
    ext = json.load(io.open(path, encoding="utf-8-sig"))

    pool = load_archive(args.root, args.date)
    pool_urls = {re.sub(r"\?.*$", "", p["url"]).rstrip("/") for p in pool}
    cookie_path = contract.path_cookie(args.root, args.date)
    if not os.path.exists(cookie_path):
        cookie_path = None
        raw = os.path.join(args.root, contract.RAW_DIRNAME)
        for d in sorted(os.listdir(raw), reverse=True) if os.path.isdir(raw) else []:
            c = contract.path_cookie(args.root, d)
            if os.path.exists(c):
                cookie_path = c
                break
    cookie = (io.open(cookie_path, encoding="utf-8-sig").read().strip() if cookie_path else "")

    entries = []
    for rank in sorted(ext, key=int):
        block = ext[rank] or {}
        # 交付物渲染读的是 chains[].evidence, 话题库读的是展平 items —— JSON 往返后二者是不同对象,
        # 因此复核结果必须同时落到两处(实测只标 items 会导致 HTML/Excel 上看不到等级)。
        for it in list(block.get("items") or []) + list(block.get("dropped") or []) + \
                [e for ch in (block.get("chains") or []) for e in (ch.get("evidence") or [])]:
            entries.append(it)

    annotations = {}
    seen_urls = {}
    for it in entries:
        url = it.get("url") or ""
        content = it.get("content") or ""
        key = re.sub(r"\?.*$", "", url).rstrip("/")
        if key not in annotations:
            groups, hosts, matched = corroborate(content, pool, contract.EXT_SHINGLE_FOLD)
            corr = groups >= contract.EXT_CORROBORATION_MIN
            tier, anchors, named = tier_of(content, corr, False)
            annotations[key] = {
                "source_tier": tier,
                "source_tier_label": contract.EXT_SOURCE_TIERS[tier],
                "source_kind": source_kind(url),
                "anchors": anchors,
                "in_archive": key in pool_urls,
                "corroboration": {"groups": groups, "hosts": sorted(hosts)[:5], "matched": matched},
            }
    for it in entries:                      # 同一 url 的展平条目/链内证据/未采用条目共享同一份结论
        it.update(annotations[re.sub(r"\?.*$", "", it.get("url") or "").rstrip("/")])

    tiers, link_stat, in_arch_bad, n_corr = {}, {}, [], 0
    for key, rec in annotations.items():       # 按 url 去重统计(链内证据与展平 items 是同一份结论)
        tiers[rec["source_tier"]] = tiers.get(rec["source_tier"], 0) + 1
        if rec["corroboration"]["groups"] >= contract.EXT_CORROBORATION_MIN:
            n_corr += 1
        if not rec["in_archive"]:
            in_arch_bad.append(key)

    if not args.no_links:
        done = {}
        for it in entries:
            url = it.get("url") or ""
            if url not in done:
                done[url] = probe(url, cookie)
                link_stat[done[url]] = link_stat.get(done[url], 0) + 1
                time.sleep(args.delay)
            it["link_status"] = done[url]
    else:
        for it in entries:
            it.setdefault("link_status", "skipped")

    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(ext, f, ensure_ascii=False, indent=1)

    report = {
        "date": args.date, "total": len(entries),
        "tiers": tiers, "tier_labels": contract.EXT_SOURCE_TIERS,
        "link_status": link_stat if not args.no_links else "skipped",
        "corroborated": n_corr,
        "in_archive_false": sorted(set(in_arch_bad)),
        "archive_pool": len(pool), "cookie": bool(cookie),
    }
    with io.open(os.path.join(contract.day_dir(args.root, args.date), "ext_verify.json"),
                 "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    print("复核 %d 条证据 | 归档池 %d 条原始结果 | cookie %s" % (
        len(entries), len(pool), "有" if cookie else "无"))
    print("信源等级:", {("%s·%s" % (k, contract.EXT_SOURCE_TIERS[k][:4])): v
                    for k, v in sorted(tiers.items())})
    print("多源印证(独立来源组≥%d): %d 条" % (contract.EXT_CORROBORATION_MIN, n_corr))
    if in_arch_bad:
        print("[WARN] %d 条 url 不在当日检索归档里(可能凭空/或手写):" % len(in_arch_bad))
        for u in in_arch_bad[:5]:
            print("   ", u)
    else:
        print("归档核对: 全部 url 均出自当日检索结果")
    if not args.no_links:
        print("链接探活:", link_stat)
        dead = [it for it in entries if str(it.get("link_status")) not in ("200", "skipped")]
        for it in dead[:5]:
            print("   %-10s %s" % (it.get("link_status"), it.get("url")))
    print("报告:", os.path.join(contract.day_dir(args.root, args.date), "ext_verify.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
