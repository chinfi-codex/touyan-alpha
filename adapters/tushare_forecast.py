import os
from datetime import datetime, timedelta

from .common import adapter_result, normalize_item

SOURCE = "tushare_forecast"


def collect(date, include_next_day=False):
    try:
        token = os.getenv("TUSHARE_TOKEN", "").strip()
        if not token:
            raise RuntimeError("缺少环境变量 TUSHARE_TOKEN")

        import tushare as ts

        pro = ts.pro_api(token)

        query_dates = [date]
        if include_next_day:
            next_day = (datetime.strptime(date, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")
            query_dates.append(next_day)

        rows = []
        for d in query_dates:
            ann_date = d.replace("-", "")
            df = pro.forecast(
                ann_date=ann_date,
                fields="ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,last_parent_net,summary,change_reason",
            )
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                row = {}
                for k, v in r.to_dict().items():
                    row[k] = v.item() if hasattr(v, "item") else v
                rows.append(row)

        if not rows:
            return adapter_result(date=date, source=SOURCE, items=[])

        name_map = {}
        try:
            basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
            if basic is not None and not basic.empty:
                name_map = dict(zip(basic["ts_code"], basic["name"]))
        except Exception:
            pass

        items = []
        seen = set()
        for raw in rows:
            ts_code = str(raw.get("ts_code") or "")
            summary = str(raw.get("summary") or raw.get("change_reason") or "")
            dedup_key = (
                ts_code,
                str(raw.get("ann_date") or ""),
                str(raw.get("end_date") or ""),
                str(raw.get("type") or ""),
                summary,
            )
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            items.append(
                normalize_item(
                    date=date,
                    source=SOURCE,
                    symbol=ts_code,
                    company=name_map.get(ts_code, ""),
                    title="业绩预告 %s" % ts_code,
                    summary=summary,
                    url="https://tushare.pro",
                    raw=raw,
                    category="上市公司公开信息",
                    subcategory="业绩预告",
                    rule_id="tushare.forecast.window.v1",
                    excluded=False,
                    exclude_reason="",
                    tags=["业绩预告"],
                    event_time=str(raw.get("ann_date") or ""),
                )
            )

        return adapter_result(date=date, source=SOURCE, items=items)
    except Exception as e:
        return adapter_result(date=date, source=SOURCE, error=str(e))
