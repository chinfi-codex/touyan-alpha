#!/usr/bin/env python3
import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from adapters import ADAPTERS
from adapters.tavily_news import save_news_data


def _adapter_source(adapter):
    return getattr(adapter, "SOURCE", adapter.__name__.split(".")[-1])


def _parse_sources(raw):
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def run_collect(date, base_dir, sources=""):
    out_dir = base_dir / "output" / date
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = _parse_sources(sources)
    summary = {
        "date": date,
        "counts": {},
        "counts_by_subcategory": {},
        "excluded_counts_by_rule": {},
        "errors": {},
    }

    for adapter in ADAPTERS:
        src = _adapter_source(adapter)
        if selected and src not in selected:
            continue

        # 公告、机构调研、业绩预告带次日窗口
        # 互动易只筛选当天日期
        if src in ("cninfo_fulltext", "cninfo_relation", "tushare_forecast"):
            result = adapter.collect(date, include_next_day=True)
        else:
            result = adapter.collect(date)

        src = result["source"]
        (out_dir / (src + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["counts"][src] = result.get("count", 0)

        for item in result.get("items") or []:
            sub = item.get("subcategory") or ""
            if sub:
                summary["counts_by_subcategory"][sub] = summary["counts_by_subcategory"].get(sub, 0) + 1
            if item.get("excluded"):
                rid = item.get("rule_id") or "excluded.unknown"
                summary["excluded_counts_by_rule"][rid] = summary["excluded_counts_by_rule"].get(rid, 0) + 1

        if result.get("error"):
            summary["errors"][src] = result["error"]

    # 收集新闻动态数据
    try:
        news_ok = save_news_data(date, base_dir / "output")
        summary["tavily_news"] = "ok" if news_ok else "failed"
    except Exception as e:
        summary["tavily_news"] = f"error: {str(e)[:100]}"

    # 收集知识星球数据
    try:
        from adapters.zsxq import save_zsxq_data
        zsxq_ok = save_zsxq_data(date, base_dir / "output")
        summary["zsxq"] = "ok" if zsxq_ok else "failed"
    except Exception as e:
        summary["zsxq"] = f"error: {str(e)[:100]}"

    # 收集 clippings 数据
    try:
        from adapters.clippings import save_clippings_data
        clippings_ok = save_clippings_data(date, base_dir / "output")
        summary["clippings"] = "ok" if clippings_ok else "failed"
    except Exception as e:
        summary["clippings"] = f"error: {str(e)[:100]}"

    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description="投研alpha：按日期聚合抓取信源")
    ap.add_argument("--date", default=dt.datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d"), help="抓取日期 YYYY-MM-DD")
    ap.add_argument("--sources", default="", help="仅运行指定源，逗号分隔")
    ap.add_argument("--project-dir", default=str(Path(__file__).resolve().parent), help="项目目录")
    args = ap.parse_args()

    summary = run_collect(args.date, Path(args.project_dir), sources=args.sources)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
