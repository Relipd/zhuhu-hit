# -*- coding: utf-8 -*-
"""基础技术栈适配层:统一解析 zhihu-cli 与凭证状态。

背景(为什么要这一层)
----------------------
本 skill(zhihu-hot-track)的业务能力全部建立在 `zhihu` skill(基础技术栈)之上:
后者负责 CLI 的安装/升级/鉴权,并对外暴露 `scripts/run.ps1|run.sh`(统一入口)
与 setup 输出的绝对 `binary_path`。历史上 hot-track 的每个脚本各自硬编码
`%LOCALAPPDATA%\\ZhihuCLI\\current\\zhihu-cli.exe`,带来三个真实问题:

  1. 与基础栈的路径规则不一致:基础栈支持 `ZHIHU_CLI_HOME` 覆盖安装位置,hot-track 不支持;
  2. 基础栈升级会替换自身实现(如 run.ps1 的字段增删),硬编码/强依赖字段的脚本会随之失效;
  3. CLI 二进制可能被清理,而凭证仍留在系统凭证库——脚本却无法自行判断(见踩坑 19)。

本模块的定位:hot-track 侧**唯一的**环境解析入口。原则:
  - 只消费基础栈的公开约定(`ZHIHU_CLI` / `ZHIHU_CLI_HOME` / setup 的 `binary_path` / run.ps1 的 status JSON);
  - 对 status 字段**宽容读取**(缺失即降级为 None,不抛错),使基础栈演进不会连带打断业务;
  - 凭证是否可复用由本模块自行探测系统凭证库,不依赖基础栈是否提供该字段(双向兜底)。

用法:
    import zhihu_env
    cli = zhihu_env.require_cli()          # 可用则返回绝对路径, 否则抛带修复指引的异常
    rep = zhihu_env.diagnose()             # 环境诊断报告(供 doctor.py / 报错信息复用)
    ok  = zhihu_env.keychain_present()     # True/False/None(无法判断)
"""
import json
import os
import subprocess
import sys

__all__ = [
    "cli_home", "candidates", "skill_dir", "skill_status", "resolve_cli",
    "require_cli", "keychain_present", "diagnose", "cli_version", "run_skill_setup_hint",
]

_SKILL_NAME = "zhihu"
_cache = {}


def _exe(name="zhihu-cli"):
    return name + ".exe" if os.name == "nt" else name


def cli_home():
    """CLI 安装根目录。规则必须与基础栈 zhihu skill 的 run.ps1 / run.sh 完全一致。"""
    env = os.environ.get("ZHIHU_CLI_HOME")
    if env:
        return env
    if os.name == "nt":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "ZhihuCLI")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "zhihu-cli")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "zhihu-cli")


def candidates():
    """按优先级返回 CLI 候选绝对路径(附来源标签)。"""
    out = []
    env = os.environ.get("ZHIHU_CLI")
    if env:
        out.append((env, "env:ZHIHU_CLI"))
    home = cli_home()
    if home:
        out.append((os.path.join(home, "current", _exe()), "cli_home"))
    # 额外兼容:某些安装把二进制直接放在 home 下(不放进 current/)
    if home:
        out.append((os.path.join(home, _exe()), "cli_home_flat"))
    return out


def skill_dir(name=_SKILL_NAME):
    """定位基础栈 skill 目录:环境变量优先,其次按同级目录推断
    (本文件位于 <skills_root>/zhihu-hot-track/scripts/,基础栈在 <skills_root>/zhihu/)。"""
    env = os.environ.get("ZHIHU_SKILL_DIR")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    skills_root = os.path.dirname(os.path.dirname(here))
    cand = os.path.join(skills_root, name)
    return cand if os.path.isdir(cand) else None


def skill_status(timeout=60):
    """调用基础栈的统一入口 `run.ps1|run.sh status`,返回原始 JSON(失败返回 None)。

    宽容原则: 本函数不假设任何字段存在,调用方一律用 .get() 取值。
    """
    if "skill_status" in _cache:
        return _cache["skill_status"]
    d = skill_dir()
    result = None
    if d:
        if os.name == "nt":
            runner = os.path.join(d, "scripts", "run.ps1")
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", runner, "status"]
        else:
            runner = os.path.join(d, "scripts", "run.sh")
            cmd = ["sh", runner, "status"]
        if os.path.exists(runner):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout)
                result = json.loads((r.stdout or "").strip())
            except Exception:
                result = None
    _cache["skill_status"] = result
    return result


def _dig(obj, *keys):
    """宽容地按路径取值: 任一层缺失或类型不符 -> None"""
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def cli_version(path, timeout=30):
    try:
        r = subprocess.run([path, "version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        d = json.loads((r.stdout or "").strip())
        return d.get("version") or d.get("Version")
    except Exception:
        return None


def resolve_cli():
    """返回可用的 CLI 绝对路径;找不到返回 None。

    顺序: 环境变量 / cli_home 推算 -> 基础栈 status 的 binary_path(权威, 兼容自定义安装)。
    """
    if "cli" in _cache:
        return _cache["cli"]
    found = None
    for path, _src in candidates():
        if path and os.path.exists(path):
            found = path
            break
    if not found:
        st = skill_status()
        for path_keys in (("cli", "binary_path"), ("binary_path",),
                          ("binary", "path"), ("cli", "path")):
            v = _dig(st, *path_keys)
            if v and os.path.exists(v):
                found = v
                break
    _cache["cli"] = found
    return found


def cli_source(path):
    """标注解析结果来自哪个通道(便于报错时定位)。"""
    if not path:
        return None
    for p, src in candidates():
        if p and os.path.normcase(p) == os.path.normcase(path):
            return src
    return "zhihu_skill_status"


def keychain_present():
    """自行探测系统凭证库中是否已有 zhihu-cli 的 Access Secret。

    与基础栈解耦: 即使 zhihu skill 升级后不再输出凭证相关字段, 本函数仍然可用(见踩坑 19)。
    返回 True / False / None(无法判断)。
    """
    if "keychain" in _cache:
        return _cache["keychain"]
    val = None
    try:
        if os.name == "nt":
            r = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=20)
            val = "zhihu-cli:access-secret" in (r.stdout or "")
        elif sys.platform == "darwin":
            val = False
            for svc in ("zhihu-cli:access-secret", "zhihu-cli"):
                r = subprocess.run(["security", "find-generic-password", "-s", svc],
                                   capture_output=True, text=True, timeout=20)
                if r.returncode == 0:
                    val = True
                    break
    except Exception:
        val = None
    _cache["keychain"] = val
    return val


def find_cookie(root, date=None):
    """定位可复用的网页 Cookie 文件。

    按用户 2026-09-11 指示:Cookie 长期保留、跨天复用、不验证、不删除。
    因此查找顺序为 —— ① 当日 `raw/<date>/cookies.txt`;② `raw/` 下**最近日期**目录里的
    cookies.txt(实现跨天自动复用, 无需重新获取就能接着用)。
    返回绝对路径或 None。
    """
    cands = []
    if date:
        cands.append(os.path.join(root, "raw", date, "cookies.txt"))
    raw = os.path.join(root, "raw")
    if os.path.isdir(raw):
        for d in sorted(os.listdir(raw), reverse=True):
            cands.append(os.path.join(raw, d, "cookies.txt"))
    for p in cands:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return p
        except OSError:
            continue
    return None


def run_skill_setup_hint():
    """安装/升级基础栈 CLI 的可执行指引(供报错信息复用)。"""
    d = skill_dir()
    if os.name == "nt":
        runner = os.path.join(d, "scripts", "setup.ps1") if d else r"<zhihu-skill>\scripts\setup.ps1"
        return "powershell -ExecutionPolicy Bypass -File \"%s\"" % runner
    runner = os.path.join(d, "scripts", "setup.sh") if d else "<zhihu-skill>/scripts/setup.sh"
    return "bash \"%s\"" % runner


def diagnose():
    """环境诊断报告(dict, 可直接 json 序列化)。"""
    cli = resolve_cli()
    st = skill_status()
    return {
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "cli": {
            "resolved": cli,
            "exists": bool(cli and os.path.exists(cli)),
            "source": cli_source(cli),
            "version": cli_version(cli) if cli else None,
            "cli_home": cli_home(),
            "candidates": [{"path": p, "source": s, "exists": bool(p and os.path.exists(p))}
                           for p, s in candidates()],
        },
        "credentials": {
            "keychain_present": keychain_present(),
            "skill_reported_configured": _dig(st, "auth", "configured"),
            "skill_reported_keychain": _dig(st, "auth", "keychain_present"),
        },
        "zhihu_skill": {
            "dir": skill_dir(),
            "status_ok": st is not None,
            "installed": _dig(st, "installed"),
            "skill_version": _dig(st, "skill", "current_version"),
            "skill_update_available": _dig(st, "skill", "update_available"),
            "cli_version_reported": _dig(st, "cli", "current_version"),
            "next_action": _dig(st, "next_action"),
        },
        "setup_hint": run_skill_setup_hint(),
    }


def require_cli():
    """取 CLI 绝对路径;不可用时抛 RuntimeError,信息里包含完整修复指引。"""
    cli = resolve_cli()
    if cli:
        return cli
    rep = diagnose()
    cand_lines = "\n".join(
        "    - {src}: {path} (存在={exists})".format(**c)
        for c in rep["cli"]["candidates"]) or "    (无候选路径)"
    kc = rep["credentials"]["keychain_present"]
    if kc is True:
        cred = "系统凭证库中已有 Access Secret —— 装好 CLI 即可直接复用, 无需重新申请。"
    elif kc is False:
        cred = "系统凭证库中未发现 Access Secret —— 安装后需要按 zhihu skill 流程生成并注入。"
    else:
        cred = "无法探测系统凭证库(非 Windows/macOS 或工具不可用)—— 安装后请跑 auth status --verify 确认。"
    raise RuntimeError(
        "未找到可用的 zhihu-cli(基础技术栈: zhihu skill)。\n"
        "  候选路径:\n{cands}\n"
        "  已尝试的兜底: 调用 {skill_dir} 的 run.ps1|run.sh status 读取 binary_path\n"
        "  凭证状态: {cred}\n"
        "修复方式:\n"
        "  1) 经用户同意后安装/修复基础栈: {hint}\n"
        "  2) 或设置 ZHIHU_CLI 指向已有可执行文件\n"
        "  3) 自定义安装位置请设 ZHIHU_CLI_HOME(规则与 zhihu skill 一致)\n"
        "  排查工具: python scripts/doctor.py --root <ROOT>".format(
            cands=cand_lines, skill_dir=rep["zhihu_skill"]["dir"], cred=cred,
            hint=rep["setup_hint"]))
