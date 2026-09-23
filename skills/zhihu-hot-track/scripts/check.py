# -*- coding: utf-8 -*-
"""热榜跟进 - 数据完整性校验(Agent 完成分析后运行)。

用法: python check.py --root <工作根目录> --date 2026-08-08
检查: 热榜条数 / 回答内容非空 / 分析四维齐全 / 情绪字段值域(新:多标签+强度+指向; 旧:三元 judge) / URL 前缀
有缺失时退出码非 0, 输出缺失明细。
"""
import argparse, json, os, sys

import contract   # 数据契约:文件名 / 字段 / 值域的单一定义处(见 contract.py)

# Windows 中文控制台默认 GBK: 直接 print "✓" 等非 GBK 字符会抛
# UnicodeEncodeError 并以退出码 1 结束, 让"校验通过"看起来像"校验失败"(坑 19)。
# 这里强制 UTF-8 输出并对不可编码字符降级, 保证退出码只反映校验结果。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

JUDGES = set(contract.EMOTIONS)
TAGS = set(contract.EMOTION_TAGS)
TARGETS = set(contract.EMOTION_TARGETS)
INTENS = set(contract.EMOTION_INTENSITY)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    summary = json.load(open(contract.path_answers(args.root, args.date), encoding="utf-8"))
    an = json.load(open(contract.path_analysis(args.root, args.date), encoding="utf-8"))

    # hot.json 容错: 当天可能只做了单问题追加追踪, 没有榜单快照
    items = contract.read_hot_items(args.root, args.date)

    problems = []
    if len(items) == 0 and len(summary) == 0:
        problems.append("热榜与回答数据均为空")

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
            for k in contract.ANALYSIS_CORE:
                v = A.get(k)
                if not v or v == "MISSING":
                    problems.append(f"#{s['rank']}-回答{i} 分析字段[{k}]缺失")
            # 情绪: 两套模型并存(2026-09-13 起为「多标签+强度+指向」)。
            # 优先按新模型校验(带 emotion_tags 即新数据); 仅 legacy judge 时按旧三元校验;
            # 两者都没有 = 漏标。这样过渡期一条记录同时带两套也不会绕过新校验。
            if A.get("emotion_tags") is not None:
                tags = A.get("emotion_tags")
                if not isinstance(tags, list) or not tags:
                    problems.append(f"#{s['rank']}-回答{i} 情绪标签缺失(应为 1-{contract.EMOTION_TAG_MAX} 个)")
                else:
                    bad = [t for t in tags if t not in TAGS]
                    if bad:
                        problems.append(f"#{s['rank']}-回答{i} 情绪标签非法: {bad}")
                    if len(tags) > contract.EMOTION_TAG_MAX:
                        problems.append(f"#{s['rank']}-回答{i} 情绪标签 {len(tags)} 个, 超过上限 "
                                        f"{contract.EMOTION_TAG_MAX}")
                    if len(set(tags)) != len(tags):
                        problems.append(f"#{s['rank']}-回答{i} 情绪标签重复: {tags}")
                if A.get("emotion_intensity") not in INTENS:
                    problems.append(f"#{s['rank']}-回答{i} 情绪强度非法: {A.get('emotion_intensity')}"
                                    f"(应为 1-5)")
                if A.get("emotion_target") not in TARGETS:
                    problems.append(f"#{s['rank']}-回答{i} 情绪指向非法: {A.get('emotion_target')}")
            elif A.get("judge"):
                if A["judge"] not in JUDGES:
                    problems.append(f"#{s['rank']}-回答{i} 情绪判断非法: {A['judge']}")
            else:
                problems.append(f"#{s['rank']}-回答{i} 情绪字段缺失(既无 emotion_tags 也无 judge)")

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
    print("[OK] 全部通过: 分析齐全, 情绪字段(多标签+强度+指向 或 历史三元)值域正确, 内容与 URL 无缺失")
    print("提示: HTML 结构校验请运行 scripts/verify_html.py --root <ROOT> --date <D>")

if __name__ == "__main__":
    main()
