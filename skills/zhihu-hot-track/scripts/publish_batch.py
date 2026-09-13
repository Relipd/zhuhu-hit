# -*- coding: utf-8 -*-
"""批量发布拟答稿 + **发布台账**(2026-09-13 新增)。⚠️ 需用户明确授权, 不接默认流程。

为什么要有台账(当天实测的痛点)
------------------------------
批量发了 18 条, **脚本全部报成功**, 但线上核对只有 13 条真发出去 —— 事后要靠截图、`me contents`、
逐条 goto 才能拼出"到底发了哪些", `me contents` 还只返回 29 条里的 17 条。故把发布状态落成
`raw/<D>/publish_ledger.json`, 作为**唯一事实源**: 重跑时自动跳过已发布的、只补未发布的。

安全设计(都是当天踩出来的)
--------------------------
* **每条发布前**用 `publish_draft.py` 生成脚本(内含"字数校验不过就拒绝发布"闸门);
* **每条发布后**以「URL 是否变成 /answer/<id>」判定成功 —— 点完按钮不等于发出去;
* **连续 2 条点不动就停**(实测连发约 13 条后平台静默限流: 按钮位置正确、真实鼠标点击与
  Ctrl+Enter 都无反应、页面无任何提示), 剩下的标记 `blocked`, 由人隔一段时间再跑;
* 每条之间留间隔(默认 75s), 支持起始冷却 `--cooldown`。

用法
----
  python publish_batch.py --root <ROOT> --date D --status          # 只看台账
  python publish_batch.py --root <ROOT> --date D                   # 发布所有"未发布"的 rank
  python publish_batch.py --root <ROOT> --date D --ranks 15,16     # 只发指定 rank
  python publish_batch.py --root <ROOT> --date D --cooldown 600 --gap 75
  python publish_batch.py --root <ROOT> --date D --mark "1=<answer url>"   # 人工登记已发布
  python publish_batch.py --root <ROOT> --date D --mark-manual 15,16      # 标记为"待人工发布"
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
CLI_DIR = os.environ.get("PLAYWRIGHT_CLI_DIR", r"D:\claude code\playwright-cli")
TMP = os.environ.get("TEMP", r"D:\DSH")


def ledger_path(root, date):
    return os.path.join(contract.day_dir(root, date), "publish_ledger.json")


def load_ledger(root, date):
    p = ledger_path(root, date)
    if os.path.exists(p):
        with io.open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    return {"date": date, "items": {}}


def save_ledger(root, date, led):
    p = ledger_path(root, date)
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(led, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def show(led):
    items = led.get("items", {})
    pub = [k for k, v in items.items() if v.get("status") == "published"]
    other = {k: v.get("status") for k, v in items.items() if v.get("status") != "published"}
    print("台账 %s：已发布 %d 条 %s" % (led.get("date"), len(pub), sorted(pub, key=int)))
    if other:
        print("           其他状态：%s" % {k: other[k] for k in sorted(other, key=int)})
    return pub


def main():
    ap = argparse.ArgumentParser(description="批量发布拟答稿并维护发布台账(需用户授权)")
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--ranks", default=None, help="默认: 前 %d 条中有拟答稿的 rank"
                    % contract.PUBLISH_TOP_N)
    ap.add_argument("--all", action="store_true",
                    help="不受「每日前 N 条」限制, 发布全部有稿的 rank(默认只发前 %d 条)"
                         % contract.PUBLISH_TOP_N)
    ap.add_argument("--gap", type=float, default=75, help="每条间隔秒(默认 75, 防限流)")
    ap.add_argument("--cooldown", type=float, default=0, help="开始前冷却秒")
    ap.add_argument("--max-consecutive-fail", type=int, default=2,
                    help="连续失败多少条就停(判定为限流)")
    ap.add_argument("--status", action="store_true", help="只打印台账")
    ap.add_argument("--mark", action="append", default=[], help="人工登记已发布: N=<answer url>")
    ap.add_argument("--mark-manual", default=None, help="标记为待人工发布: 15,16")
    args = ap.parse_args()

    led = load_ledger(args.root, args.date)
    items = led.setdefault("items", {})
    with io.open(contract.path_answers(args.root, args.date), encoding="utf-8-sig") as f:
        summary = {s["rank"]: s for s in json.load(f)}

    if args.mark:
        for kv in args.mark:
            k, _, u = kv.partition("=")
            rk = str(int(k))
            dp = contract.path_draft(args.root, args.date, rk)
            ln = 0
            if os.path.exists(dp):
                body = "\n".join(io.open(dp, encoding="utf-8-sig").read().splitlines()[1:])
                ln = len(re.sub(r"\s", "", body))
            items[rk] = {"status": "published", "answer_url": u.strip(), "len": ln,
                         "source": "manual-mark"}
        save_ledger(args.root, args.date, led)
        print("已人工登记 %d 条" % len(args.mark))
        show(led)
        return 0

    if args.mark_manual:
        for k in args.mark_manual.split(","):
            rk = str(int(k))
            items.setdefault(rk, {})["status"] = "pending_manual"
        save_ledger(args.root, args.date, led)
        print("已标记待人工发布：%s" % args.mark_manual)
        show(led)
        return 0

    if args.status:
        show(led)
        return 0

    # 每日配额: 用户 2026-09-13 实测收到「已达到本日或本周数量上限」, 故定成制度 ——
    # 默认只发**前 PUBLISH_TOP_N 条**, 其余明确标 draft_only(只出稿, 无发布要求)。
    with_draft = [int(k) for k in summary
                  if os.path.exists(contract.path_draft(args.root, args.date, k))]
    if args.ranks:
        ranks = [int(x) for x in args.ranks.split(",")]
    elif args.all:
        ranks = sorted(with_draft)
    else:
        ranks = [r for r in sorted(with_draft) if r <= contract.PUBLISH_TOP_N]
    over = [r for r in sorted(with_draft)
            if r > contract.PUBLISH_TOP_N and (args.all or args.ranks is None)]
    if over:
        for r in over:
            if items.get(str(r), {}).get("status") != "published":
                items[str(r)] = {"status": "draft_only",
                                 "note": "超出每日发布上限(前 %d 条), 按策略只出稿不发布"
                                         % contract.PUBLISH_TOP_N}
        save_ledger(args.root, args.date, led)
        print("按策略(每日前 %d 条)不发布, 已标 draft_only: %s" % (contract.PUBLISH_TOP_N, over))
    todo = [r for r in ranks if items.get(str(r), {}).get("status") != "published"]
    skipped = [r for r in ranks if r not in todo]
    if skipped:
        print("台账显示已发布，跳过：%s" % skipped)
    if not todo:
        print("没有待发布的 rank")
        return 0
    if args.cooldown:
        print("冷却 %.0f 秒后再开始…" % args.cooldown)
        time.sleep(args.cooldown)

    consec_fail = 0
    for i, rk in enumerate(todo):
        draft = contract.path_draft(args.root, args.date, rk)
        url = summary[rk]["url"]
        js = os.path.join(TMP, "_pub_%d.js" % rk)
        g = subprocess.run([sys.executable, os.path.join(HERE, "publish_draft.py"),
                            "--draft", draft, "--out", js, "--publish",
                            "--shot", os.path.join(TMP, "_p%d_before.png" % rk),
                            "--shot2", os.path.join(TMP, "_p%d_after.png" % rk)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if g.returncode != 0:
            print("rank%-3d 生成脚本失败" % rk)
            items[str(rk)] = {"status": "gen_failed"}
            consec_fail += 1
            continue
        subprocess.run(["node", "playwright-cli.js", "goto", url], cwd=CLI_DIR,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        r = subprocess.run(["node", "playwright-cli.js", "run-code", "--filename=" + js],
                           cwd=CLI_DIR, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        m = re.findall(r'\{"ok".*?\}', r.stdout + r.stderr, re.S)
        res = json.loads(m[-1]) if m else {"ok": False, "reason": "no-result"}
        if res.get("published"):
            items[str(rk)] = {"status": "published", "answer_url": res.get("urlAfter", ""),
                              "len": res.get("len"), "expected": res.get("expected"),
                              "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            consec_fail = 0
            print("rank%-3d 已发布 %s" % (rk, res.get("urlAfter", "")))
        else:
            # 配额提示优先: 平台弹「已达到本日或本周数量上限」时, 继续试剩下的条毫无意义
            if res.get("limitHit") or res.get("reason") == "DAILY_QUOTA_LIMIT":
                items[str(rk)] = {"status": "blocked_limit",
                                  "limit_text": res.get("limitText", ""),
                                  "at": time.strftime("%Y-%m-%d %H:%M:%S")}
                save_ledger(args.root, args.date, led)
                print("rank%-3d 命中**日/周配额上限** —— 立即停止(继续试无意义)。" % rk)
                print("  平台原文: %s" % res.get("limitText", ""))
                print("  剩余条目标 blocked_limit: 隔天(或下周)再跑本命令即可续发; "
                      "也可人工发布: python make_manual_publish.py --ranks %s"
                      % ",".join(str(x) for x in todo[i + 1:]))
                show(led)
                return 2
            items[str(rk)] = {"status": "blocked", "reason": res.get("reason"),
                              "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            consec_fail += 1
            print("rank%-3d 未发布 (%s)" % (rk, res.get("reason")))
        save_ledger(args.root, args.date, led)
        sys.stdout.flush()
        if consec_fail >= args.max_consecutive_fail:
            rest = todo[i + 1:]
            for x in rest:
                items.setdefault(str(x), {})["status"] = "blocked"
            save_ledger(args.root, args.date, led)
            print("\n连续 %d 条点不动 —— 判定为平台发布频率限制, 已停下。" % consec_fail)
            print("剩余 %s 已标记 blocked: 建议隔一段时间(实测 10 分钟冷却仍不够)再跑本命令, "
                  "或改用人工发布: python make_manual_publish.py --ranks <...>" % rest)
            show(led)
            return 1
        if i < len(todo) - 1:
            time.sleep(args.gap)
    show(led)
    return 0


if __name__ == "__main__":
    sys.exit(main())
