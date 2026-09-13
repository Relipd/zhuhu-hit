# -*- coding: utf-8 -*-
"""一键跑完当日交付链路, 并逐关校验 —— 取代"手敲四条命令"。

为什么需要(2026-09-13 实测): 交付链路是 5 步且顺序敏感
(check → fill_excel → gen_html → verify_html, 加 extension 汇总),
每一步都要看退出码, 手敲时容易漏步或看错输出 —— 实测这一轮里就出现过
"改了 emit/model 但忘记重出 Excel/HTML"。把它固化成一条命令, 失败即停并打出是哪一关。

用法
----
  python run_pipeline.py --root <ROOT> --date D                  # 全套(不含 Swarm/发布)
  python run_pipeline.py --root <ROOT> --date D --merge          # 先汇总 extension 再往下
  python run_pipeline.py --root <ROOT> --date D --skip-verify    # 跳过 HTML 校验(调试用)

它**不做**的事(避免误触发): 不跑 Swarm、不抓取、不发布、不改 analysis.json。
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))


def run(step, argv):
    print("\n===== %s =====" % step)
    p = subprocess.run([sys.executable] + argv, cwd=HERE)
    ok = (p.returncode == 0)
    print("[%s] %s (exit=%d)" % ("OK" if ok else "FAIL", step, p.returncode))
    return ok


def main():
    ap = argparse.ArgumentParser(description="一键跑完当日交付链路并逐关校验")
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--merge", action="store_true", help="先跑 merge_extension(汇总+事实性复核)")
    ap.add_argument("--no-links", action="store_true", help="merge 时跳过链接探活")
    ap.add_argument("--skip-verify", action="store_true", help="跳过 verify_html")
    ap.add_argument("--emotion", action="store_true",
                    help="先跑 merge_emotion --write(把情绪片段并进 analysis.json)")
    args = ap.parse_args()

    steps = []
    if args.emotion:
        steps.append(("情绪片段合并", ["merge_emotion.py", "--root", args.root,
                                      "--date", args.date, "--write"]))
    if args.merge:
        mv = ["merge_extension.py", "--root", args.root, "--date", args.date]
        if args.no_links:
            mv.append("--no-links")
        steps.append(("汇总 extension + 事实性复核", mv))
    steps += [
        ("数据完整性校验", ["check.py", "--root", args.root, "--date", args.date]),
        ("填 Excel", ["fill_excel.py", "--root", args.root, "--date", args.date]),
        ("生成 HTML", ["gen_html.py", "--root", args.root, "--date", args.date]),
    ]
    if not args.skip_verify:
        steps.append(("HTML 结构校验", ["verify_html.py", "--root", args.root, "--date", args.date]))

    failed = None
    for name, argv in steps:
        if not run(name, argv):
            failed = name
            break

    print("\n" + "=" * 60)
    if failed:
        print("[FAIL] 链路在「%s」中断 —— 修好后重跑本命令(前面的步骤可重复执行)" % failed)
        return 1
    print("[DONE] %d 关全部通过: %s" % (len(steps), " → ".join(n for n, _ in steps)))
    print("产物: %s / %s" % (contract.xlsx_path(args.root, args.date),
                             contract.report_entry(args.root, args.date)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
