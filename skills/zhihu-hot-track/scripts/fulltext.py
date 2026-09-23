# -*- coding: utf-8 -*-
"""热榜跟进 - 回答全文补全(尽力而为)。

搜索接口的 ContentText 是摘要(截断)。本脚本用平台网页 API
(见 platform_profile.api_base) 尝试补全, 并通过 content_need_truncated 标记状态:
  full      已补全为全文
  truncated  网页 API 也截断(需网页登录 Cookie, 未提供) -> 保留摘要并标注
  summary    网页 API 无内容, 保留搜索摘要

用法: python fulltext.py --root <工作根目录> --date 2026-08-08 [--delay 1.0] [--retry 3]
      [--cookie raw/<date>/cookies.txt]  # 网页登录 Cookie 文件, 解锁截断回答全文
说明: 结果写回 answers_summary.json 的 text 字段, 并新增 content_status 标记;
      单条失败自动退避重试(默认3次), 仍失败则标 summary 并把原因写入 error 字段;
      不带 --force 时只处理非 full 条目, 因此重跑本脚本 = 只重试失败条目。
      运行于 Agent 分析之前或之后均可(之后则截断回答的分析需标注基于摘要)。
"""
import argparse, io, json, os, re, sys, time, urllib.request

# 基础技术栈适配层与本脚本同目录(见 zhihu_env.py 的模块说明)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract   # noqa: E402  数据契约:文件名 / 字段 / 值域的单一定义处
import platform_profile as pf   # noqa: E402  L2 平台档案:接口地址与 URL 模板
import zhihu_env  # noqa: E402

def qid_of(url):
    m = re.search(r"/question/(\d+)", url or "")
    return m.group(1) if m else None

def fetch_answer(aid, qid=None, cookie=None, timeout=20):
    """返回 (content_html, need_truncated) 或抛异常; 带 cookie 时附 Cookie/Referer 头解锁全文"""
    url = f"{pf.get('api_base')}/answers/{aid}?include=content"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    }
    if cookie:
        headers["Cookie"] = cookie
        if qid:
            headers["Referer"] = (pf.get("url_question") or "").format(qid=qid)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    content = d.get("content", "") or ""
    plain = re.sub(r"<[^>]+>", "", content).strip()
    return plain, bool(d.get("content_need_truncated"))

def fetch_answer_retry(aid, qid=None, cookie=None, timeout=20, max_try=3, backoff=2.0):
    """带重试的抓取: 网络抖动/偶发 HTTPError 下自动退避重试(坑 20)。

    实测单次 HTTPError 就让回答退化为 summary, 而重跑一次即可成功;
    因此这里把重试内置, 避免依赖 Agent 手工重跑。
    """
    last = None
    for attempt in range(1, max_try + 1):
        try:
            return fetch_answer(aid, qid, cookie, timeout)
        except Exception as e:
            last = e
            if attempt < max_try:
                time.sleep(backoff * attempt)
    raise last

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数(防限流)")
    ap.add_argument("--force", action="store_true", help="已补全的也重抓")
    ap.add_argument("--retry", type=int, default=3, help="单条回答失败重试次数(默认3)")
    ap.add_argument("--backoff", type=float, default=2.0, help="重试退避基数秒(第n次等 n*backoff)")
    ap.add_argument("--cookie", default=None, help="网页登录 Cookie 文件路径(解锁截断回答全文)")
    args = ap.parse_args()

    cookie, cookie_path = None, None
    if args.cookie:
        cookie_path = args.cookie
    else:
        # 未显式指定时自动复用最近一份 Cookie(当日优先, 否则 raw/ 下最近日期)
        cookie_path = zhihu_env.find_cookie(args.root, args.date)
    if cookie_path:
        with io.open(cookie_path, encoding="utf-8-sig") as f:   # 兼容 BOM(坑 25)
            cookie = f.read().strip()
        print(f"[info] cookie: 复用 {cookie_path}(不验证、不删除)")

    path = contract.path_answers(args.root, args.date)
    summary = json.load(open(path, encoding="utf-8"))

    stats = {"full": 0, "truncated": 0, "summary": 0}
    failed = []
    for s in summary:
        for a in s["answers"]:
            if a.get("content_status") == "full" and not args.force:
                stats["full"] += 1
                continue
            aid = a["url"].split("/answer/")[1].split("?")[0]
            try:
                plain, truncated = fetch_answer_retry(aid, qid_of(a["url"]), cookie,
                                                      max_try=args.retry, backoff=args.backoff)
                if plain and len(plain) > len(a["text"]):
                    a["text"] = plain
                a["content_status"] = "truncated" if truncated else ("full" if plain else "summary")
                a.pop("error", None)          # 成功则清除历史失败痕迹
            except Exception as e:
                a["content_status"] = "summary"
                a["error"] = f"{type(e).__name__}: {e}"   # 失败原因落盘, 便于诊断(坑 20)
                failed.append((s["rank"], aid, a["error"]))
                print(f"  #{s['rank']} answer={aid} 抓取失败(已重试{args.retry}次): {type(e).__name__}")
            stats[a["content_status"]] += 1
            time.sleep(args.delay)

    json.dump(summary, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"补全完成: full={stats['full']} truncated={stats['truncated']} summary={stats['summary']} (cookie={'带' if cookie else '未带'})")
    if failed:
        print(f"仍有 {len(failed)} 条失败(已标注 content_status=summary 与 error 字段), 明细:")
        for rank, aid, err in failed[:10]:
            print(f"  - #{rank} answer={aid}: {err}")
        print("重跑本脚本(不带 --force)会自动只重试这些非 full 条目。")
    # 死答清单(2026-09-21 起, 坑 78): 无正文的回答会卡 check「内容为空」, 在这里提前点名
    dead = [(s["rank"], a["url"], a.get("error") or "内容为空")
            for s in summary for a in s["answers"]
            if a.get("content_status") == "summary" and not (a.get("text") or "").strip()]
    if dead:
        print(f"[死答] {len(dead)} 条无正文(疑已删/失效, 连 cookie 都取不到):")
        for rank, url, why in dead:
            print(f"  - #{rank} {url} ({why})")
        print("处置(坑 78): 从 answers_summary.json 与 analysis.json **同步移除**该条再过 check; 不要伪造正文。")
    print(f"truncated/summary 的回答为接口摘要, 备注列已由 fill_excel 自动标注; 全文需{pf.get('name')}网页登录")
    if cookie:
        print("提示: Cookie 按新策略长期保留复用(不删除, 见 Step 1.2); 分析请按全文复核(约束二)")

if __name__ == "__main__":
    main()
