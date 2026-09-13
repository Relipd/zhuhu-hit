# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 发散证据的事实性复核(信源门槛兜底 + 多源印证 + 链接探活)。

为什么需要它
------------
本流程信源集中在知乎, 交付的其实是**「知乎平台公众言论」的事实性提炼**, 不是已核实的事实。
用户 2026-09-12 明令: 匿名口述(如「有从业者对比称, 2000粉博主月入3000-4000元」)
不值得采信, 获取帖子时要有**信源门槛**。

三道复核(全部为后处理, 不增加 subagent 成本):
  1. **信源等级(source_tier)** —— 兜底打标, 不硬拦截(判定权在采集端):
       C 匿名归属(不可作事实采信) / D 可核锚点不足(仅作观点/主张)
       A 具名主体+可核锚点 / B 有可核锚点但未见具名主体
     锚点 = **数值锚点**(带单位数字) + **制度性锚点**(法规条号/案号/公文与判例),
     2026-09-13 补充后者: 只看数字会把「六部门联合通报」「国务院办公厅印发《意见》」
     这类一等一的事实性证据误判成 D。
     另一条升级路径: **多源独立印证**可把 B 升到 A。
     判定结论按 (url, content 指纹) 缓存 —— 同一 url 挂多条不同内容时必须各自判定。
  2. **entities 兜底** —— schema 里 entities 标「推荐」导致实测无人填写, 这里按主体形态
     (文件名/机构名/人名) 自动抽取并标 entities_auto, 让话题库 --entity 检索可用。
  3. **多源印证(corroboration)** —— 用当日检索归档池(ext_search/<D>/rank_<N>/rank_0N_*.json),
     按关键数字找同数出现, 并做**同源折叠**(洗稿转载视为同一来源, 3-gram Jaccard ≥ 阈值),
     统计「独立来源组」数。不做折叠的话, 中文自媒体大量转载会让"多源"变成自欺。
  4. **链接探活(link_status)** + **归档核对(in_archive)** —— 链接是否还活着、url 是否真出自检索结果
     (后者把「必须取自搜索结果」这条纪律从 subagent 自述变成脚本强制)。

用法:
  python verify_ext.py --root <ROOT> --date YYYY-MM-DD [--no-links] [--delay 0.4] [--json]

结果就地写回 raw/<D>/extension.json(每条证据/未采用条目的 source_tier/source_kind/
link_status/in_archive/corroboration), 并另写报告 raw/<D>/ext_verify.json。
"""
import argparse
import hashlib
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
DOC_RE = re.compile(contract.EXT_DOC_ANCHOR)
HEARSAY_RE = re.compile(contract.EXT_HEARSAY)
NAMED_RE = re.compile(contract.EXT_NAMED)
# 具名人物(软信号, 仅用于 entities 自动抽取): 姓氏锚定 + 紧邻职务/动词
PERSON_RE = re.compile(r"(?:[%s])[\u4e00-\u9fa5]{1,2}(?=(?:%s))"
                       % (contract.EXT_SURNAMES, contract.EXT_PERSON_TITLE))
DOC_TITLE_RE = re.compile(r"《[^》]{2,30}》")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def host_of(url):
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def key_of(url):
    """url 归一键(去 query 与尾斜杠) —— 归档核对与链接探活按它去重。"""
    return re.sub(r"\?.*$", "", url or "").rstrip("/")


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
    """锚点数 = 数值锚点(带单位数字) + 制度性锚点(法规条号/案号/公文与判例)。

    2026-09-13 修: 只用数值锚点会**系统性误杀制度性事实** —— 实测
    「湖北省纪委机关…六部门联合通报7起…王某被判有期徒刑一年六个月」数值锚点只有 1 个,
    被判 D·观点, 而它的锚点其实是「六家具名机关 + 联合通报 + 判例」。
    返回 (数值数, 制度数, 合计)。
    """
    content = content or ""
    num = len(key_numbers(content))
    doc = len(EXTRA_RE.findall(content)) + len(DOC_RE.findall(content))
    return num, doc, num + doc


def extract_entities(content, cap=None):
    """从正文里抽主体锚点(机构/文件名/人名), 供话题库 --entity 检索。

    背景(2026-09-13 实测): entities 在 schema 里是「可选但推荐」, 结果 71 条证据**一次都没填**,
    --entity 检索形同虚设且无人报警。subagent 不填时由此处兜底自动抽取(标注 entities_auto)。
    """
    cap = contract.EXT_ENTITY_MAX if cap is None else cap
    out, seen = [], set()
    for rx in (DOC_TITLE_RE, NAMED_RE, PERSON_RE):
        for m in rx.finditer(content or ""):
            s = re.sub(r"^《|》$", "", m.group(0)).strip()
            if 2 <= len(s) <= 30 and s not in seen:
                seen.add(s)
                out.append(s)
            if len(out) >= cap:
                return out
    return out


def tier_of(content, corroborated, named_hint):
    num, doc, anchors = anchor_count(content)
    hearsay = bool(HEARSAY_RE.search(content or ""))
    named = bool(named_hint) or bool(NAMED_RE.search(content or ""))
    if hearsay and not named:
        return "C", anchors, named
    if named and anchors >= contract.EXT_NUM_MIN:
        return "A", anchors, named
    if corroborated and anchors >= contract.EXT_NUM_MIN:
        return "A", anchors, named          # 多源独立印证 → 事实性
    if anchors >= contract.EXT_NUM_MIN:
        return "B", anchors, named
    return "D", anchors, named


def probe(url, cookie, attempts=None, backoff=None):
    """链接探活。

    2026-09-13 实测: 单次探活会被瞬时网络抖动放大成"死链" —— 同一批 url 两次运行分别报
    4 条与 24 条失败(HTTP 522 / TimeoutError, 站点侧 Cloudflare 抖动), 而 gen_html 会把
    非 200 一律渲染成「来源已失效」。故: 4xx 视为确定性结果立即返回; 5xx/超时/连接错误
    退避重试(默认 2 次), 仍失败才记录。
    """
    attempts = contract.EXT_LINK_RETRY if attempts is None else attempts
    backoff = contract.EXT_LINK_RETRY_BACKOFF if backoff is None else backoff
    last = "unknown"
    for i in range(max(1, attempts)):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Referer": "https://www.zhihu.com/",
            **({"Cookie": cookie} if cookie else {})})
        try:
            with urllib.request.urlopen(req, timeout=contract.EXT_LINK_TIMEOUT) as r:
                return str(r.status)
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            if e.code < 500:                 # 4xx 是确定性结果, 重试无意义
                return last
        except Exception as e:
            last = type(e).__name__
        if i < attempts - 1:
            time.sleep(backoff * (i + 1))
    return last


def run(root, date, no_links=False, delay=None, quiet=False):
    """执行复核并把结果写回 raw/<D>/extension.json; 返回报告 dict。

    被 merge_extension.py 在写完 extension.json 后直接调用(步骤已合并), 也可单独 CLI 调用。
    """
    delay = contract.EXT_LINK_DELAY if delay is None else delay
    path = contract.path_extension(root, date)
    if not os.path.exists(path):
        raise FileNotFoundError("未找到 %s" % path)
    ext = json.load(io.open(path, encoding="utf-8-sig"))

    pool = load_archive(root, date)
    pool_urls = {key_of(p["url"]) for p in pool}
    cookie_path = contract.path_cookie(root, date)
    if not os.path.exists(cookie_path):
        cookie_path = None
        raw = os.path.join(root, contract.RAW_DIRNAME)
        for d in sorted(os.listdir(raw), reverse=True) if os.path.isdir(raw) else []:
            c = contract.path_cookie(root, d)
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
        # 2026-09-13 修(真实 bug): 结论原先只按 **url** 缓存, 但同一 url 可能挂着**多条不同 content**
        # 的条目 —— 实测澎湃占位链接 m.thepaper.cn/wifiKey_detail.jsp 被 3 个 rank 的 6 条无关证据
        # 共用, 于是先被看到的那条的结论被盖到其余各条上: rank9 一条 named=True/锚点=8 的判例
        # (按规则应为 A) 因此被标成 D。现按 (url, content 指纹) 缓存, 同 url 不同内容各自判定。
        ck = key_of(url) + "||" + hashlib.md5(content.encode("utf-8")).hexdigest()[:10]
        if ck not in annotations:
            groups, hosts, matched = corroborate(content, pool, contract.EXT_SHINGLE_FOLD)
            corr = groups >= contract.EXT_CORROBORATION_MIN
            tier, anchors, named = tier_of(content, corr, False)
            url_key = key_of(url)
            annotations[ck] = {
                "source_tier": tier,
                "source_tier_label": contract.EXT_SOURCE_TIERS[tier],
                "source_kind": source_kind(url),
                "anchors": anchors,
                "in_archive": url_key in pool_urls,
                "corroboration": {"groups": groups, "hosts": sorted(hosts)[:5], "matched": matched},
            }
    for it in entries:            # 同一 (url, content) 的展平条目/链内证据/未采用条目共享同一份结论
        ck = key_of(it.get("url") or "") + "||" + \
            hashlib.md5((it.get("content") or "").encode("utf-8")).hexdigest()[:10]
        it.update(annotations[ck])
        if not it.get("entities"):          # entities 兜底自动抽取(schema 标"推荐" ⇒ 实测无人填)
            ents = extract_entities(it.get("content") or "")
            if ents:
                it["entities"] = ents
                it["entities_auto"] = True

    tiers, link_stat, in_arch_bad, n_corr, n_auto = {}, {}, [], 0, 0
    for ck, rec in annotations.items():    # 按 (url, content) 去重统计 = 真实独立证据数
        tiers[rec["source_tier"]] = tiers.get(rec["source_tier"], 0) + 1
        if rec["corroboration"]["groups"] >= contract.EXT_CORROBORATION_MIN:
            n_corr += 1
        if not rec["in_archive"]:
            in_arch_bad.append(ck.split("||")[0])
    n_auto = sum(1 for it in entries if it.get("entities_auto"))

    if not no_links:
        done = {}
        for it in entries:
            url = it.get("url") or ""
            if url not in done:
                done[url] = probe(url, cookie)
                link_stat[done[url]] = link_stat.get(done[url], 0) + 1
                time.sleep(delay)
            it["link_status"] = done[url]
    else:
        for it in entries:
            it.setdefault("link_status", "skipped")

    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(ext, f, ensure_ascii=False, indent=1)

    # 独立证据数 = 按 (url, content) 去重的结论条数 —— 等于「链内证据 + 未采用条目」。
    # items 是 chains 的展平镜像(同一份内容两个对象, 见坑 39), 不能重复计入,
    # 否则会报出「复核 183 条证据」而真实独立证据只有 112 条这种虚高数字(2026-09-13 实测)。
    n_chain_ev = sum(len(ch.get("evidence") or [])
                     for b in ext.values() for ch in (b.get("chains") or []))
    n_drop = sum(len(b.get("dropped") or []) for b in ext.values())
    report = {
        "date": date, "total": len(entries),
        "distinct": len(annotations),
        "evidence": {"chains": n_chain_ev, "dropped": n_drop,
                     "items_mirror_of_chains": sum(len(b.get("items") or []) for b in ext.values())},
        "tiers": tiers, "tier_labels": contract.EXT_SOURCE_TIERS,
        "link_status": link_stat if not no_links else "skipped",
        "corroborated": n_corr,
        "entities_autofilled": n_auto,
        "in_archive_false": sorted(set(in_arch_bad)),
        "archive_pool": len(pool), "cookie": bool(cookie),
    }
    with io.open(os.path.join(contract.day_dir(root, date), "ext_verify.json"),
                 "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    if quiet:
        return report
    print("复核 %d 条独立证据(链内 %d + 未采用 %d; items %d 为链内镜像, 不另计) | "
          "归档池 %d 条原始结果 | cookie %s" % (
              len(annotations), n_chain_ev, n_drop, report["evidence"]["items_mirror_of_chains"],
              len(pool), "有" if cookie else "无"))
    print("信源等级:", {("%s·%s" % (k, contract.EXT_SOURCE_TIERS[k][:4])): v
                    for k, v in sorted(tiers.items())})
    print("多源印证(独立来源组≥%d): %d 条" % (contract.EXT_CORROBORATION_MIN, n_corr))
    if n_auto:
        print("entities 兜底自动抽取: %d 条(subagent 未填, 由脚本按主体形态补)" % n_auto)
    if in_arch_bad:
        print("[WARN] %d 条 url 不在当日检索归档里(可能凭空/或手写):" % len(in_arch_bad))
        for u in in_arch_bad[:5]:
            print("   ", u)
    else:
        print("归档核对: 全部 url 均出自当日检索结果")
    if not no_links:
        print("链接探活:", link_stat)
        dead = [it for it in entries if str(it.get("link_status")) not in ("200", "skipped")]
        for it in dead[:5]:
            print("   %-10s %s" % (it.get("link_status"), it.get("url")))
    print("报告:", os.path.join(contract.day_dir(root, date), "ext_verify.json"))
    return report


def main():
    ap = argparse.ArgumentParser(description="发散证据事实性复核(信源门槛兜底/多源印证/链接探活)")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True)
    ap.add_argument("--no-links", action="store_true", help="跳过链接探活(纯本地, 零请求)")
    ap.add_argument("--delay", type=float, default=contract.EXT_LINK_DELAY)
    ap.add_argument("--json", action="store_true", help="只输出机读报告")
    args = ap.parse_args()
    if args.json:
        print(json.dumps(run(args.root, args.date, args.no_links, args.delay, quiet=True),
                         ensure_ascii=False, indent=1))
        return 0
    run(args.root, args.date, args.no_links, args.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
