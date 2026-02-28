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
python3 collect.py --date 2026-02-26
```

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
