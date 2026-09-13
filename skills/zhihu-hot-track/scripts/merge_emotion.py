# -*- coding: utf-8 -*-
"""把情绪判断 subagent 的片段合并进 analysis.json, 并与主 Agent 的判定做分歧对账。

为什么需要它(2026-09-13 实测)
------------------------------
情绪判断下放 subagent 后, 主 Agent 必须能**只复核分歧**而不是重判一遍。首次实测
subagent 与主 Agent 完全一致率只有 **2/10(20%)**, 差异集中在 `讽刺`vs`调侃`、强度标定、
抽象评论的指向、`失望`vs`无奈`vs`忧虑` 四处 —— 也就是说"只看不一致的那些"本身是有价值的工作量,
所以要把对账做成脚本。

片段格式(subagent 产出, 见 prompt_emotion.md):
  ext_search/<D>/emotion/emotion_batch_<tag>.json
  {"1": [{"tags": ["愤怒","讽刺"], "intensity": 5, "target": "制度环境", "why": "…"}, …], …}
数组顺序必须与该 rank 在 answers_summary.json 里的 answers 顺序一致。

用法
----
  # 只校验+对账, 不写(先看分歧)
  python merge_emotion.py --root <ROOT> --date D --compare

  # 合并写入(片段值覆盖同一条回答的 emotion_* 三字段; 保留 why 便于审计)
  python merge_emotion.py --root <ROOT> --date D --write

  # 只处理指定批次文件
  python merge_emotion.py --root <ROOT> --date D --frag <a.json> --frag <b.json> --write
"""
import argparse
import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load(path):
    with io.open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def validate(frag, path, summary_by_rank, errors, warnings, stats):
    """结构校验: 键是 rank、数组长度 == 回答数、值域合法。"""
    for rk, arr in frag.items():
        rk = str(rk)
        if rk not in summary_by_rank:
            errors.append("%s: rank %s 不在 answers_summary.json 里" % (os.path.basename(path), rk))
            continue
        want = len(summary_by_rank[rk]["answers"])
        if not isinstance(arr, list):
            errors.append("%s: rank %s 的值不是数组" % (os.path.basename(path), rk))
            continue
        if len(arr) != want:
            errors.append("%s: rank %s 数组长度 %d != 回答数 %d" % (os.path.basename(path), rk, len(arr), want))
        for i, e in enumerate(arr, 1):
            where = "%s rank%s #%d" % (os.path.basename(path), rk, i)
            if not isinstance(e, dict):
                errors.append("%s: 不是对象" % where)
                continue
            tags = e.get("tags")
            if not isinstance(tags, list) or not tags:
                errors.append("%s: tags 缺失/为空" % where)
            else:
                bad = [t for t in tags if t not in contract.EMOTION_TAGS]
                if bad:
                    errors.append("%s: tags 非法 %s" % (where, bad))
                if len(tags) > contract.EMOTION_TAG_MAX:
                    errors.append("%s: tags %d 个超过上限 %d" % (where, len(tags), contract.EMOTION_TAG_MAX))
                if len(set(tags)) != len(tags):
                    errors.append("%s: tags 重复" % where)
            if e.get("intensity") not in contract.EMOTION_INTENSITY:
                errors.append("%s: intensity 非法 %r" % (where, e.get("intensity")))
            if e.get("target") not in contract.EMOTION_TARGETS:
                errors.append("%s: target 非法 %r" % (where, e.get("target")))
            if not (e.get("why") or "").strip():
                warnings.append("%s: 缺 why(无法复核判定依据)" % where)
            stats["answers"] = stats.get("answers", 0) + 1


def main():
    ap = argparse.ArgumentParser(description="合并情绪判断片段并与主 Agent 判定对账")
    ap.add_argument("--root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--frag", action="append", default=None,
                    help="片段文件, 可多次传; 默认自动发现 ext_search/<D>/emotion/emotion_batch_*.json")
    ap.add_argument("--compare", action="store_true", help="只对账不写(默认行为)")
    ap.add_argument("--write", action="store_true", help="合并写入 analysis.json")
    ap.add_argument("--json", action="store_true", help="分歧明细以 JSON 输出")
    args = ap.parse_args()

    frags = args.frag or sorted(glob.glob(os.path.join(
        contract.ext_search_dir(args.root, args.date), "emotion", "emotion_batch_*.json")))
    if not frags:
        sys.exit("[FAIL] 没找到情绪片段文件")
    summary = load(contract.path_answers(args.root, args.date))
    summary_by_rank = {str(s["rank"]): s for s in summary}
    an_path = contract.path_analysis(args.root, args.date)
    an = load(an_path)

    errors, warnings, stats = [], [], {}
    merged = {}
    for fp in frags:
        try:
            frag = load(fp)
        except Exception as e:
            errors.append("%s: 读取失败 %s" % (os.path.basename(fp), e))
            continue
        validate(frag, fp, summary_by_rank, errors, warnings, stats)
        for rk, arr in frag.items():
            merged[str(rk)] = arr                 # 后到的批次覆盖同 rank(正常不该重叠)

    if errors:
        print("[FAIL] %d 条结构错误:" % len(errors))
        for e in errors[:20]:
            print("  -", e)
        return 1

    # ---- 对账: 与 analysis.json 现有判定逐条比 ----
    diff, same, n = [], 0, 0
    for rk, arr in sorted(merged.items(), key=lambda kv: int(kv[0])):
        cur = an.get(rk, {}).get("answers") or []
        for i, sub in enumerate(arr):
            if i >= len(cur):
                continue
            n += 1
            m = cur[i]
            mt, st = set(m.get("emotion_tags") or []), set(sub["tags"])
            md = {"tags": (mt == st), "intensity": m.get("emotion_intensity") == sub["intensity"],
                  "target": m.get("emotion_target") == sub["target"]}
            if all(md.values()):
                same += 1
            else:
                diff.append({"rank": rk, "idx": i + 1,
                             "main": {"tags": sorted(mt), "intensity": m.get("emotion_intensity"),
                                      "target": m.get("emotion_target")},
                             "sub": {"tags": sub["tags"], "intensity": sub["intensity"],
                                     "target": sub["target"], "why": sub.get("why", "")},
                             "fields": [k for k, v in md.items() if not v]})

    print("片段 %d 个 | 覆盖 %d 个 rank / %d 条回答" % (len(frags), len(merged), stats.get("answers", 0)))
    if warnings:
        print("[WARN] %d 条: 缺 why(前 5)" % len(warnings))
        for w in warnings[:5]:
            print("  -", w)
    print("与主 Agent 判定对比: 完全一致 %d/%d (%.0f%%) | 有分歧 %d"
          % (same, n, (same * 100.0 / n if n else 0), len(diff)))
    if args.json:
        print(json.dumps(diff, ensure_ascii=False, indent=1))
    else:
        fields = {}
        for d in diff:
            for f in d["fields"]:
                fields[f] = fields.get(f, 0) + 1
        if fields:
            print("分歧字段分布:", fields)
        for d in diff[:12]:
            print("  rank%-3s #%-2d 主:%s/%s/%s  子:%s/%s/%s"
                  % (d["rank"], d["idx"],
                     "、".join(d["main"]["tags"]), d["main"]["intensity"], d["main"]["target"],
                     "、".join(d["sub"]["tags"]), d["sub"]["intensity"], d["sub"]["target"]))

    if not args.write:
        print("(未写入; 加 --write 合并)")
        return 0

    for rk, arr in merged.items():
        cur = an.setdefault(rk, {}).setdefault("answers", [])
        for i, sub in enumerate(arr):
            if i >= len(cur):
                continue
            cur[i]["emotion_tags"] = sub["tags"]
            cur[i]["emotion_intensity"] = sub["intensity"]
            cur[i]["emotion_target"] = sub["target"]
            if sub.get("why"):
                cur[i]["emotion_why"] = sub["why"]      # 审计字段: 判定依据
            cur[i].pop("judge", None)
    tmp = an_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(an, f, ensure_ascii=False, indent=1)
    os.replace(tmp, an_path)
    print("已写入 %s(%d 个 rank 的情绪字段已更新)" % (an_path, len(merged)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
