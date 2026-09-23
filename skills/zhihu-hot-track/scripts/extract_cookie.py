#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 playwright storageState 提取知乎登录 Cookie → raw/<D>/cookies.txt(坑 77 的自愈配方)。

背景(2026-09-21 实战): 跑到一半 cookie 失效 → question_fetch 全部 search_fallback、
fulltext 全部 summary。自愈路径 = 用 playwright-cli 从**已登录的 Edge 持久配置**里
storage-state save 出 zhihu-state.json, 再用本脚本解析成 cookies.txt —— 全程免手工复制。

用法:
  python extract_cookie.py --state <zhihu-state.json> --out <ROOT>/raw/<D>/cookies.txt
  # 可选 --domain zhihu.com(默认), 只保留该域 cookie

产出格式与 question_fetch.py / fulltext.py 的消费约定一致: **单行 Cookie 头**
(name=value; name=value; ...), UTF-8 无 BOM(坑 25)。
未见到 z_c0 会打 [WARN](未登录态, 全文解锁会失败)。
"""
import argparse
import io
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(
        description="playwright storageState → cookies.txt(单行 Cookie 头, UTF-8 无 BOM)")
    ap.add_argument("--state", required=True, help="storage state JSON 路径")
    ap.add_argument("--out", required=True, help="产出路径(通常 raw/<D>/cookies.txt)")
    ap.add_argument("--domain", default="zhihu.com", help="只保留该域 cookie(默认 zhihu.com)")
    a = ap.parse_args()

    try:
        data = json.load(io.open(a.state, encoding="utf-8-sig"))
    except Exception as e:
        sys.exit("[FAIL] 读不了 storageState %s: %s" % (a.state, e))
    keep = [c for c in (data.get("cookies") or []) if a.domain in (c.get("domain") or "")]
    if not keep:
        sys.exit("[FAIL] storageState 里没有 %s 域的 cookie —— 是否在登录态下保存?" % a.domain)
    names = sorted(c.get("name", "") for c in keep)
    if "z_c0" not in names:
        print("[WARN] 未见到 z_c0(登录凭证) —— 提取的是未登录态, 全文解锁会失败")
    line = "; ".join("%s=%s" % (c.get("name", ""), c.get("value", "")) for c in keep)
    out_dir = os.path.dirname(os.path.abspath(a.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
    print("[OK] %d 条 cookie → %s" % (len(keep), a.out))
    print("     字段: %s%s" % (", ".join(names),
                              "(含 z_c0)" if "z_c0" in names else "(缺 z_c0!)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
