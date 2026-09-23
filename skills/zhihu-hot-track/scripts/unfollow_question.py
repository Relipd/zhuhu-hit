# -*- coding: utf-8 -*-
"""取消当前知乎问题页的关注 —— **可选后续功能**(2026-09-13 用户要求)。

背景: **人工粘贴发布**回答后, 知乎会自动关注该问题(实测两条都变成「已关注」)。
这是平台行为, 不是误点。本脚本把"发布后清尾"做成可复用的一步:

  # 1) 生成取消关注的 run-code 脚本(与会话无关, 只作用于"当前页面")
  python unfollow_question.py --out <unfollow.js>
  # 2) 对每个目标问题页执行
  cd <playwright-cli 仓库>
  node playwright-cli.js goto <问题URL>
  node playwright-cli.js run-code --filename=<unfollow.js>

幂等: 已经是「关注问题」状态时直接返回 skipped, 不会反向关注。
⚠️ 这仍属"操作真实账号"的自动化(2026-09-16 起自动发帖已删除, 本脚本是仅存的浏览器自动化之一,
 Cookie 获取是另一处); 未经用户要求不要执行。
"""
import argparse
import io
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

JS = r"""async page => {
  const snap = async () => (await page.locator('button, a, div[role="button"]').allInnerTexts())
    .map(s => s.trim()).filter(s => /^(已关注|关注问题|关注)$/.test(s));

  const before = await snap();
  let btn = page.getByRole('button', { name: '已关注' }).first();
  if (await btn.count() === 0) {
    btn = page.getByText('已关注', { exact: true }).first();
  }
  if (await btn.count() === 0) {
    return { ok: true, skipped: true, reason: 'NOT_FOLLOWED', before: before };
  }
  await btn.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  // 吸顶 header 可能拦截指针事件 ⇒ dispatchEvent 兜底(历史发布自动化踩过的同一坑)
  try { await btn.click({ timeout: 8000 }); }
  catch (e) { await btn.dispatchEvent('click'); }
  await page.waitForTimeout(2600);
  // 少数情况下会弹确认框
  let dialog = 'none';
  try {
    const c = page.getByRole('button', { name: /取消关注|确定|确认/ }).last();
    if (await c.count() > 0) { await c.click({ timeout: 4000 }); await page.waitForTimeout(1500); dialog = 'confirmed'; }
  } catch (e) { dialog = 'no-confirm-button'; }
  const after = await snap();
  return { ok: !after.includes('已关注'), before: before, after: after,
           dialog: dialog, url: page.url() };
}
"""


def main():
    ap = argparse.ArgumentParser(description="生成「取消问题关注」的 playwright run-code 脚本")
    ap.add_argument("--out", required=True, help="生成的 .js 路径")
    args = ap.parse_args()
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(JS)
    print("生成 %s\n用法: node playwright-cli.js goto <问题URL> && "
          "node playwright-cli.js run-code --filename=%s" % (args.out, args.out))


if __name__ == "__main__":
    sys.exit(main())
