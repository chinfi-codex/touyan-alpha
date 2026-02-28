import datetime as dt
import math

import requests

CNINFO_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    "Origin": "http://www.cninfo.com.cn",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


def fetch_cninfo(se_date, tab_name, timeout=20):
    base = {
        "pageSize": 30,
        "column": "szse",
        "tabName": tab_name,
        "plate": "",
        "stock": "",
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": se_date,
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }

    resp = requests.post(CNINFO_URL, data=dict(base, pageNum=1), headers=CNINFO_HEADERS, timeout=timeout)
    resp.raise_for_status()
    obj = resp.json()

    total = int(obj.get("totalAnnouncement", 0) or 0)
    pages = max(1, int(math.ceil(float(total) / 30)))
    rows = []

    def parse_anns(anns):
        for a in anns or []:
            ts = a.get("announcementTime")
            adate = ""
            if isinstance(ts, (int, float)):
                adate = dt.datetime.fromtimestamp(ts / 1000.0).strftime("%Y-%m-%d")
            rows.append(
                {
                    "announcementTime": adate,
                    "secCode": (a.get("secCode") or "").strip(),
                    "secName": (a.get("secName") or "").strip(),
                    "announcementTitle": (a.get("announcementTitle") or "").strip(),
                    "adjunctUrl": ("http://static.cninfo.com.cn/" + a.get("adjunctUrl", "")) if a.get("adjunctUrl") else "",
                    "raw": a,
                }
            )

    parse_anns(obj.get("announcements"))
    for page in range(2, pages + 1):
        r = requests.post(CNINFO_URL, data=dict(base, pageNum=page), headers=CNINFO_HEADERS, timeout=timeout)
        r.raise_for_status()
        parse_anns((r.json() or {}).get("announcements"))

    seen = set()
    out = []
    for x in rows:
        k = (x["announcementTime"], x["secCode"], x["announcementTitle"], x["adjunctUrl"])
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out
