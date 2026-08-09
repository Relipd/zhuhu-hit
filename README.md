# zhuhu-hit

搜集知乎热点，按月分类，形成长期热点追踪及思路拓展。

知乎热榜每日跟进：抓热榜前 20 → 多变体搜索合并回答 → 逐条四维分析（立场/解决思路/判断逻辑/情绪倾向）→ 前 10 热点拓展（Agent Swarm 并行发散）→ 产出月度 Excel + 分页式 HTML 展示页。原始数据按日期归档，可回溯。

一个可复用的 Claude Code 项目级 skill（`skills/zhihu-hot-track/`），所有脚本参数化，不写死任何绝对路径。

## 核心特性

- **全流程自动化**：抓取 → 全文补全（Cookie 解锁截断回答）→ 四维分析 → 校验 → Excel / HTML 交付，一次斜杠命令跑完。
- **热点拓展（前 10 rank）**：`Agent Swarm` 并行——每个 rank 独立 subagent 动态发散搜索（每轮 1 条查询、由结果驱动下一条、收敛即止），主 Agent 汇总去重。
- **话题库双轨索引（跨日期查重）**：`index.json`（机读，url 唯一键去重）+ `话题库.md`（人读展示，自动重建）；发散搜索前程序化查重，已收录主题不重复搜索，同类型案例 ≤3。
- **收敛性判断**：每轮检索前查重（查询主题去重 / 结果 URL 去重 / 同类型上限），连续 2 轮无新线索即止，避免无意义重复搜索。
- **情绪分析由 Agent 亲自判断**（禁止脚本/关键词判定），脚本只做值域与格式校验。
- **HTML 展示规范固定**（anti-slop）：墨蓝渐变 + 暖纸底 + 原生 `<details>` 折叠 + 无 JS，分页式索引 + 每问题一页。

## 目录结构

```
skills/zhihu-hot-track/
├── SKILL.md          # 完整流程规范：抓取/分析/校验/交付 + 约束 + 踩坑记录
└── scripts/          # 全流程通用脚本（参数化）
    ├── run.py        # 热榜 + 6 变体搜索 + 合并去重
    ├── fulltext.py   # 回答全文补全 + 截断检测（--cookie 解锁全文）
    ├── search_many.py# 热点拓展动态搜索（单条 queries.json 驱动，支持限流重试）
    ├── check.py      # 完整性/情绪值域校验
    ├── fill_excel.py # 填月度 Excel（情绪下拉、截断备注、热点拓展 sheet）
    ├── gen_html.py   # 生成 HTML 展示页（分页式 + 热点拓展块）
    └── topic_lib.py  # 话题库双轨维护：update 增量收录 / search 查重 / rebuild
```

## 依赖

- Python 3.8+
- [zhihu-cli](https://github.com/zhihu/zhihu-cli)（知乎开放平台 CLI，`%LOCALAPPDATA%\ZhihuCLI\current\zhihu-cli.exe` 或环境变量 `ZHIHU_CLI` 指定），需 `zhihu-cli auth` 配置 Access Secret
- （可选）[playwright-cli](https://github.com/microsoft/playwright-cli)：网页登录 Cookie 自动提取（全文解锁），不可用时手动复制
- 分析步骤（analysis.json 四维分析）由 Claude/Agent 完成，脚本不做任何语义判断

## 快速开始

```text
ROOT=<你的工作根目录>
D=2026-08-08

1. 抓取:   python scripts/run.py --root %ROOT% --date %D% --variants 6
2. 补全:   python scripts/fulltext.py --root %ROOT% --date %D% --cookie raw/<D>/cookies.txt
3. 分析:   Agent 读 raw/<D>/answers_summary.json 逐条写四维分析 → raw/<D>/analysis.json
4. 拓展:   Agent Swarm 并行处理前 10 rank（动态发散搜索）→ raw/<D>/extension.json
           python scripts/topic_lib.py update --root %ROOT% --date %D%   # 纳入话题库
5. 校验:   python scripts/check.py --root %ROOT% --date %D%
6. 填表:   python scripts/fill_excel.py --root %ROOT% --date %D%
7. 出网页: python scripts/gen_html.py --root %ROOT% --date %D%
```

完整规范（查询变体规则、四维分析约束、热点拓展发散逻辑、话题库机制、HTML 规范、踩坑记录）见 [skills/zhihu-hot-track/SKILL.md](skills/zhihu-hot-track/SKILL.md)。

## 说明

- 仓库仅含 skill 代码与文档，不含任何抓取数据、凭据或本地路径。
- 知乎热榜/回答为公开数据；原始数据快照按日期存于用户本地工作目录（如 `跟进excel-YYYY-MM.xlsx`、`raw/YYYY-MM-DD/`、`话题库/`）。
- Cookie 等敏感凭证在流程收尾后自动删除，不落盘。
