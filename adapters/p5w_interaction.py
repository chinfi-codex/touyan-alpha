import datetime as dt
import html
import math
import re

import requests

from .common import adapter_result, normalize_item

SOURCE = "p5w_interaction"
P5W_URL = "https://ir.p5w.net/interaction/getNewSearchR.shtml"
P5W_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}
TAG_RE = re.compile(r"<[^>]+>")


def fetch_page(
    page,
    rows=10,
    key_words="",
    company_code="",
    company_baseinfo_id="",
    timeout=20,
    session=None,
):
    try:
        rows = int(rows)
    except Exception:
        rows = 10
    rows = max(1, min(rows, 10))

    payload = {
        "isPagination": "1",
        "keyWords": key_words or "",
        "companyCode": company_code or "",
        "companyBaseinfoId": company_baseinfo_id or "",
        "page": str(max(0, int(page))),
        "rows": str(rows),
    }

    s = session or requests
    resp = s.post(P5W_URL, data=payload, headers=P5W_HEADERS, timeout=timeout)
    resp.raise_for_status()
    obj = resp.json()
    if not obj.get("success"):
        raise RuntimeError("接口返回失败: %s" % obj)
    return obj


def strip_html(text):
    if text is None:
        return ""
    s = html.unescape(str(text))
    s = TAG_RE.sub("", s)
    return s.strip()


def normalize_rows(rows):
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        event_time = (row.get("replyerTimeStr") or row.get("questionerTimeStr") or "").strip()
        event_date = event_time[:10] if len(event_time) >= 10 else ""
        x = dict(row)
        x["event_time"] = event_time
        x["event_date"] = event_date
        x["clean_content"] = strip_html(row.get("content", ""))
        x["clean_reply_content"] = strip_html(row.get("replyContent", ""))
        out.append(x)
    return out


def filter_time(rows, start, end):
    try:
        start_d = dt.datetime.strptime(start, "%Y-%m-%d").date()
        end_d = dt.datetime.strptime(end, "%Y-%m-%d").date()
    except Exception:
        return []

    out = []
    for row in rows or []:
        event_date = (row.get("event_date") or "").strip()
        try:
            d = dt.datetime.strptime(event_date, "%Y-%m-%d").date()
        except Exception:
            continue
        if start_d <= d <= end_d:
            out.append(row)
    return out


def collect(date, rows_per_page=10, max_pages=30, key_words="", company_code=""):
    try:
        try:
            rows_per_page = int(rows_per_page)
        except Exception:
            rows_per_page = 10
        rows_per_page = max(1, min(rows_per_page, 10))

        try:
            max_pages = int(max_pages)
        except Exception:
            max_pages = 30
        max_pages = max(1, max_pages)

        all_rows = []
        seen_pid = set()

        def append_page_rows(page_rows):
            for r in page_rows or []:
                pid = str(r.get("pid") or "").strip()
                if pid:
                    if pid in seen_pid:
                        continue
                    seen_pid.add(pid)
                all_rows.append(r)

        with requests.Session() as session:
            first = fetch_page(
                page=0,
                rows=rows_per_page,
                key_words=key_words,
                company_code=company_code,
                session=session,
            )
            append_page_rows(first.get("rows"))

            total = int(first.get("total", 0) or 0)
            expected_pages = max(1, int(math.ceil(float(total) / rows_per_page))) if total else 1
            pages_to_fetch = min(max_pages, expected_pages)

            for p in range(1, pages_to_fetch):
                obj = fetch_page(
                    page=p,
                    rows=rows_per_page,
                    key_words=key_words,
                    company_code=company_code,
                    session=session,
                )
                append_page_rows(obj.get("rows"))

        norm = normalize_rows(all_rows)
        if company_code:
            norm = [x for x in norm if str(x.get("companyCode", "")).strip() == str(company_code).strip()]
        filt = filter_time(norm, start=date, end=date)

        items = []
        for x in filt:
            items.append(
                normalize_item(
                    date=x.get("event_date") or date,
                    source=SOURCE,
                    symbol=x.get("companyCode", ""),
                    company=x.get("companyShortname", ""),
                    title=(x.get("clean_content", "") or "")[:80],
                    summary=(x.get("clean_reply_content", "") or "")[:300],
                    url="https://ir.p5w.net/interaction/",
                    raw=x,
                    category="上市公司公开信息",
                    subcategory="互动问答",
                    rule_id="p5w.interaction.fixed.v1",
                    excluded=False,
                    exclude_reason="",
                    tags=["互动问答"],
                    event_time=x.get("event_time") or "",
                )
            )

        return adapter_result(date=date, source=SOURCE, items=items)
    except Exception as e:
        return adapter_result(date=date, source=SOURCE, error=str(e))
