# -*- coding: utf-8 -*-
"""问题维度抓取:网页 API 直取"某问题下的高赞回答"(替代纯关键词搜索召回)。

为什么需要它(2026-09-11 实测)
------------------------------
`search zhihu` 是**全站关键词检索**:召回取决于回答正文是否命中查询词,`--count` 上限 10,
且返回的多是全站其他内容。实测对比(带 Cookie 直连网页接口):

    rank1 客厅    我们抓 5 条 / 该问题共 301 条, 漏掉最高 766 赞 (我们最高只有 51 赞)
    rank2 红果    我们抓 4 条 / 共 607 条, 漏掉最高 869 赞 (我们最高只有 14 赞)
    rank4 画报    我们抓 4 条 / 共 1814 条, 漏掉 6088/3411/1803 赞

本脚本改为**问题维度**抓取:直接请求该问题的回答列表,按赞排序取前 N,
并记录 `total_answers` 与 `coverage`,使覆盖率从 ~2% 变为"最热 N 条必覆盖"。

条目类型适配(热榜条目类型混杂)
--------------------------------
    /question/{qid}          -> api/v4/questions/{qid}/answers (列表, 按赞)
    /p/{id} 或 zhuanlan      -> api/v4/articles/{id}          (专栏文章, 无"回答")
    /question/{qid}/answer/{aid} -> api/v4/answers/{aid}      (单条回答)

多源分层降级
------------
    web(本脚本) 成功 -> source=web_question / web_article
    web 失败/为空     -> 用 answers_summary.json 里 run.py 的搜索结果兜底, source=search

用法:
  python question_fetch.py --root <ROOT> --date <D> [--top 5] [--delay 1.5]
  python question_fetch.py --root <ROOT> --date <D> --out <对比文件>   # 不改动交付数据(推荐先对比)
  python question_fetch.py --root <ROOT> --date <D> --no-merge         # 不与搜索兜底合并

Cookie: 读 raw/<D>/cookies.txt(存在即用, 不验证; 见 SKILL.md Step 1.2 懒加载策略)。
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

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract   # noqa: E402  数据契约:文件名 / 字段 / 值域的单一定义处
import platform_profile as pf   # noqa: E402  L2 平台档案:接口地址与 URL 模板
import zhihu_env  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
API = pf.get("api_base")
# 列表接口的 include: 只能写"需要服务端额外注入"的字段。
# 教训(2026-09-11 实测): 混入 id / url / author.name 这类**默认字段**的键,
# 会让整个 include 部分失效 —— voteup_count 直接变成 None(表现: 抓到回答但赞数全 0)。
ANS_INCLUDE = "data[*].voteup_count,content,data[*].comment_count"

# 请求级重试参数(由 --retry/--backoff 覆盖, 见 get_json 的说明)
_RETRY = 3
_BACKOFF = 5.0


def strip_html(html):
    txt = re.sub(r"<[^>]+>", "", html or "")
    txt = (txt.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
              .replace("&amp;", "&").replace("&quot;", '"').replace("&#34;", '"'))
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def load_cookie(root, date):
    """复用可用的 Cookie(当日优先, 否则 raw/ 下最近一份; 不验证、不删除)。"""
    p = zhihu_env.find_cookie(root, date)
    if not p:
        return None, None
    # 兼容带 BOM 的文件(坑 25)
    return io.open(p, encoding="utf-8-sig").read().strip(), p


def get_json(url, cookie=None, timeout=25, retry=None, backoff=None):
    """带退避重试的 JSON 请求(单一入口, 三种条目类型共用)。

    为什么必须重试: 实测平台网页接口在连续请求后会偶发 403(限流), 而**同一个 Cookie、
    同一个 URL 单独请求又返回 200**。2026-09-12 的 rank5 就是这样一次瞬时 403 被上层
    try/except 兜底成 search_fallback, 结果该问题既丢了主数据源、也丢了 total_answers/coverage
    (覆盖率标注的依据)。此处重试后, 上层只在真正连续失败时才降级。
    """
    retry = _RETRY if retry is None else retry
    backoff = _BACKOFF if backoff is None else backoff
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
               "Referer": (pf.get("referer") or "")}
    if cookie:
        headers["Cookie"] = cookie
    last = None
    for attempt in range(1, max(1, retry) + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            if attempt >= max(1, retry):
                break
            time.sleep(backoff * attempt)
    raise last


def kind_of(url):
    """判定热榜条目类型。"""
    if re.search(r"/answer/(\d+)", url or ""):
        return "answer"
    if re.search(r"/p/(\d+)", url or "") or "zhuanlan" in (url or ""):
        return "article"
    if re.search(r"/question/(\d+)", url or ""):
        return "question"
    return "unknown"


def aid_key(url):
    """回答的稳定去重键(优先 answer id)。"""
    m = re.search(r"/answer/(\d+)", url or "")
    return m.group(1) if m else (url or "")

def qid_of(url):
    m = re.search(r"/question/(\d+)", url or "")
    return m.group(1) if m else None


def fetch_question(qid, top, cookie, delay, pages=1):
    """返回 (answers, total, title)。

    三个实测要点:
      1. `order_by=voteup` 并不严格按赞降序(与 default 同序), 因此**必须自行在返回集合内排序**;
      2. 单页 20 条未必包含全部最热回答, `pages>1` 可多取几页提高"最热 N 条"命中率;
      3. **标题只能从这里拿**: `api/v4/questions/{qid}`(单问题元数据接口)实测直接 403,
         而 answers 接口每条结果自带 `question.title`(2026-09-12 实测)。
    """
    answers, total, limit, title = [], None, 20, ""
    for page in range(max(pages, 1)):
        url = (f"{API}/questions/{qid}/answers?include={ANS_INCLUDE}"
               f"&limit={limit}&offset={page * limit}&order_by=voteup")
        d = get_json(url, cookie)
        data = d.get("data") or []
        if total is None:
            total = (d.get("paging") or {}).get("totals")
        if data and not title:
            title = ((data[0].get("question") or {}).get("title") or "")
        if not data:
            break
        for a in data:
            aid = str(a.get("id"))
            content = strip_html(a.get("content"))
            trunc = bool(a.get("content_need_truncated"))
            answers.append({
                "url": (pf.get("url_answer") or "").format(qid=qid, aid=aid),
                "text": content,
                "likes": a.get("voteup_count") or 0,
                "author": ((a.get("author") or {}).get("name") or ""),
                "comment_count": a.get("comment_count") or 0,
                "content_status": "truncated" if trunc else ("full" if content else "summary"),
            })
        if len(data) < limit:
            break
        if page + 1 < max(pages, 1):
            time.sleep(delay)
    answers.sort(key=lambda a: -(a.get("likes") or 0))
    return answers[:max(top, 1)], total, title


def fetch_article(pid, cookie):
    d = get_json(f"{API}/articles/{pid}?include=content,voteup_count,comment_count,author,title", cookie)
    content = strip_html(d.get("content"))
    return [{
        "url": (pf.get("url_article") or "").format(pid=pid),
        "text": content,
        "likes": d.get("voteup_count") or 0,
        "author": ((d.get("author") or {}).get("name") or ""),
        "comment_count": d.get("comment_count") or 0,
        "content_status": "full" if content else "summary",
    }], 1, (d.get("title") or "")


def fetch_answer(aid, qid, cookie):
    d = get_json(f"{API}/answers/{aid}?include=content,voteup_count,comment_count,author", cookie)
    content = strip_html(d.get("content"))
    return [{
        "url": (pf.get("url_answer") or "").format(qid=qid, aid=aid) if qid
               else (pf.get("url_answer_bare") or "").format(aid=aid),
        "text": content,
        "likes": d.get("voteup_count") or 0,
        "author": ((d.get("author") or {}).get("name") or ""),
        "comment_count": d.get("comment_count") or 0,
        "content_status": "truncated" if d.get("content_need_truncated") else
                          ("full" if content else "summary"),
    }], 1, None


def preflight_cookie(items, cookie, delay):
    """cookie 预检(2026-09-21 起): 答案内容接口失效时全部 summary/403 ——
    用第 1 个问题类条目的前几条回答试抓, 2~3 个请求内快速失败, 别把 99+ 请求烧完才发现。
    判据: 前 3 条回答 content_status **全部** summary 即判失效(有任一 full/truncated 即放行)。"""
    it0 = next((it for it in items if kind_of(it.get("Url", "")) == "question"), None)
    if it0 is None:
        return True                      # 榜首无问题类条目(全是文章/回答), 预检无对象, 放行
    try:
        answers, _, _ = fetch_question(qid_of(it0["Url"]), 3, cookie, delay, pages=1)
    except Exception as e:
        print(f"[preflight] 第 1 题抓取即失败: {type(e).__name__}: {e}")
        return False
    if not answers:
        print("[preflight] 第 1 题答案列表为空")
        return False
    stat = [a.get("content_status") for a in answers]
    if all(s == "summary" for s in stat):
        print(f"[preflight] 前 {len(stat)} 条回答全是 summary(无任何全文) —— cookie 大概率失效")
        return False
    print(f"[preflight] OK({'/'.join(stat[:3])}) —— cookie 可用")
    return True


def main():
    ap = argparse.ArgumentParser(description="问题维度抓取(网页 API, 按赞取前 N)")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True)
    ap.add_argument("--top", type=int, default=5, help="每问题保留的高赞回答数(默认5)")
    ap.add_argument("--pages", type=int, default=1, help="每问题取几页(每页20条, 取多页提高最热N命中率)")
    ap.add_argument("--delay", type=float, default=1.5, help="请求间隔秒(防限流)")
    ap.add_argument("--retry", type=int, default=3, help="单问题失败重试次数(默认3)")
    ap.add_argument("--backoff", type=float, default=5.0, help="重试退避基数秒(第 n 次等 n*backoff)")
    ap.add_argument("--out", default=None, help="输出路径, 默认覆盖 raw/<D>/answers_summary.json")
    ap.add_argument("--no-merge", action="store_true",
                    help="只用网页结果, 不并入搜索召回(默认并入: web ∪ search 并集)")
    ap.add_argument("--no-preflight", action="store_true",
                    help="跳过 cookie 预检(默认开跑前用第 1 题试抓 2~3 个请求, 失效即中止)")
    args = ap.parse_args()

    global _RETRY, _BACKOFF
    _RETRY, _BACKOFF = max(1, args.retry), max(0.0, args.backoff)

    day = contract.day_dir(args.root, args.date)
    hot = json.load(io.open(contract.path_hot(args.root, args.date), encoding="utf-8-sig"))
    items = hot[contract.HOT_ITEMS_PATH[0]][contract.HOT_ITEMS_PATH[1]]
    cur_path = contract.path_answers(args.root, args.date)
    old = {}
    if os.path.exists(cur_path):
        for s in json.load(io.open(cur_path, encoding="utf-8")):
            old[s["rank"]] = s

    cookie, cookie_path = load_cookie(args.root, args.date)
    print("[info] cookie: " + (f"复用 {cookie_path}(不验证、不删除)" if cookie
                               else "无 —— 网页接口可能 403, 将降级搜索兜底"))

    if not args.no_preflight and not preflight_cookie(items, cookie, args.delay):
        sys.exit("[FATAL] cookie 预检未通过 —— 按方式 C 重提: playwright-cli 登录态 storage-state save → "
                 f"python extract_cookie.py --state <zhihu-state.json> --out {cookie_path or 'raw/<D>/cookies.txt'}"
                 " → 重跑本命令(确实要跳过预检: --no-preflight)")

    out_path = args.out or cur_path
    summary, stats = [], {"web_question": 0, "web_article": 0, "web_answer": 0,
                          "search_fallback": 0, "empty": 0}
    for i, it in enumerate(items, 1):
        url = it["Url"]
        kind = kind_of(url)
        rec = {"rank": i, "qid": qid_of(url), "title": it["Title"], "url": url,
               "summary": it.get("Summary", ""), "answers": [],
               "total_answers": None, "coverage": None, "source": None}
        try:
            if kind == "question":
                rec["answers"], rec["total_answers"], _ = fetch_question(
                    rec["qid"], args.top, cookie, args.delay, args.pages)
                rec["source"] = "web_question"
            elif kind == "article":
                pid = re.search(r"/p/(\d+)", url).group(1)
                rec["answers"], rec["total_answers"], _ = fetch_article(pid, cookie)
                rec["source"] = "web_article"
            elif kind == "answer":
                aid = re.search(r"/answer/(\d+)", url).group(1)
                rec["answers"], rec["total_answers"], _ = fetch_answer(aid, rec["qid"], cookie)
                rec["source"] = "web_answer"
            else:
                raise ValueError(f"未知条目类型: {url}")
            if not rec["answers"]:
                raise ValueError("网页返回空")
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if isinstance(e, urllib.error.HTTPError):
                msg = f"HTTP {e.code}({'需登录/Cookie 失效' if e.code in (401, 403) else '接口异常'})"
            if not args.no_merge and old.get(i, {}).get("answers"):
                rec["answers"] = old[i]["answers"]
                rec["source"] = "search_fallback"
                rec["fetch_error"] = msg
                stats["search_fallback"] += 1
            else:
                rec["source"] = "empty"
                rec["fetch_error"] = msg
                stats["empty"] += 1
                print(f"  #{i:02d} 抓取失败: {msg}")
        else:
            stats[rec["source"]] = stats.get(rec["source"], 0) + 1

        # 多源**并集**(不是二选一): web(问题维度, 全文) ∪ search(关键词召回)。
        # 两者互补 —— 实测 rank4 的 17503 赞回答**不在网页首 20 条内**(只有搜索召回拿到过它),
        # 而 rank2 的 870 赞回答搜索完全没召回。并集后按赞排序取前 N, 才真正是"该问题最热的 N 条"。
        merged, web_n = {}, 0
        for a in rec["answers"]:
            merged[aid_key(a["url"])] = dict(a, from_="web")
            web_n += 1
        if not args.no_merge:
            for a in old.get(i, {}).get("answers", []):
                k = aid_key(a["url"])
                if k not in merged:
                    merged[k] = dict(a, from_="search")
                elif len(a.get("text") or "") > len(merged[k].get("text") or ""):
                    # 同一条回答: 保留更长文本的版本, 并同步其 content_status
                    merged[k]["text"] = a["text"]
                    merged[k]["content_status"] = a.get("content_status", merged[k].get("content_status"))
        rec["answers"] = sorted(merged.values(), key=lambda a: -(a.get("likes") or 0))[:args.top]
        rec["sources"] = sorted({a.get("from_") for a in rec["answers"] if a.get("from_")})
        if rec["source"].startswith("web") and len(merged) > web_n:
            rec["source"] += "+search"
        if rec["total_answers"]:
            rec["coverage"] = round(len(rec["answers"]) / rec["total_answers"], 4)
        summary.append(rec)
        n_total = rec["total_answers"] or "-"
        cov = f"{rec['coverage']*100:.1f}%" if rec["coverage"] is not None else "n/a"
        top_like = rec["answers"][0]["likes"] if rec["answers"] else 0
        print(f"  #{i:02d} {rec['source']:<15} 取 {len(rec['answers'])}/{n_total} 条 (覆盖 {cov}) 最高赞={top_like}")
        time.sleep(args.delay)

    # 保留单问题追加追踪(extra=true)的条目: 本脚本只按 hot.json 重建榜单条目,
    # 若不保留, 重跑一次就会把追加的 rank 21+ **静默删除**(2026-09-12 实测隐患)。
    extras = [s for s in old.values() if s.get("extra")]
    if extras:
        clash = [s["rank"] for s in extras if any(int(x["rank"]) == int(s["rank"]) for x in summary)]
        if clash:
            print("[WARN] 追加条目 rank %s 与榜单条目冲突, 已跳过保留(请检查 extra_questions.json)" % clash)
            extras = [s for s in extras if int(s["rank"]) not in clash]
        summary.extend(extras)
        summary.sort(key=lambda s: int(s["rank"]))
        print("[info] 保留 %d 条单问题追加条目: rank %s"
              % (len(extras), [s["rank"] for s in extras]))

    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    tot_all = sum(s["total_answers"] or 0 for s in summary)
    tot_got = sum(len(s["answers"]) for s in summary)
    print(f"\n[done] 写出 {out_path}")
    print(f"       问题 {len(summary)} 个 | 抓取回答 {tot_got} 条 | 网页已知总数 {tot_all} 条 "
          f"| 全局覆盖 {tot_got/tot_all*100:.1f}%" if tot_all else "")
    print(f"       来源分布: {stats}")
    if stats["empty"] or stats["search_fallback"]:
        print("       提示: 存在降级/空结果 —— 若为 403, 按 SKILL.md Step 1.2 获取 Cookie 后重跑本脚本")


if __name__ == "__main__":
    main()
