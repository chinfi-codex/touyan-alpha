import os
import re
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import requests

from .common import adapter_result, normalize_item

SOURCE = "tavily_news"
TAVILY_URL = "https://api.tavily.com/search"


def _canonical_url(url):
    try:
        u = urlparse((url or "").strip())
        return urlunparse((u.scheme.lower(), u.netloc.lower(), u.path, "", "", ""))
    except Exception:
        return (url or "").strip()


def _normalized_title(title):
    t = (title or "").strip().lower()
    return re.sub(r"\s+", " ", t)


def _safe_date(text, fallback):
    s = (text or "").strip()
    if not s:
        return fallback, ""
    try:
        # Accept ISO-like timestamps from Tavily.
        ts = s.replace("Z", "+00:00")
        d = datetime.fromisoformat(ts).strftime("%Y-%m-%d")
        return d, s
    except Exception:
        return fallback, s


def _fetch_query(api_key, query, max_results=12, timeout=25):
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "topic": "news",
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }
    r = requests.post(TAVILY_URL, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


TECH_TOPICS = [
    {
        "theme": "ai_infra",
        "subcategory": "科技新闻",
        "query": "CPO co-packaged optics NPO LPO transceiver silicon photonics data center liquid cooling CDU cold plate immersion cooling AI cluster NVLink UALink latest news",
        "keywords": ["cpo", "co-packaged optics", "lpo", "silicon photonics", "liquid cooling", "cdu", "cold plate", "nvlink", "ualink", "ai cluster"],
        "strong": ["cpo", "nvlink", "ualink", "silicon photonics"],
    },
    {
        "theme": "memory",
        "subcategory": "科技新闻",
        "query": "HBM3E HBM4 Samsung SK hynix Kioxia NAND DDR5 enterprise SSD CoWoS memory outlook latest news",
        "keywords": ["hbm", "hbm3e", "hbm4", "samsung", "sk hynix", "kioxia", "nand", "ddr5", "enterprise ssd", "cowos"],
        "strong": ["hbm4", "hbm3e", "sk hynix", "cowos"],
    },
    {
        "theme": "china_ai_chips",
        "subcategory": "科技新闻",
        "query": "Cambricon Ascend Chinese AI chip CANN MindSpore AI server cluster interconnect semiconductor policy latest",
        "keywords": ["cambricon", "ascend", "cann", "mindspore", "chinese ai chip", "domestic accelerator", "interconnect"],
        "strong": ["ascend", "cambricon", "mindspore"],
    },
    {
        "theme": "robotics",
        "subcategory": "科技新闻",
        "query": "humanoid robotics embodied AI servo reducer force torque sensor robotaxi warehouse robotics Tesla Optimus Figure Unitree latest",
        "keywords": ["humanoid", "embodied ai", "servo", "force torque sensor", "robotaxi", "warehouse robotics", "optimus", "unitree"],
        "strong": ["optimus", "unitree", "humanoid"],
    },
    {
        "theme": "commercial_space",
        "subcategory": "科技新闻",
        "query": "commercial space launch reusable rocket satellite constellation earth observation space economy Starlink Rocket Lab latest",
        "keywords": ["commercial space", "reusable rocket", "satellite constellation", "earth observation", "starlink", "rocket lab"],
        "strong": ["starlink", "rocket lab", "reusable rocket"],
    },
    {
        "theme": "semi_equipment_packaging",
        "subcategory": "科技新闻",
        "query": "semiconductor equipment lithography etch deposition metrology inspection WFE capex advanced packaging CoWoS SoIC Foveros chiplet ABF latest",
        "keywords": ["lithography", "etch", "deposition", "metrology", "wfe", "advanced packaging", "cowos", "soic", "foveros", "chiplet", "abf"],
        "strong": ["cowos", "foveros", "soic"],
    },
]

MACRO_TOPICS = [
    {
        "theme": "fed_fomc",
        "subcategory": "宏观新闻",
        "query": "Federal Reserve FOMC Fed officials speech latest",
        "keywords": ["federal reserve", "fomc", "fed", "powell", "rate cut", "rate hike"],
        "strong": ["fomc", "federal reserve", "powell"],
    },
    {
        "theme": "rates_dollar_commodities",
        "subcategory": "宏观新闻",
        "query": "US Treasury yield dollar index DXY oil gold copper commodity latest",
        "keywords": ["treasury yield", "dollar index", "dxy", "oil", "gold", "commodity"],
        "strong": ["dxy", "treasury yield"],
    },
    {
        "theme": "us_data",
        "subcategory": "宏观新闻",
        "query": "US CPI payroll unemployment NFP inflation latest release",
        "keywords": ["cpi", "nonfarm payroll", "nfp", "unemployment", "inflation"],
        "strong": ["nfp", "nonfarm payroll", "cpi"],
    },
    {
        "theme": "china_data",
        "subcategory": "宏观新闻",
        "query": "China PPI CPI PMI social financing retail sales latest data",
        "keywords": ["ppi", "cpi", "pmi", "social financing", "retail sales", "社融", "社零"],
        "strong": ["pmi", "社融", "social financing"],
    },
]


def _score(text, keywords, strong):
    t = (text or "").lower()
    score = 0
    for k in keywords:
        if k.lower() in t:
            score += 1
    strong_hit = any(k.lower() in t for k in strong)
    return score, strong_hit


def _iter_topics():
    for t in TECH_TOPICS:
        yield t
    for t in MACRO_TOPICS:
        yield t


def collect(date, slot="", max_results_per_topic=12):
    try:
        api_key = os.getenv("TAVILY_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("缺少环境变量 TAVILY_API_KEY")

        all_candidates = []
        for topic in _iter_topics():
            obj = _fetch_query(api_key=api_key, query=topic["query"], max_results=max_results_per_topic)
            for r in obj.get("results") or []:
                title = (r.get("title") or "").strip()
                content = (r.get("content") or "").strip()
                joined = title + "\n" + content
                score, strong_hit = _score(joined, topic["keywords"], topic["strong"])
                if not strong_hit and score < 2:
                    continue

                published = r.get("published_date") or ""
                d, event_time = _safe_date(published, fallback=date)
                all_candidates.append(
                    {
                        "topic": topic["theme"],
                        "subcategory": topic["subcategory"],
                        "title": title,
                        "summary": content,
                        "url": r.get("url") or "",
                        "event_date": d,
                        "event_time": event_time,
                        "score": score,
                        "raw": r,
                    }
                )

        seen_url = set()
        seen_title = set()
        items = []
        for x in all_candidates:
            cu = _canonical_url(x["url"])
            nt = _normalized_title(x["title"])
            if cu and cu in seen_url:
                continue
            if nt and nt in seen_title:
                continue
            if cu:
                seen_url.add(cu)
            if nt:
                seen_title.add(nt)

            raw = dict(x["raw"]) if isinstance(x["raw"], dict) else {"raw": x["raw"]}
            raw["topic"] = x["topic"]
            raw["score"] = x["score"]
            raw["slot"] = slot or ""

            items.append(
                normalize_item(
                    date=x["event_date"] or date,
                    source=SOURCE,
                    symbol="",
                    company="",
                    title=(x["title"] or "")[:160],
                    summary=(x["summary"] or "")[:300],
                    url=x["url"],
                    raw=raw,
                    category="新闻",
                    subcategory=x["subcategory"],
                    rule_id="tavily.news.topic_filter.v1",
                    excluded=False,
                    exclude_reason="",
                    tags=[x["topic"]],
                    event_time=x["event_time"],
                )
            )

        return adapter_result(date=date, source=SOURCE, items=items)
    except Exception as e:
        return adapter_result(date=date, source=SOURCE, error=str(e))
