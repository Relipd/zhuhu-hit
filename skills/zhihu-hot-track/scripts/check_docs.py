"""组成清单一致性体检(只读, 不修改任何文件)。

**为什么需要这个脚本**: 本 skill 的能力散在 SKILL.md / ARCHITECTURE.md / writing_method.md
三份文档里, 而"组成清单"这类文档最容易发生两种腐坏 —— ① 新增脚本忘了登记(文档落后于代码);
② 改了范围/口径只改了主流程, 别处的旧表述留成了矛盾(2026-09-13 实测: 拓展范围从"前 10"扩到
"前 20" 后, 文档里仍残留 6 处"只做前 10")。两种腐坏都不会报错, 只会让人照旧文档做错事。

**检查四件事**:
  1. 磁盘上每个 scripts/*.py|*.md 是否都在 ARCHITECTURE.md §二 的组成清单里归了层;
  2. ARCHITECTURE.md 里是否列了磁盘上不存在的"幽灵组件";
  3. SKILL.md 的脚本/模板表是否覆盖了磁盘上的全部组件;
  4. SKILL.md 里是否还有与当前范围口径矛盾的旧表述(用 `--scope` 传入当前口径的正则与豁免词)。

退出码 0 = 全部一致; 1 = 有缺漏(逐条打印)。**只读**: 不使用任何写操作。

用法:
    python scripts/check_docs.py                      # 用内置默认口径(当前=拓展前 20)
    python scripts/check_docs.py --json               # 机读输出
    python scripts/check_docs.py --skill-dir <dir>    # 指定 skill 目录(默认取本脚本的上一级)
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

# ---- 默认口径(改流程时同步改这里; 这是本脚本唯一的业务知识) -------------------
DEFAULT_SCOPE_PATTERN = r"前 10|rank ?1-10|只有前|仅前 10"
"""会与本 skill 当前范围(拓展/分析覆盖前 20 全部)冲突的旧表述。"""

DEFAULT_SCOPE_EXEMPT = ("原为", "2026-09-13 起", "实测", "原 Swarm", "范围变更", "改为", "从 10 扩到")
"""命中上面的正则但含这些词的行, 属于历史说明, 不算矛盾。"""

DOCS = ("SKILL.md", "ARCHITECTURE.md", "writing_method.md")
FILE_RE = r"`([A-Za-z_][A-Za-z0-9_]*\.(?:py|md))`"


def _read(path: str) -> str:
    with io.open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _section(text: str, start: str, end: str) -> str:
    """取 `start` 与 `end` 两个标记之间的内容; 缺任一标记则返回空串。"""
    if start not in text:
        return ""
    tail = text.split(start, 1)[1]
    return tail.split(end, 1)[0] if end in tail else tail


def run(skill_dir: str, scope_pattern: str = DEFAULT_SCOPE_PATTERN,
        scope_exempt=DEFAULT_SCOPE_EXEMPT, quiet: bool = False) -> dict:
    scripts_dir = os.path.join(skill_dir, "scripts")
    disk = sorted(f for f in os.listdir(scripts_dir) if f.endswith((".py", ".md")))

    paths = {name: os.path.join(skill_dir, name) for name in DOCS}
    texts = {name: _read(p) for name, p in paths.items() if os.path.exists(p)}

    # ① / ② ARCHITECTURE.md §二 组成清单的覆盖度
    arch = texts.get("ARCHITECTURE.md", "")
    sec2 = _section(arch, "## 二、", "## 三、")
    classified = set(re.findall(FILE_RE, sec2))
    unclassified = [f for f in disk if f not in classified]
    # DOCS 是三份文档自身的互引, 不是"组件", 不算幽灵项
    phantom = sorted(c for c in classified if c not in disk and c not in DOCS)

    # ③ SKILL.md 的脚本/模板表
    skill = texts.get("SKILL.md", "")
    rows = set(re.findall(r"^\| `([A-Za-z_][A-Za-z0-9_]*\.(?:py|md))`", skill, re.M))
    row_missing = [f for f in disk if f not in rows]
    row_phantom = sorted(r for r in rows if r not in disk and r not in DOCS)

    # ④ 范围口径的残留矛盾
    stale = []
    for ln, line in enumerate(skill.splitlines(), 1):
        if re.search(scope_pattern, line) and not any(k in line for k in scope_exempt):
            stale.append({"line": ln, "text": line.strip()[:160]})

    # 书写 skill 是否被三份文档共同登记(它是唯一跨"产物层"与"方法论层"的组件)
    writing = {name: txt.count("书写skill") for name, txt in texts.items()}

    ok = not (unclassified or phantom or row_missing or row_phantom or stale)
    result = {
        "ok": ok,
        "disk_total": len(disk),
        "disk_py": sum(f.endswith(".py") for f in disk),
        "disk_md": sum(f.endswith(".md") for f in disk),
        "classified": len(disk) - len(unclassified),
        "unclassified": unclassified,
        "phantom_in_architecture": phantom,
        "skill_table_rows": len(rows),
        "skill_table_missing": row_missing,
        "skill_table_phantom": row_phantom,
        "stale_scope_lines": stale,
        "writing_skill_mentions": writing,
    }

    if not quiet:
        line = "-" * 68
        print(line)
        print("组成清单体检  %s" % skill_dir)
        print(line)
        print("磁盘实际      : %d 件 (%d py + %d md)"
              % (result["disk_total"], result["disk_py"], result["disk_md"]))
        print("ARCHITECTURE  : 已归类 %d/%d  未归类 %s  幽灵 %s"
              % (result["classified"], result["disk_total"],
                 unclassified or "无", phantom or "无"))
        print("SKILL.md 表   : %d 行  缺漏 %s  幽灵 %s"
              % (len(rows), row_missing or "无", row_phantom or "无"))
        print("范围口径残留  : %d 处" % len(stale))
        for item in stale:
            print("    L%-5d %s" % (item["line"], item["text"]))
        print("书写 skill    : %s" % ", ".join("%s×%d" % (k, v) for k, v in writing.items()))
        print(line)
        print("[%s] 组成清单一致" % ("PASS" if ok else "FAIL"))
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="组成清单一致性体检(只读)")
    ap.add_argument("--skill-dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="skill 根目录(默认取本脚本的上一级)")
    ap.add_argument("--scope-pattern", default=DEFAULT_SCOPE_PATTERN,
                    help="与当前范围矛盾的旧表述正则")
    ap.add_argument("--json", action="store_true", help="机读输出")
    args = ap.parse_args(argv)

    if not os.path.isdir(os.path.join(args.skill_dir, "scripts")):
        print("[FAIL] 找不到 scripts/ 目录: %s" % args.skill_dir, file=sys.stderr)
        return 2

    res = run(args.skill_dir, scope_pattern=args.scope_pattern, quiet=args.json)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
