# zhuhu-hit

搜集知乎热点，按月分类，形成长期热点追踪及思路拓展。
![Uploading image.png…]()

知乎热榜每日跟进：抓热榜前 20 → 多变体搜索合并回答 → 逐条四维分析（立场/解决思路/判断逻辑/情绪倾向）→ 产出月度 Excel + 分页式 HTML 展示页。原始数据按日期归档，可回溯。

一个可复用的 Claude Code 项目级 skill（`skills/zhihu-hot-track/`），所有脚本参数化，不写死任何绝对路径。

## 目录结构

```
skills/zhihu-hot-track/
├── SKILL.md          # 完整流程规范：抓取/分析/校验/交付 + 约束 + 踩坑记录
└── scripts/          # 全流程通用脚本（参数化）
    ├── run.py        # 热榜 + 6 变体搜索 + 合并去重
    ├── fulltext.py   # 回答全文补全 + 截断检测
    ├── search_many.py# 热点拓展批量搜索（queries.json 驱动）
    ├── check.py      # 完整性/情绪值域校验
    ├── fill_excel.py # 填月度 Excel（情绪下拉、截断备注、热点拓展 sheet）
    └── gen_html.py   # 生成 HTML 展示页
```

## 依赖

- Python 3.8+
- [zhihu-cli](https://github.com/zhihu/zhihu-cli)（知乎开放平台 CLI，`%LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe` 或环境变量 `ZHIHU_CLI` 指定），需 `zhihu-cli auth` 配置 Access Secret
- 分析步骤（analysis.json 四维分析）由 Claude/Agent 完成，脚本不做任何语义判断

## 快速开始

```text
ROOT=<你的工作根目录>
D=2026-08-08

1. 抓取:   python scripts/run.py --root %ROOT% --date %D% --variants 6
2. 补全:   python scripts/fulltext.py --root %ROOT% --date %D%
3. 分析:   Agent 读 raw/<D>/answers_summary.json 逐条写四维分析 → raw/<D>/analysis.json
4. 校验:   python scripts/check.py --root %ROOT% --date %D%
5. 填表:   python scripts/fill_excel.py --root %ROOT% --date %D%
6. 出网页: python scripts/gen_html.py --root %ROOT% --date %D%
```

完整规范（查询变体规则、四维分析约束、HTML 规范、踩坑记录）见 [skills/zhihu-hot-track/SKILL.md](skills/zhihu-hot-track/SKILL.md)。

## 说明

- 仓库仅含 skill 代码与文档，不含任何抓取数据、凭据或本地路径。
- 知乎热榜/回答为公开数据；原始数据快照按日期存于用户本地工作目录（如 `跟进excel-YYYY-MM.xlsx`、`raw/YYYY-MM-DD/`）。
