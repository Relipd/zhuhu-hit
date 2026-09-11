# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 数据完整性校验(Agent 完成分析后运行)。

用法: python check.py --root <工作根目录> --date 2026-08-08
检查: 热榜条数 / 回答内容非空 / 分析四维齐全 / 情绪判断值域 / URL 前缀
有缺失时退出码非 0, 输出缺失明细。
"""
import argparse, json, os, sys

# Windows 中文控制台默认 GBK: 直接 print "✓" 等非 GBK 字符会抛
# UnicodeEncodeError 并以退出码 1 结束, 让"校验通过"看起来像"校验失败"(坑 19)。
# 这里强制 UTF-8 输出并对不可编码字符降级, 保证退出码只反映校验结果。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

JUDGES = {"积极", "中立", "消极"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    day = os.path.join(args.root, "raw", args.date)
    hot = json.load(open(os.path.join(day, "hot.json"), encoding="utf-8-sig"))
    summary = json.load(open(os.path.join(day, "answers_summary.json"), encoding="utf-8"))
    an = json.load(open(os.path.join(day, "analysis.json"), encoding="utf-8"))

    problems = []
    if len(hot["Data"]["Items"]) == 0:
        problems.append("热榜为空")

    total = 0
    for s in summary:
        rank = str(s["rank"])
        if rank not in an:
            problems.append(f"#{s['rank']} 缺少 analysis 条目")
            continue
        q = an[rank]
        if not q.get("essence"):
            problems.append(f"#{s['rank']} 问题本质为空")
        if len(q["answers"]) != len(s["answers"]):
            problems.append(f"#{s['rank']} 分析条数({len(q['answers'])})与回答数({len(s['answers'])})不符")
        for i, a in enumerate(s["answers"], 1):
            total += 1
            if not a.get("text"):
                problems.append(f"#{s['rank']}-回答{i} 内容为空")
            if not str(a.get("url", "")).startswith("http"):
                problems.append(f"#{s['rank']}-回答{i} URL异常: {a.get('url')}")
            if a.get("content_status") not in (None, "full", "truncated", "summary"):
                problems.append(f"#{s['rank']}-回答{i} content_status 非法: {a.get('content_status')}")
            if i - 1 >= len(q["answers"]):
                continue
            A = q["answers"][i - 1]
            for k in ("stance", "approach", "logic", "emotion", "judge"):
                v = A.get(k)
                if not v or v == "MISSING":
                    problems.append(f"#{s['rank']}-回答{i} 分析字段[{k}]缺失")
            if A.get("judge") not in JUDGES:
                problems.append(f"#{s['rank']}-回答{i} 情绪判断非法: {A.get('judge')}")

    print(f"校验: {len(summary)} 问题, {total} 回答")
    # 覆盖度提示(软, 不影响退出码): 有 total_answers 时报告"抓到多少 / 该问题共有多少",
    # 避免把"抓到 5 条"误读成"该问题只有 5 条"(2026-09-11 实测某问题 5/303)。
    if any(s.get("total_answers") for s in summary):
        got = sum(len(s["answers"]) for s in summary if s.get("total_answers"))
        alln = sum(s["total_answers"] for s in summary if s.get("total_answers"))
        low = [s for s in summary if s.get("total_answers") and (s.get("coverage") or 0) < 0.05]
        print(f"覆盖度: 抓取 {got} / 网页已知 {alln} ({got / alln * 100:.1f}%) | 覆盖 <5% 的问题 {len(low)} 个")
        for s in low[:5]:
            print(f"  - #{s['rank']}: {len(s['answers'])}/{s['total_answers']} "
                  f"({(s.get('coverage') or 0) * 100:.1f}%)")
    if problems:
        print(f"发现 {len(problems)} 个问题:")
        for p in problems[:50]:
            print("  -", p)
        sys.exit(1)
    print("[OK] 全部通过: 分析齐全, 情绪判断值域正确, 内容与 URL 无缺失")
    print("提示: HTML 结构校验请运行 scripts/verify_html.py --root <ROOT> --date <D>")

if __name__ == "__main__":
    main()
