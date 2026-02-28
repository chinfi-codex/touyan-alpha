def normalize_item(date, source, symbol="", company="", title="", summary="", url="", raw=None, **extra):
    item = {
        "date": date,
        "source": source,
        "symbol": symbol or "",
        "company": company or "",
        "title": title or "",
        "summary": summary or "",
        "url": url or "",
        "raw": raw if raw is not None else {},
    }
    if extra:
        item.update(extra)
    return item


def adapter_result(date, source, items=None, error=""):
    items = items or []
    return {
        "date": date,
        "source": source,
        "count": len(items),
        "error": error,
        "items": items,
    }
