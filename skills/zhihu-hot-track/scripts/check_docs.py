"""组成清单一致性体检(只读, 不修改任何文件)。

**为什么需要这个脚本**: 本 skill 的能力散在 SKILL.md / ARCHITECTURE.md / writing_method.md
三份文档里, 而"组成清单"这类文档最容易发生两种腐坏 —— ① 新增脚本忘了登记(文档落后于代码);
② 改了范围/口径只改了主流程, 别处的旧表述留成了矛盾(2026-09-13 实测: 拓展范围从"前 10"扩到
"前 20" 后, 文档里仍残留 6 处"只做前 10")。两种腐坏都不会报错, 只会让人照旧文档做错事。

**检查五件事**:
  1. 磁盘上每个 scripts/*.py|*.md 是否都在 ARCHITECTURE.md §二 的组成清单里归了层;
  2. ARCHITECTURE.md 里是否列了磁盘上不存在的"幽灵组件";
  3. SKILL.md 的脚本/模板表是否覆盖了磁盘上的全部组件;
  4. SKILL.md 里是否还有与当前范围口径矛盾的旧表述(用 `--scope` 传入当前口径的正则与豁免词);
  5. **平台字面量守卫**(2026-09-14 新增): 除 `platform_profile.L2_COMPONENTS` 列出的 L2 组件外,
     任何脚本/模板都不得出现平台名、站点域名或 CLI 名(判定模式见
     `platform_profile.PLATFORM_LITERAL_PATTERN`)。这条守卫把"换平台只改 L2"从**约定**
     变成**机器可查的事实**: L1/L3 一旦写回平台字面量即 FAIL。
     同时双向比对 `L2_COMPONENTS` ↔ ARCHITECTURE.md §二 的 L2 表, 防止名单与文档分叉。

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_profile as pf   # noqa: E402  L2 名单与平台字面量模式的单一定义处

# Windows 中文控制台默认 GBK: 逐条打印命中行时可能含非 GBK 字符(如 emoji),
# 不强制 UTF-8 会抛 UnicodeEncodeError 并把"体检结果"伪装成崩溃(踩坑 19/20)。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---- 默认口径(改流程时同步改这里; 这是本脚本唯一的业务知识) -------------------
DEFAULT_SCOPE_PATTERN = (r"前 10|rank ?1-10|只有前|仅前 10|前 15|只发前 ?15|PUBLISH_TOP_N|"
                         r"自动发(布|帖)")
"""会与当前口径(拓展/分析覆盖前 20 全部; 2026-09-16 起自动发帖已删除、改为待发帖列)冲突的旧表述。"""

DEFAULT_SCOPE_EXEMPT = ("原为", "2026-09-13 起", "实测", "原 Swarm", "范围变更", "改为",
                        "从 10 扩到", "已删", "删除", "退役", "2026-09-16")
"""命中上面的正则但含这些词的行, 属于历史说明或删除决策的记录, 不算矛盾。"""

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


def platform_literals(skill_dir: str, l2=pf.L2_COMPONENTS):
    """⑤ 平台字面量守卫: 返回 [(文件, 行号, 行内容)] —— 非 L2 组件里出现的平台字面量。

    为什么只查非 L2: 见 platform_profile.py 的模块说明 —— 平台属性只允许写在一个地方(档案),
    其余位置一旦写死, 换平台就会变成"改十几处、漏一处不报错"。
    只扫 `scripts/` 内的组件: 三份文档(SKILL/ARCHITECTURE/writing_method)是**本平台实例的说明书**,
    记载平台事实是它们的职责, 不在守卫范围内。
    """
    pattern = re.compile(pf.PLATFORM_LITERAL_PATTERN)
    hits = []
    scripts_dir = os.path.join(skill_dir, "scripts")
    if not os.path.isdir(scripts_dir):
        return hits
    for name in sorted(os.listdir(scripts_dir)):
        if not name.endswith((".py", ".md")) or name in l2:
            continue
        path = os.path.join(scripts_dir, name)
        if not os.path.isfile(path):
            continue
        for ln, line in enumerate(_read(path).splitlines(), 1):
            if pattern.search(line):
                hits.append({"file": name, "line": ln, "text": line.strip()[:140]})
    return hits


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

    # ③ SKILL.md 的脚本/模板表(2026-09-14 起表已拆到 references/, 两处都扫)
    skill = texts.get("SKILL.md", "")
    row_re = r"^\| `([A-Za-z_][A-Za-z0-9_]*\.(?:py|md))`"
    rows = set(re.findall(row_re, skill, re.M))
    table_sources = ["SKILL.md"]
    ref_pointer_missing = []
    refdir = os.path.join(skill_dir, "references")
    if os.path.isdir(refdir):
        for fn in sorted(os.listdir(refdir)):
            if fn.endswith(".md"):
                rows |= set(re.findall(row_re, _read(os.path.join(refdir, fn)), re.M))
                table_sources.append("references/" + fn)
    # 文档指针可达性:SKILL.md 里指向 references/<file> 的每一处都必须真的存在(指针腐烂不报错, 所以机器查)
    for m in set(re.findall(r"references/([A-Za-z0-9_.\-]+\.md)", skill)):
        if not os.path.exists(os.path.join(refdir, m)):
            ref_pointer_missing.append(m)
    row_missing = [f for f in disk if f not in rows]
    row_phantom = sorted(r for r in rows if r not in disk and r not in DOCS)

    # ④ 范围口径的残留矛盾
    stale = []
    for ln, line in enumerate(skill.splitlines(), 1):
        if re.search(scope_pattern, line) and not any(k in line for k in scope_exempt):
            stale.append({"line": ln, "text": line.strip()[:160]})

    # 书写 skill 是否被三份文档共同登记(它是唯一跨"产物层"与"方法论层"的组件)
    writing = {name: txt.count("书写skill") for name, txt in texts.items()}

    # ⑤ 平台字面量守卫 + L2 名单与文档的双向比对
    literals = platform_literals(skill_dir)
    arch_l2 = set(re.findall(FILE_RE, _section(arch, "### L2", "### L3")))
    l2_missing_on_disk = sorted(c for c in pf.L2_COMPONENTS if c not in disk)
    l2_doc_mismatch = sorted((set(pf.L2_COMPONENTS) ^ arch_l2))

    ok = not (unclassified or phantom or row_missing or row_phantom or stale
              or literals or l2_missing_on_disk or l2_doc_mismatch or ref_pointer_missing)
    result = {
        "ok": ok,
        "disk_total": len(disk),
        "disk_py": sum(f.endswith(".py") for f in disk),
        "disk_md": sum(f.endswith(".md") for f in disk),
        "classified": len(disk) - len(unclassified),
        "unclassified": unclassified,
        "phantom_in_architecture": phantom,
        "skill_table_rows": len(rows),
        "skill_table_sources": table_sources,
        "skill_table_missing": row_missing,
        "skill_table_phantom": row_phantom,
        "ref_pointer_missing": ref_pointer_missing,
        "stale_scope_lines": stale,
        "writing_skill_mentions": writing,
        "platform_literals": literals,
        "l2_missing_on_disk": l2_missing_on_disk,
        "l2_doc_mismatch": l2_doc_mismatch,
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
        print("SKILL.md 表   : %d 行 (来自 %s)  缺漏 %s  幽灵 %s"
              % (len(rows), "+".join(table_sources), row_missing or "无", row_phantom or "无"))
        print("references    : 指针缺失 %s" % (ref_pointer_missing or "无"))
        print("范围口径残留  : %d 处" % len(stale))
        for item in stale:
            print("    L%-5d %s" % (item["line"], item["text"]))
        print("书写 skill    : %s" % ", ".join("%s×%d" % (k, v) for k, v in writing.items()))
        print("平台字面量    : 非 L2 文件命中 %d 处   L2 名单 %d 件(缺件 %s / 与文档不一致 %s)"
              % (len(literals), len(pf.L2_COMPONENTS),
                 l2_missing_on_disk or "无", l2_doc_mismatch or "无"))
        for item in literals:
            print("    %s L%-5d %s" % (item["file"], item["line"], item["text"]))
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
