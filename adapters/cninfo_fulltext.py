from datetime import datetime, timedelta

from .cninfo_base import fetch_cninfo
from .common import adapter_result, normalize_item
from .cninfo_rules import classify_cninfo_fulltext

SOURCE = "cninfo_fulltext"


def collect(date, include_next_day=False):
    try:
        dates = [date]
        if include_next_day:
            next_day = (datetime.strptime(date, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")
            dates.append(next_day)
        
        rows = []
        for d in dates:
            se_date = "%s~%s" % (d, d)
            rows.extend(fetch_cninfo(se_date=se_date, tab_name="fulltext"))
        items = []
        for r in rows:
            title = r.get("announcementTitle", "")
            cls = classify_cninfo_fulltext(title)
            raw = r.get("raw", r)
            if isinstance(raw, dict):
                raw = dict(raw)
                raw["classification"] = cls
            items.append(
                normalize_item(
                    date=r.get("announcementTime") or date,
                    source=SOURCE,
                    symbol=r.get("secCode", ""),
                    company=r.get("secName", ""),
                    title=title,
                    summary=title,
                    url=r.get("adjunctUrl", ""),
                    raw=raw,
                    category=cls["category"],
                    subcategory=cls["subcategory"],
                    rule_id=cls["rule_id"],
                    excluded=cls["excluded"],
                    exclude_reason=cls["exclude_reason"],
                    tags=cls["tags"],
                    event_time=r.get("announcementTime") or "",
                )
            )
        return adapter_result(date=date, source=SOURCE, items=items)
    except Exception as e:
        return adapter_result(date=date, source=SOURCE, error=str(e))
