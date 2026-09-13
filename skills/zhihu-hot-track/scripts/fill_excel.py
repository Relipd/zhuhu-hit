# -*- coding: utf-8 -*-
"""知乎热榜跟进 - 填月度 Excel(不存在时自动建模板; 新日期 sheet 插到最前)。

用法:
  python fill_excel.py --root <工作根目录> --date 2026-08-08 [--xlsx <文件路径>]

读: <root>/raw/<date>/{hot.json, answers_summary.json, analysis.json}
约定: 一级行=问题, 二级行=回答(≤10条); 月份文件内按天分 sheet, 最新日期在前。
"""
import argparse, io, json, os, sys

import contract   # 数据契约:文件名 / 字段 / 值域的单一定义处(见 contract.py)
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HEADERS = ["层级", "问题序号", "排名", "问题标题", "原问题URL", "问题点赞数", "问题本质",
           "回答序号", "回答内容", "回答点赞数",
           "立场分析", "解决思路", "判断逻辑", "情绪倾向",
           "情绪标签", "情绪强度", "情绪指向", "备注"]
FONT = "微软雅黑"
HDR_FILL = PatternFill("solid", fgColor="2F5496")
HDR_FONT = Font(name=FONT, size=10, bold=True, color="FFFFFF")
Q_FILL = PatternFill("solid", fgColor="D6E4F0")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="top")
WIDTHS = [7, 8, 6, 40, 36, 9, 40, 8, 50, 9, 26, 26, 26, 26, 20, 9, 12, 12]

DOC = [
    ("结构", "按天分页: 每天一个 sheet(YYYY-MM-DD), 最新日期排最前。每月一个 Excel 文件。"),
    ("一级行-问题", "层级=问题: 问题序号(1-20), 排名, 标题, 原问题URL, 问题点赞数(接口无则取最高赞回答并备注), 问题本质。"),
    ("二级行-回答", "层级=回答: 问题序号(归属), 回答序号(1-10), 回答内容(原文), 回答点赞数。"),
    ("回答四维分析", "立场分析/解决思路/判断逻辑/情绪倾向 基于原文归纳, 不编造。"),
    ("情绪模型(2026-09-13 起)", "多元化情绪: 情绪标签(" + "/".join(contract.EMOTION_TAGS)
     + ", 每条 1-3 个) + 情绪强度(1 极淡-5 极强) + 情绪指向(" + "/".join(contract.EMOTION_TARGETS)
     + ")。均由 Agent 阅读原文判断, 禁止脚本/程序判定。"),
    ("历史日期", "2026-09-11 及更早的 sheet 是旧三元模型(情绪判断: 积极/中立/消极), 保留原样不改写。"),
    ("示例行", "模板首次创建时含示例日 sheet, 正式抓取后由 fill_excel 替换。"),
    ("数据来源", "zhihu-cli: hot + search zhihu 多变体查询合并。详见 skill 文档。"),
]

def ensure_workbook(path, year, month):
    """无文件时创建月度模板(含说明 sheet, 无示例日)"""
    wb = Workbook()
    ws = wb.active
    ws.title = "说明"
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 100
    for i, (a, b) in enumerate(DOC, 1):
        ca, cb = ws.cell(row=i, column=1, value=a), ws.cell(row=i, column=2, value=b)
        ca.font = Font(name=FONT, size=10, bold=True)
        cb.font = Font(name=FONT, size=10)
        cb.alignment = Alignment(vertical="top", wrap_text=True)
        if i == 1:
            for c in (ca, cb):
                c.fill, c.font = HDR_FILL, HDR_FONT
    ws.freeze_panes = "A2"
    wb.save(path)
    print(f"新建月度模板: {path}")

def emotion_cells(A):
    """情绪三列的值(标签/强度/指向)。

    两套模型并存(2026-09-13 起为多标签+强度+指向): 新数据直接取三字段;
    历史三元数据(只有 judge)把三值放进标签列、后两列留空 —— 这样即便对旧日期重跑 fill_excel,
    也不会因为字段缺失而崩, 且信息不丢。
    """
    if A.get("emotion_tags") is not None:
        tags = "、".join(A.get("emotion_tags") or [])
        return [tags or None, A.get("emotion_intensity"), A.get("emotion_target")]
    if A.get("judge"):
        return [A["judge"] + "(旧三元)", None, None]
    return [None, None, None]


def style_row(ws, is_q):
    for c in ws[ws.max_row]:
        c.font = Font(name=FONT, size=10)
        c.border = BORDER
        c.alignment = Alignment(vertical="top", wrap_text=True)
        if is_q:
            c.fill = Q_FILL
    for col in (2, 3, 6, 8, 10, 15, 16, 17):
        ws.cell(row=ws.max_row, column=col).alignment = CENTER

def write_doc_sheet(wb):
    """刷新「说明」sheet(每次运行都重写)。

    为什么每次写: 说明 sheet 原先只在**新建工作簿**时生成, 因此模型/列结构改了它也不会更新 ——
    实测 2026-09-13 情绪改多元化后, 说明页仍在讲旧三值, 交付物自相矛盾。
    """
    if "说明" not in wb.sheetnames:
        ws = wb.create_sheet("说明", len(wb.sheetnames))
    else:
        ws = wb["说明"]
        ws.delete_rows(1, ws.max_row + 1)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 100
    for i, (a, b) in enumerate(DOC, 1):
        ca, cb = ws.cell(row=i, column=1, value=a), ws.cell(row=i, column=2, value=b)
        ca.font = Font(name=FONT, size=10, bold=True)
        cb.font = Font(name=FONT, size=10)
        cb.alignment = Alignment(vertical="top", wrap_text=True)
        if i == 1:
            for c in (ca, cb):
                c.fill, c.font = HDR_FILL, HDR_FONT
    ws.freeze_panes = "A2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--xlsx", default=None, help="Excel 路径(默认 <root>/跟进excel-YYYY-MM.xlsx)")
    args = ap.parse_args()

    year, month = args.date.split("-")[0], args.date.split("-")[1]
    xlsx = args.xlsx or contract.xlsx_path(args.root, args.date)
    if not os.path.exists(xlsx):
        ensure_workbook(xlsx, year, month)

    summary = json.load(open(contract.path_answers(args.root, args.date), encoding="utf-8"))
    an = json.load(open(contract.path_analysis(args.root, args.date), encoding="utf-8"))
    ext_path = contract.path_extension(args.root, args.date)
    ext = json.load(open(ext_path, encoding="utf-8")) if os.path.exists(ext_path) else None

    wb = load_workbook(xlsx)
    write_doc_sheet(wb)
    if args.date in wb.sheetnames:
        del wb[args.date]
    ws = wb.create_sheet(args.date, 0)
    ws.append(HEADERS)
    for c in ws[1]:
        c.fill, c.font = HDR_FILL, HDR_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER

    for s in summary:
        rank, q = s["rank"], an[str(s["rank"])]
        top = s["answers"][0]["likes"] if s["answers"] else None
        # 覆盖度标注(约束: 不得让读者以为"抓到几条 = 该问题只有几条")
        cov = ""
        if s.get("total_answers"):
            cov = " | 覆盖 {}/{} ({:.1f}%)".format(
                len(s["answers"]), s["total_answers"],
                len(s["answers"]) / s["total_answers"] * 100)
        note_q = ("问题点赞数=该问题最高赞回答" if top is not None else "") + cov
        if s.get("extra"):
            note_q = (note_q + " | " if note_q else "") + "追加追踪(非榜单条目)"
        ws.append(["问题", rank, rank, s["title"], s["url"], top, q["essence"],
                   None, None, None, None, None, None, None, None, None, None,
                   note_q or None])
        style_row(ws, True)
        ws.cell(row=ws.max_row, column=5).hyperlink = s["url"]
        for i, a in enumerate(s["answers"], 1):
            A = q["answers"][i - 1]
            # 四维主体按契约顺序落列(顺序由 contract.ANALYSIS_CORE 决定, 不在此处重复声明);
            # 情绪占 3 列(标签/强度/指向), 由 emotion_cells 兼容新旧两套模型。
            dims = [A[f] for f in contract.ANALYSIS_CORE] + emotion_cells(A)
            note = {"truncated": "接口摘要，全文需登录网页查看", "summary": "接口摘要(全文抓取失败)",
                    "full": None}.get(a.get("content_status"))
            ws.append(["回答", rank, None, None, None, None, None, i, a["text"], a["likes"]]
                      + dims + [note])
            style_row(ws, False)

    # 情绪列: 强度(O列)与指向(Q列)是单值 → 硬下拉约束; 标签列(P列)是 1-3 个多值,
    # Excel 的 list 校验无法表达多选(会把合法值判为非法), 故不加硬下拉, 词表写在「说明」sheet。
    for col, vals, title in (("P", list(contract.EMOTION_INTENSITY), "情绪强度"),
                             ("R", list(contract.EMOTION_TARGETS), "情绪指向")):
        dv = DataValidation(type="list", formula1='"%s"' % ",".join(str(v) for v in vals),
                            allow_blank=True, showErrorMessage=True, errorTitle=title,
                            error="仅允许: %s(由 Agent 阅读原文判断, 禁止脚本/程序判定)"
                                  % " / ".join(str(v) for v in vals))
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{ws.max_row}")

    for i, w in enumerate(WIDTHS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:R{ws.max_row}"

    # ---- 热点拓展板块(extension.json; 2026-09-13 起覆盖全部条目, 不再只写前 10) ----
    if ext:
        # 末列「发散想法 / 关系 / 信源等级 / 多源印证 / 链接」为链式与事实性复核新增;
        # 追加在末尾, 保证历史日期的行不会错位。
        EXT_HEADERS = ["日期", "排名", "问题标题", "扩展类型", "扩展内容", "来源链接", "备注",
                       "发散想法", "关系", "信源等级", "多源印证", "链接"]
        ext_sheet = wb.create_sheet("热点拓展") if "热点拓展" not in wb.sheetnames else wb["热点拓展"]
        # 保留其他日期的行
        # 注意: 历史上每次重跑都会把残留的表头行(首列 = "日期")当作"其他日期的数据行"
        # 再保留一次, 于是表头逐次累积(实测 2026-09 表里积了 4 行重复表头)。此处一并过滤。
        old_rows = []
        if ext_sheet.max_row > 1:
            for r in ext_sheet.iter_rows(min_row=2, values_only=True):
                if r[0] in (None, EXT_HEADERS[0]) or r[0] == args.date:
                    continue
                old_rows.append(r)
        # 清空整表再写表头: 只删 2..N 行会保留第 1 行的旧表头, 而 append 又把新表头写到第 2 行,
        # 于是每次重跑都多一行重复表头(实测 2026-09 表里积到 4 行)。
        ext_sheet.delete_rows(1, max(ext_sheet.max_row, 1))
        ext_sheet.append(EXT_HEADERS)
        for c in ext_sheet[1]:
            c.fill, c.font = HDR_FILL, HDR_FONT
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = BORDER
        new_rows = []
        for rank_str in sorted(ext.keys(), key=lambda k: int(k)):
            e = ext[rank_str]
            chains = e.get("chains") or []
            if chains:
                # 链式: 每个想法一行标题(扩展类型=想法), 其下证据行带「印证/反驳/边界」, 末尾一行落点
                # 有链接就附上: 想法行填「提炼该想法的回答」链接, 落点行填本链全部来源链接。
                for ch in chains:
                    src = ch.get("source") or {}
                    labels = []
                    if src.get("answer_index"):
                        labels.append("回答 %s" % src["answer_index"])
                    if src.get("likes") not in (None, ""):
                        labels.append("%s 赞" % src["likes"])
                    src_note = ("出处：" + "·".join(labels)) if src.get("url") else ""
                    new_rows.append([args.date, int(rank_str), e["title"], "想法",
                                     ch.get("claim", ""), src.get("url", ""), src_note,
                                     ch.get("claim", ""), "", "", "", ""])
                    for it in ch.get("evidence", []):
                        tier = it.get("source_tier") or ""
                        tier_txt = ("%s·%s" % (tier, contract.EXT_SOURCE_TIERS[tier])
                                    if tier in contract.EXT_SOURCE_TIERS else "")
                        corr = it.get("corroboration") or {}
                        corr_txt = ("独立来源 %d 组" % corr["groups"]
                                    if corr.get("groups") else "")
                        new_rows.append([args.date, int(rank_str), e["title"], it["type"], it["content"],
                                         it.get("url", ""), it.get("note", ""),
                                         ch.get("claim", ""), it.get("relation", ""),
                                         tier_txt, corr_txt, it.get("link_status", "")])
                    if ch.get("takeaway"):
                        # 落点行附本链全部来源(多个链接换行分隔), 便于顺着结论回看证据
                        ev_urls = [it.get("url", "") for it in ch.get("evidence", []) if it.get("url")]
                        new_rows.append([args.date, int(rank_str), e["title"], "落点",
                                         ch["takeaway"], "\n".join(ev_urls),
                                         "本链来源 %d 条" % len(ev_urls) if ev_urls else "",
                                         ch.get("claim", ""), "", "", "", ""])
            else:
                # 兼容历史格式(无 chains): 扁平条目
                for it in e.get("items", []):
                    new_rows.append([args.date, int(rank_str), e["title"], it["type"], it["content"],
                                     it.get("url", ""), it.get("note", ""), "", it.get("relation", "")])
            if e.get("thinking"):
                new_rows.append([args.date, int(rank_str), e["title"], "思考过程", e["thinking"],
                                 "", "", "", "", "", "", ""])
        all_rows = new_rows + old_rows
        all_rows.sort(key=lambda r: (str(r[0]), r[1]), reverse=True)  # 最新日期在上
        for r in all_rows:
            ext_sheet.append(list(r) + [None] * (len(EXT_HEADERS) - len(r)))  # 历史行补空列
            for c in ext_sheet[ext_sheet.max_row]:
                c.font = Font(name=FONT, size=10)
                c.border = BORDER
                c.alignment = Alignment(vertical="top", wrap_text=True)
            u = ext_sheet.cell(row=ext_sheet.max_row, column=6)
            if r[5] and "\n" not in str(r[5]):     # 多个链接的单元格(落点行)不做超链接, 避免指向无效地址
                u.hyperlink = r[5]
        for i, w in enumerate([11, 6, 36, 10, 52, 36, 18, 40, 8, 22, 14, 10], 1):
            ext_sheet.column_dimensions[get_column_letter(i)].width = w
        ext_sheet.freeze_panes = "A2"
        ext_sheet.auto_filter.ref = f"A1:L{ext_sheet.max_row}"
        wb.move_sheet("热点拓展", offset=len(wb.sheetnames) - 2)

    # ---- 拟答参考稿(ext_search/<D>/rank_<n>/draft_<n>.md, 2026-09-13 起) ----
    # 与「热点拓展」同款累积表: 保留其他日期的行, 重写当日行, 表头只留一行(坑 31)。
    draft_rows = []
    for s in summary:
        rk = s["rank"]
        p = contract.path_draft(args.root, args.date, rk)
        if not os.path.exists(p):
            continue
        try:
            raw = io.open(p, encoding="utf-8-sig").read().strip()
        except Exception:
            continue
        if not raw:
            continue
        lines = raw.splitlines()
        title = lines[0].lstrip("# ").strip() if lines and lines[0].lstrip().startswith("#") else ""
        body = "\n".join(lines[1:] if title else lines).strip()
        draft_rows.append([args.date, rk, s["title"], title, body])
    H = list(contract.DRAFT_HEADERS)
    ds = wb[contract.DRAFT_SHEET] if contract.DRAFT_SHEET in wb.sheetnames \
        else wb.create_sheet(contract.DRAFT_SHEET)
    old = []
    if ds.max_row > 1:
        for r in ds.iter_rows(min_row=2, values_only=True):
            if r[0] in (None, H[0]) or r[0] == args.date:
                continue
            old.append(r)
    ds.delete_rows(1, max(ds.max_row, 1))
    ds.append(H)
    for c in ds[1]:
        c.fill, c.font = HDR_FILL, HDR_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER
    for r in sorted(draft_rows + old, key=lambda x: (str(x[0]), -int(x[1])), reverse=True):
        ds.append(list(r) + [None] * (len(H) - len(r)))
        for c in ds[ds.max_row]:
            c.font = Font(name=FONT, size=10)
            c.border = BORDER
            c.alignment = Alignment(vertical="top", wrap_text=True)
    for i, w in enumerate([11, 6, 34, 30, 90], 1):
        ds.column_dimensions[get_column_letter(i)].width = w
    ds.freeze_panes = "A2"
    ds.auto_filter.ref = f"A1:E{max(ds.max_row, 1)}"

    if "说明" in wb.sheetnames:
        wb.move_sheet("说明", offset=len(wb.sheetnames) - 1)
    wb.save(xlsx)
    print(f"saved: {xlsx} | sheet {args.date}: {len(summary)} 问题, "
          f"{sum(len(s['answers']) for s in summary)} 回答, 共 {ws.max_row - 1} 行"
          + (f" | 热点拓展: {len(new_rows) if ext else 0} 行" if ext else "")
          + (f" | 拟答参考: {len(draft_rows)} 篇" if draft_rows else ""))

if __name__ == "__main__":
    main()
