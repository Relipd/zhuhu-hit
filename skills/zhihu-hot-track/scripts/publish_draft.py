# -*- coding: utf-8 -*-
"""把拟答稿填进知乎网页编辑器(可选: 并发布) —— **需要用户明确授权才可使用**。

⚠️ 风险与边界(2026-09-13 实测后写定)
--------------------------------------------------------------------
* 开放平台/`zhihu-cli` **没有发布接口**(见 SKILL.md「本流程不发布」一节), 所以只能走
  **浏览器自动化驱动已登录的网页端**。
* 这是**操作真实账号的不可逆对外行为**: 一旦发布即对外可见。自动化发帖**多半违反平台用户协议**,
  有账号风险。**未经用户逐条明确授权不得执行**; 不要把它接进默认流程。
* 因此本脚本**默认只填不发布**; 发布必须显式 `--publish`, 且脚本内置"字数校验不通过就拒绝发布"的闸门。

实测有效/踩过的坑(照做即可)
--------------------------------------------------------------------
1. **代码必须内联**: `playwright-cli run-code` 的执行体是**单一函数表达式**, 不支持 `require/import`,
   所以正文不能从文件读、只能内联进 JS —— 本脚本负责转义(中文直接内联, 引号/换行由 json.dumps 处理),
   不要手抄正文进 JS。
2. **必须幂等**: 脚本跑两次会把正文原样叠一遍(实测编辑器里变成 962 字 = 2×481)。所以每次先
   `Ctrl+A` + `Delete` 清空并**回读确认归零**, 再插入。
3. **吸顶 header 会拦截点击**: `WriteAnswerButton` 明明可见可用, 普通 `click()` 必然 30s 超时
   (`<header class="AppHeader"> intercepts pointer events`)。兜底用 `dispatchEvent('click')`。
4. **插入方式**: 聚焦 contenteditable → `keyboard.insertText(段落)`, 段间按两个 `Enter` 形成空行分段。
5. **知乎「回答」没有标题字段**(只有「文章」有): 稿子的 `# 标题` **不发**, 只发正文。
6. **发布前必须回读校验**: 读 `innerText()` 去空白后与草稿字数比对, 不等就**拒绝发布**并回报。
   注意页面上的「字数」计数器**会滞后**(实测截图时还显示旧值 962, 稍后才变成 481), 所以以 innerText 为准。
7. 发布后**会自动关注该问题**(实测两条都变成「已关注」)——属平台行为, 需要的话让用户手动取消。
8. 弹窗「发布成功」会盖住页面, 下一步用 `press Escape` 关掉。
9. **「点了发布」不等于「发出去了」**(2026-09-13 实测 rank15-19): 点完「发布回答」后 URL 不一定跳到
   `/answer/<id>` —— 编辑器仍开着、按钮仍是「发布回答」, 页面看着像正常但答案根本没提交。故脚本
   **以「URL 是否变成 `/answer/<id>`」为成功判据**, 不成立就重试一次并如实回报 `published:false`。
   早期实现点完就报 `published:true`, 属**假成功**(整批 18 条都报成功, 实际只有 13 条发布)。

用法(两步, 不要合成一条)
--------------------------------------------------------------------
  # 1) 生成 run-code 脚本(默认只填不发布)
  python publish_draft.py --draft <draft_n.md> --out <fill.js> [--publish]

  # 2) 用 playwright-cli 执行(需已 open 过该问题页; 见 SKILL.md 流程)
  cd D:\\...\\playwright-cli
  node playwright-cli.js run-code --filename=<fill.js>
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract          # 配额提示正则 / 发布策略常量的唯一定义处

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="生成知乎发帖用的 playwright run-code 脚本(默认只填不发布)")
    ap.add_argument("--draft", required=True, help="draft_<n>.md 路径")
    ap.add_argument("--out", required=True, help="生成的 .js 路径")
    ap.add_argument("--publish", action="store_true",
                    help="填完直接点发布(**需用户明确授权**; 默认只填, 保留人工点发布)")
    ap.add_argument("--shot", default=r"D:\DSH\shot_filled.png", help="填充后截图")
    ap.add_argument("--shot2", default=r"D:\DSH\shot_published.png", help="发布后截图")
    args = ap.parse_args()

    raw = io.open(args.draft, encoding="utf-8-sig").read().strip()
    lines = raw.splitlines()
    title = ""
    if lines and lines[0].lstrip().startswith("#"):
        title = lines[0].lstrip("# ").strip()
        lines = lines[1:]
    # 知乎「回答」无标题字段 ⇒ 只发 body; title 仅用于日志
    paras = [p.strip() for p in "\n".join(lines).strip().split("\n\n") if p.strip()]

    pub = ""
    if args.publish:
        pub = f"""
  // ---- 发布(仅在字数校验通过后执行) ----
  if (!(len === expected && len > 0)) {{
    return {{ ok: false, reason: 'LEN_MISMATCH_REFUSE_PUBLISH', len: len, expected: expected }};
  }}
  let pubBtn = page.getByRole('button', {{ name: '发布回答' }}).last();
  if (await pubBtn.count() === 0) {{
    pubBtn = page.getByRole('button', {{ name: /^发布$/ }}).last();
  }}
  if (await pubBtn.count() === 0) {{ return {{ ok: false, reason: 'NO_PUBLISH_BUTTON' }}; }}
  await pubBtn.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  const limitRe = new RegExp({json.dumps(contract.PUBLISH_LIMIT_RE)});
  let limitHit = false, limitText = '';
  const scanLimit = async () => {{
    // 提示是 toast 会自己消失 ⇒ 每次点击后**立刻**扫一遍, 不能等 6 秒后再扫(实测会扫不到,
    // 于是"配额上限"被记成含义不明的 blocked)
    try {{
      const bt = await page.locator('body').innerText();
      const mm = bt.match(limitRe);
      if (mm && !limitHit) {{
        limitHit = true;
        limitText = bt.slice(Math.max(0, mm.index - 30), mm.index + 40).replace(/\\s+/g, ' ');
      }}
    }} catch (e) {{}}
  }};
  try {{ await pubBtn.click({{ timeout: 8000 }}); }}
  catch (e) {{ await pubBtn.dispatchEvent('click'); }}
  await page.waitForTimeout(1200); await scanLimit();
  await page.waitForTimeout(4800); await scanLimit();

  // **必须验证**: 实测点击后 URL 不一定跳到 /answer/(rank15-19 出现"点了但没发出去",
  // 编辑器仍开着、按钮仍是「发布回答」)。原实现点完就无条件报 published:true, 属假成功。
  let published = /\\/answer\\/\\d+/.test(page.url());
  if (!published) {{
    // 重试一次(可能被吸顶 header 拦了点击, 或首点只触发了确认)
    try {{
      const b2 = page.getByRole('button', {{ name: '发布回答' }}).last();
      if (await b2.count() > 0) {{
        try {{ await b2.click({{ timeout: 8000 }}); }}
        catch (e) {{ await b2.dispatchEvent('click'); }}
        await page.waitForTimeout(1200); await scanLimit();
        await page.waitForTimeout(4800); await scanLimit();
        published = /\\/answer\\/\\d+/.test(page.url());
      }}
    }} catch (e) {{}}
  }}
  await page.screenshot({{ path: {json.dumps(args.shot2)} }});
  return {{ ok: published, published: published, len: len, expected: expected,
            urlAfter: page.url(), titleAfter: await page.title(),
            limitHit: limitHit, limitText: limitText,
            reason: published ? '' : (limitHit ? 'DAILY_QUOTA_LIMIT'
                                              : 'CLICK_DID_NOT_NAVIGATE_TO_ANSWER') }};
"""
    js = f"""async page => {{
  const paras = {json.dumps(paras, ensure_ascii=False, indent=2)};
  let expected = 0;
  for (const p of paras) expected += p.replace(/\\s/g, '').length;

  // 1) 打开编辑器(若尚未打开)。三种入口都要试 —— 实测只找「写回答」会失败:
  //    页面若已存在**自动草稿**(上一次点了发布但没提交成功), 页头按钮变成「编辑回答」,
  //    此时没有「写回答」按钮, 编辑器也不会自己出现 ⇒ locator.waitFor 超时(rank15-19 实测)。
  if (await page.locator('div[contenteditable="true"]').count() === 0) {{
    let open = page.getByRole('button', {{ name: '写回答' }}).first();
    if (await open.count() === 0) {{
      open = page.getByRole('button', {{ name: /编辑回答/ }}).first();
    }}
    if (await open.count() === 0) {{          // 兜底: 草稿入口文案
      open = page.getByText(/草稿备份|继续编辑|编辑我的回答/).first();
    }}
    if (await open.count() > 0) {{
      await open.scrollIntoViewIfNeeded();
      try {{ await open.click({{ timeout: 8000 }}); }}
      catch (e) {{ await open.dispatchEvent('click'); }}   // 吸顶 header 拦截指针事件时的兜底
      await page.waitForTimeout(3500);
    }}
  }}

  // 2) 定位正文编辑器
  const ed = page.locator('div[contenteditable="true"]').last();
  await ed.waitFor({{ state: 'visible', timeout: 25000 }});
  await ed.click();
  await page.waitForTimeout(500);

  // 3) 清空(幂等关键): 反复 Ctrl+A + Delete 直到回读为 0
  let afterClear = -1;
  for (let k = 0; k < 4; k++) {{
    await page.keyboard.press('Control+a');
    await page.waitForTimeout(150);
    await page.keyboard.press('Delete');
    await page.waitForTimeout(400);
    afterClear = (await ed.innerText()).replace(/\\s/g, '').length;
    if (afterClear === 0) break;
  }}
  await page.waitForTimeout(400);

  // 4) 只插入一次(段间两个 Enter ⇒ 空行分段)
  for (let i = 0; i < paras.length; i++) {{
    if (i > 0) {{ await page.keyboard.press('Enter'); await page.keyboard.press('Enter'); }}
    await page.keyboard.insertText(paras[i]);
    await page.waitForTimeout(200);
  }}
  await page.waitForTimeout(1600);

  // 5) 回读校验(以 innerText 为准, 页面计数器会滞后)
  const t = await ed.innerText();
  const len = t.replace(/\\s/g, '').length;
  const paraCount = t.split('\\n').map(x => x.trim()).filter(Boolean).length;
  await page.screenshot({{ path: {json.dumps(args.shot)} }});
{pub}
  return {{ ok: len === expected, afterClear: afterClear, len: len, expected: expected,
            paraCount: paraCount, head: t.replace(/\\s/g, '').slice(0, 26) }};
}}
"""
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(js)
    print("生成 %s | 段落 %d | 正文 %d 字 | 发布=%s | 标题(知乎回答无标题, 不发): %s"
          % (args.out, len(paras), sum(len(p.replace(" ", "")) for p in paras),
             "是(需授权)" if args.publish else "否(只填)", title or "(无)"))


if __name__ == "__main__":
    main()
