# 投研alpha

首期目标：把当前已在用的四类信源能力统一接入到一个可复用项目中，按日拉取并落地为标准化 JSON。

## 项目结构

```text
projects/投研alpha/
├── adapters/
│   ├── __init__.py
│   ├── common.py                # 统一字段/统一返回结构
│   ├── cninfo_base.py           # 复用巨潮公告查询逻辑
│   ├── cninfo_fulltext.py       # cninfo 公告（fulltext）
│   ├── cninfo_relation.py       # cninfo 机构调研（relation）
│   ├── p5w_interaction.py       # p5w 互动问答（复用 skills 脚本）
│   └── tushare_forecast.py      # tushare 业绩预告
├── collect.py                   # 按日期一键聚合入口
└── output/
    └── YYYY-MM-DD/
        ├── cninfo_fulltext.json
        ├── cninfo_relation.json
        ├── p5w_interaction.json
        ├── tushare_forecast.json
        └── summary.json
```

## 统一输出规范

每条数据最小字段统一为：

- `date`
- `source`
- `symbol`
- `company`
- `title`
- `summary`
- `url`
- `raw`

每个适配器输出文件顶层统一为：

- `date`
- `source`
- `count`
- `error`（失败不静默，写明错误）
- `items`

## 环境变量

至少建议配置：

- `TUSHARE_TOKEN`：tushare 业绩预告接口

可在工作区 `.env` 中维护，再按现有运行习惯加载环境变量。

## 一键运行

```bash
cd /home/admin/.openclaw/workspace/projects/投研alpha
python3 collect.py --date 2026-02-26 --slot 2200
python3 render_static_report.py --date 2026-02-26
python3 scripts/publish_daily.py --date 2026-02-26 --slot 2200
```

## 定时更新 + GitHub Pages 发布（已内置 workflow）

工作流文件：`.github/workflows/daily-update-pages.yml`

- 每天 **07:10（北京时间）**：执行 `slot=0700`（早盘前快照，偏新闻）
- 每天 **22:10（北京时间）**：执行 `slot=2200`（收盘后全量）
- 同时支持手动触发（`workflow_dispatch`）

运行结果：

- 原始数据落地：`output/YYYY-MM-DD/*.json`
- 页面发布目录：`docs/`
  - `docs/index.html`：入口页（最近 30 天）
  - `docs/YYYY-MM-DD/index.html`：日报页面
  - `docs/data/YYYY-MM-DD/*.json`：对应原始数据

### 首次启用步骤

1. 在 GitHub 仓库设置里打开 Pages：
   - **Source** 选 `Deploy from a branch`
   - Branch 选 `master`（或 `main`），Folder 选 `/docs`
2. 在仓库 Secrets 中配置（按需）：
   - `TUSHARE_TOKEN`
   - `TAVILY_API_KEY`
3. 在 Actions 页面手动运行一次 `Daily Update + Pages` 验证。

## 已接入信源清单（第一步）

1. cninfo 公告（`fulltext`）
2. cninfo 机构调研（`relation`）
3. p5w 互动问答
4. tushare 业绩预告（`forecast`）

## 实测（2026-02-26）

运行后生成目录：`output/2026-02-26/`

各类条数：

- `cninfo_fulltext`: **912**
- `cninfo_relation`: **13**
- `p5w_interaction`: **0**
- `tushare_forecast`: **2**

汇总见：`output/2026-02-26/summary.json`
