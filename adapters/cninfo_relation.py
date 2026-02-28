from .cninfo_base import fetch_cninfo
from .common import adapter_result, normalize_item

SOURCE = "cninfo_relation"


def collect(date):
    try:
        se_date = "%s~%s" % (date, date)
        rows = fetch_cninfo(se_date=se_date, tab_name="relation")
        items = []
        for r in rows:
            title = r.get("announcementTitle", "")
            items.append(
                normalize_item(
                    date=r.get("announcementTime") or date,
                    source=SOURCE,
                    symbol=r.get("secCode", ""),
                    company=r.get("secName", ""),
                    title=title,
                    summary=title,
                    url=r.get("adjunctUrl", ""),
                    raw=r.get("raw", r),
                    category="上市公司公开信息",
                    subcategory="机构调研",
                    rule_id="cninfo.relation.fixed.v1",
                    excluded=False,
                    exclude_reason="",
                    tags=["机构调研"],
                    event_time=r.get("announcementTime") or "",
                )
            )
        return adapter_result(date=date, source=SOURCE, items=items)
    except Exception as e:
        return adapter_result(date=date, source=SOURCE, error=str(e))
