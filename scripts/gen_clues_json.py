#!/usr/bin/env python3
"""
Generate lightweight JSON clues from daily collected data.

Pipeline:
1) Stage-0 rule prefilter (no token cost)
2) Stage-1 AI prescreen (short context)
3) Stage-2 AI deep analysis (top candidates only, optional deep-read)
4) Stage-3 technical gate (trend-breakout + mean-reversion)

Outputs:
- output/<date>/clues.json
- output/<date>/trade_candidates.json
- output/<date>/token_usage.json
- state/open_clues.json
- state/clue_history.jsonl
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

try:
    import tushare as ts
except Exception:
    ts = None

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None


HIGH_VALUE_SUBCATEGORIES = {
    "重大合作/投资项目": 0.90,
    "增持": 0.74,
    "减持": 0.61,
    "监管函": 0.45,
    "对问询回复": 0.57,
    "资本运作-特定对象发行": 0.78,
    "资本运作-股权激励": 0.76,
    "资本运作-员工持股计划": 0.71,
    "业绩预告": 0.82,
    "快报": 0.80,
}

INTERACTION_KEYWORDS = [
    "订单", "中标", "签约", "合同", "扩产", "产能", "投产", "新品", "涨价", "提价",
    "业绩", "利润", "回购", "分红", "并购", "机器人", "ai", "算力", "出海", "海外",
]

INTERACTION_LOW_SIGNAL_PATTERNS = [
    r"股东人数|股东户数|谢谢关注|请关注公告|已回复",
]

REGULATORY_RISK_PATTERNS = [
    r"监管函|立案|处罚|调查|警示|纪律处分|重大诉讼|问询",
]

DEEP_READ_URL_PATTERNS = [
    re.compile(r"\.pdf$", re.IGNORECASE),
    re.compile(r"cninfo\.com\.cn", re.IGNORECASE),
]

CONCEPT_MANUAL_ALIASES = {
    "AI": "人工智能",
    "AIGC": "人工智能",
    "AIDC": "算力",
}


def cst_today() -> str:
    return (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def clip(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: max(0, n - 3)] + "..."


def to_ts_code(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    if re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", s):
        return s
    if re.fullmatch(r"\d{6}", s):
        if s.startswith(("6", "9")):
            return s + ".SH"
        if s.startswith("8"):
            return s + ".BJ"
        return s + ".SZ"
    return s


def parse_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def extract_json_block(text: str) -> Any:
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    obj_start = s.find("{")
    arr_start = s.find("[")
    starts = [x for x in [obj_start, arr_start] if x >= 0]
    if not starts:
        return None
    st = min(starts)
    end_obj = s.rfind("}")
    end_arr = s.rfind("]")
    ed = max(end_obj, end_arr)
    if ed < st:
        return None
    try:
        return json.loads(s[st : ed + 1])
    except Exception:
        return None


def env_first(*keys: str) -> str:
    for k in keys:
        v = os.getenv(k, "").strip()
        if v:
            return v
    return ""


def load_dotenv_if_present(project_dir: Path) -> None:
    env_path = project_dir / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def estimate_tokens(text: str) -> int:
    return max(1, int(math.ceil(len(text or "") / 3.6)))


class TokenLedger:
    def __init__(self, hard_cap: int):
        self.hard_cap = int(max(1, hard_cap))
        self.stage_caps = self._build_stage_caps(self.hard_cap)
        self.by_stage: Dict[str, Dict[str, Any]] = {
            "stage1": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0, "estimated": False},
            "stage2": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0, "estimated": False},
            "summarize": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0, "estimated": False},
        }
        self.degrade_actions: List[str] = []

    @staticmethod
    def _build_stage_caps(budget: int) -> Dict[str, int]:
        stage1 = min(40000, max(8000, int(budget * 0.40)))
        stage2 = min(55000, max(8000, int(budget * 0.55)))
        min_summary = min(5000, max(1000, int(budget * 0.05)))
        total = stage1 + stage2 + min_summary
        if total > budget:
            scale = float(budget) / float(total)
            stage1 = max(3000, int(stage1 * scale))
            stage2 = max(3000, int(stage2 * scale))
            min_summary = max(500, budget - stage1 - stage2)
        return {"stage1": stage1, "stage2": stage2, "summarize": min_summary}

    def total_used(self) -> int:
        return int(sum(v["total_tokens"] for v in self.by_stage.values()))

    def stage_used(self, stage: str) -> int:
        return int(self.by_stage.get(stage, {}).get("total_tokens", 0))

    def can_spend(self, stage: str, est_total_tokens: int) -> bool:
        est_total_tokens = int(max(1, est_total_tokens))
        if self.total_used() + est_total_tokens > self.hard_cap:
            return False
        cap = self.stage_caps.get(stage, self.hard_cap)
        if self.stage_used(stage) + est_total_tokens > cap:
            return False
        return True

    def record(self, stage: str, prompt_tokens: int, completion_tokens: int, total_tokens: int, estimated: bool) -> None:
        row = self.by_stage[stage]
        row["prompt_tokens"] += int(max(0, prompt_tokens))
        row["completion_tokens"] += int(max(0, completion_tokens))
        row["total_tokens"] += int(max(0, total_tokens))
        row["requests"] += 1
        row["estimated"] = bool(row["estimated"] or estimated)

    def record_estimated(self, stage: str, estimated_total: int) -> None:
        est_prompt = int(max(1, estimated_total * 0.75))
        est_completion = int(max(1, estimated_total - est_prompt))
        self.record(stage, est_prompt, est_completion, estimated_total, estimated=True)

    def summary(self) -> Dict[str, Any]:
        return {
            "hard_cap": self.hard_cap,
            "stage_caps": self.stage_caps,
            "by_stage": self.by_stage,
            "total_tokens": self.total_used(),
            "remaining_tokens": max(0, self.hard_cap - self.total_used()),
            "degrade_actions": self.degrade_actions,
        }


class LLMClient:
    def __init__(self, provider: str):
        self.provider = (provider or "kimi").strip().lower()
        self.base_url, self.api_key, self.stage1_model, self.stage2_model = self._load_config(self.provider)

    @staticmethod
    def _load_config(provider: str) -> Tuple[str, str, str, str]:
        if provider == "kimi":
            base_url = env_first(
                "KIMI_BASE_URL",
                "MOONSHOT_BASE_URL",
                "CLUE_LLM_BASE_URL",
                "OPENAI_BASE_URL",
            ) or "https://api.moonshot.cn/v1"
            api_key = env_first(
                "KIMI_API_KEY",
                "MOONSHOT_API_KEY",
                "CLUE_LLM_API_KEY",
                "OPENAI_API_KEY",
            )
            stage1_model = env_first("KIMI_STAGE1_MODEL", "CLUE_LLM_STAGE1_MODEL", "KIMI_MODEL") or "moonshot-v1-8k"
            stage2_model = env_first("KIMI_STAGE2_MODEL", "CLUE_LLM_STAGE2_MODEL", "KIMI_MODEL") or "moonshot-v1-32k"
            return base_url.rstrip("/"), api_key, stage1_model, stage2_model
        raise ValueError(f"unsupported provider: {provider}")

    def ready(self) -> bool:
        return bool(self.api_key and self.base_url and self.stage1_model and self.stage2_model)

    def validate_auth(self, timeout: int = 20) -> Tuple[bool, str]:
        if not self.ready():
            return False, "missing llm config (base_url/api_key/model)"
        try:
            # Use documented endpoint for auth probe to avoid false negatives on /models availability.
            url = self.base_url + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.stage1_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "temperature": 0,
            }
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
            if resp.status_code == 200:
                return True, "ok(chat_probe)"
            body = ""
            try:
                body = resp.text[:200]
            except Exception:
                body = ""
            return False, f"http {resp.status_code}: {body}"
        except Exception as e:
            return False, str(e)

    def chat(self, stage: str, messages: List[Dict[str, str]], max_tokens: int, temperature: float = 0.0, timeout: int = 60) -> Tuple[str, Dict[str, int], bool]:
        model = self.stage1_model if stage == "stage1" else self.stage2_model
        endpoint = self.base_url + "/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": int(max_tokens),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=timeout)
        resp.raise_for_status()
        obj = resp.json()
        content = ""
        try:
            content = obj["choices"][0]["message"]["content"]
        except Exception:
            content = ""
        usage_obj = obj.get("usage") or {}
        p = int(usage_obj.get("prompt_tokens") or 0)
        c = int(usage_obj.get("completion_tokens") or 0)
        t = int(usage_obj.get("total_tokens") or (p + c))
        estimated = False
        if t <= 0:
            joined = "\n".join((m.get("content") or "") for m in messages)
            p = estimate_tokens(joined)
            c = max(1, int(max_tokens * 0.35))
            t = p + c
            estimated = True
        return content, {"prompt_tokens": p, "completion_tokens": c, "total_tokens": t}, estimated

def load_daily_inputs(out_dir: Path) -> Dict[str, Any]:
    return {
        "cninfo_fulltext": read_json(out_dir / "cninfo_fulltext.json", {"items": []}),
        "cninfo_relation": read_json(out_dir / "cninfo_relation.json", {"items": []}),
        "p5w_interaction": read_json(out_dir / "p5w_interaction.json", {"items": []}),
        "tushare_forecast": read_json(out_dir / "tushare_forecast.json", {"items": []}),
        "tavily_news": read_json(out_dir / "tavily_news.json", {"categories": {}}),
    }


def is_low_signal_interaction(title: str, summary: str) -> bool:
    text = normalize_space((title or "") + " " + (summary or ""))
    return any(re.search(p, text, re.IGNORECASE) for p in INTERACTION_LOW_SIGNAL_PATTERNS)


def interaction_keyword_score(title: str, summary: str) -> float:
    text = normalize_space((title or "") + " " + (summary or "")).lower()
    hits = 0
    for kw in INTERACTION_KEYWORDS:
        if kw.lower() in text:
            hits += 1
    return min(1.0, hits / 3.0)


def infer_direction_from_text(subcategory: str, title: str, summary: str) -> str:
    text = normalize_space(" ".join([subcategory or "", title or "", summary or ""]))
    if re.search(r"减持|监管函|处罚|问询|诉讼|亏损|下滑|风险", text, re.IGNORECASE):
        return "short"
    if re.search(r"增持|中标|签署|订单|增长|扩产|回购|提价|盈利|业绩预增", text, re.IGNORECASE):
        return "long"
    return "neutral"


def parse_forecast_event_score(item: Dict[str, Any]) -> float:
    pmin = parse_float(item.get("change_range_min"))
    pmax = parse_float(item.get("change_range_max"))
    p = None
    if pmin is not None and pmax is not None:
        p = max(abs(pmin), abs(pmax))
    elif pmin is not None:
        p = abs(pmin)
    elif pmax is not None:
        p = abs(pmax)
    if p is None:
        return 0.75
    if p >= 100:
        return 0.96
    if p >= 50:
        return 0.90
    if p >= 30:
        return 0.84
    if p >= 15:
        return 0.78
    return 0.70


def build_stage0_candidates(data: Dict[str, Any], stage0_limit: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    total_input_items = 0

    def push(c: Dict[str, Any]) -> None:
        if not c.get("symbol"):
            return
        candidates.append(c)

    for item in data.get("cninfo_fulltext", {}).get("items", []) or []:
        total_input_items += 1
        if item.get("excluded"):
            continue
        sub = (item.get("subcategory") or "").strip()
        if sub not in HIGH_VALUE_SUBCATEGORIES:
            continue
        title = normalize_space(item.get("title") or "")
        if not title:
            continue
        score = float(HIGH_VALUE_SUBCATEGORIES[sub])
        direction_hint = infer_direction_from_text(sub, title, item.get("summary") or "")
        push(
            {
                "source": "cninfo_fulltext",
                "symbol": (item.get("symbol") or "").strip(),
                "ts_code": to_ts_code(item.get("symbol") or ""),
                "company": (item.get("company") or "").strip(),
                "title": title,
                "summary": normalize_space(item.get("summary") or ""),
                "url": (item.get("url") or "").strip(),
                "subcategory": sub,
                "tags": item.get("tags") or [],
                "event_time": item.get("event_time") or item.get("date") or "",
                "rule_score": score,
                "rule_reason": f"high-value subcategory: {sub}",
                "event_type": sub,
                "direction_hint": direction_hint,
            }
        )

    for item in data.get("cninfo_relation", {}).get("items", []) or []:
        total_input_items += 1
        title = normalize_space(item.get("title") or "")
        if not title:
            continue
        push(
            {
                "source": "cninfo_relation",
                "symbol": (item.get("symbol") or "").strip(),
                "ts_code": to_ts_code(item.get("symbol") or ""),
                "company": (item.get("company") or "").strip(),
                "title": title,
                "summary": normalize_space(item.get("summary") or ""),
                "url": (item.get("url") or "").strip(),
                "subcategory": "机构调研",
                "tags": item.get("tags") or ["机构调研"],
                "event_time": item.get("event_time") or item.get("date") or "",
                "rule_score": 0.66,
                "rule_reason": "relation event",
                "event_type": "机构调研",
                "direction_hint": "neutral",
            }
        )

    for item in data.get("tushare_forecast", {}).get("items", []) or []:
        total_input_items += 1
        title = normalize_space(item.get("title") or "")
        if not title:
            continue
        fscore = parse_forecast_event_score(item)
        push(
            {
                "source": "tushare_forecast",
                "symbol": (item.get("symbol") or "").strip(),
                "ts_code": to_ts_code(item.get("symbol") or ""),
                "company": (item.get("company") or "").strip(),
                "title": title,
                "summary": normalize_space(item.get("summary") or item.get("change_reason") or ""),
                "url": (item.get("url") or "").strip(),
                "subcategory": "业绩预告",
                "tags": item.get("tags") or ["业绩预告"],
                "event_time": item.get("event_time") or item.get("date") or "",
                "rule_score": fscore,
                "rule_reason": "forecast event",
                "event_type": "业绩预告",
                "direction_hint": infer_direction_from_text("业绩预告", title, item.get("summary") or ""),
            }
        )

    for item in data.get("p5w_interaction", {}).get("items", []) or []:
        total_input_items += 1
        title = normalize_space(item.get("title") or "")
        summary = normalize_space(item.get("summary") or "")
        if not title:
            continue
        if is_low_signal_interaction(title, summary):
            continue
        kscore = interaction_keyword_score(title, summary)
        if kscore < 0.34:
            continue
        score = 0.45 + 0.35 * kscore
        push(
            {
                "source": "p5w_interaction",
                "symbol": (item.get("symbol") or "").strip(),
                "ts_code": to_ts_code(item.get("symbol") or ""),
                "company": (item.get("company") or "").strip(),
                "title": title,
                "summary": summary,
                "url": (item.get("url") or "").strip(),
                "subcategory": "互动问答",
                "tags": item.get("tags") or ["互动问答"],
                "event_time": item.get("event_time") or item.get("date") or "",
                "rule_score": score,
                "rule_reason": "interaction keyword signal",
                "event_type": "互动问答",
                "direction_hint": infer_direction_from_text("互动问答", title, summary),
            }
        )

    dedup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for x in candidates:
        key = (x["symbol"], x["source"], clip(x["title"], 72))
        if key not in dedup or x["rule_score"] > dedup[key]["rule_score"]:
            dedup[key] = x
    rows = list(dedup.values())
    rows.sort(key=lambda r: (r.get("rule_score", 0.0), str(r.get("event_time") or ""), str(r.get("title") or "")), reverse=True)
    rows = rows[: max(1, int(stage0_limit))]
    for i, r in enumerate(rows, 1):
        r["candidate_id"] = f"cand-{i:05d}"
        r["short_context"] = clip(f"{r.get('title', '')} | {r.get('summary', '')}", 240)

    macro_context = []
    for bucket, bucket_obj in (data.get("tavily_news", {}).get("categories") or {}).items():
        summary = normalize_space((bucket_obj or {}).get("summary") or "")
        if summary:
            macro_context.append({"bucket": bucket, "summary": summary})

    stats = {
        "total_input_items": total_input_items,
        "stage0_candidates": len(rows),
        "macro_context_count": len(macro_context),
    }
    return rows, {"stats": stats, "macro_context": macro_context}


def build_stage1_prompt(batch: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    lines = []
    for x in batch:
        tags = ",".join((x.get("tags") or [])[:4])
        lines.append(
            f"{x['candidate_id']} | {x.get('symbol')} | {x.get('source')} | {x.get('subcategory')} | "
            f"rule={x.get('rule_score'):.2f} | title={clip(x.get('title',''), 90)} | summary={clip(x.get('summary',''), 140)} | tags={tags}"
        )
    user_content = (
        "请按“高精度低误报”标准，判断哪些候选构成可跟踪交易线索。\n"
        "输出严格JSON对象，格式：\n"
        '{"results":[{"id":"cand-00001","keep":true,"confidence":0.0,"direction":"long|short|neutral","reason":"<=30字","risk_flags":["..."]}]}\n'
        "要求：\n"
        "1) 仅保留信息增量明确的事件；\n"
        "2) 监管/诉讼/减持可标注short或neutral；\n"
        "3) confidence取0-1浮点；\n"
        "4) 不要输出任何JSON以外文本。\n\n"
        "候选列表：\n"
        + "\n".join(lines)
    )
    return [
        {"role": "system", "content": "你是A股事件交易研究员，严格输出JSON。"},
        {"role": "user", "content": user_content},
    ]


def stage1_heuristic(c: Dict[str, Any]) -> Dict[str, Any]:
    conf = 0.45 + 0.5 * float(c.get("rule_score") or 0.0)
    conf = min(0.96, max(0.20, conf))
    keep = conf >= 0.68
    direction = c.get("direction_hint") or "neutral"
    reason = "rule heuristic"
    risk_flags = []
    t = " ".join([c.get("subcategory", ""), c.get("title", ""), c.get("summary", "")])
    for p in REGULATORY_RISK_PATTERNS:
        if re.search(p, t, re.IGNORECASE):
            risk_flags.append("regulatory_risk")
            break
    return {
        "id": c["candidate_id"],
        "keep": keep,
        "confidence": round(conf, 4),
        "direction": direction,
        "reason": reason,
        "risk_flags": risk_flags,
    }


def run_stage1(candidates: List[Dict[str, Any]], llm: LLMClient, ledger: TokenLedger, dry_run: bool, batch_size: int) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    batch_size = max(4, min(20, int(batch_size)))

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        messages = build_stage1_prompt(batch)
        est = estimate_tokens("\n".join(m["content"] for m in messages)) + 700
        if not ledger.can_spend("stage1", est):
            ledger.degrade_actions.append("stage1 budget reached; stop remaining stage1 batches")
            break

        if dry_run or not llm.ready():
            ledger.record_estimated("stage1", est)
            parsed = {"results": [stage1_heuristic(c) for c in batch]}
        else:
            try:
                content, usage, estimated = llm.chat("stage1", messages=messages, max_tokens=700, temperature=0.0, timeout=75)
                ledger.record("stage1", usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"], estimated)
                parsed = extract_json_block(content) or {}
                if not isinstance(parsed, dict):
                    parsed = {}
            except Exception as e:
                ledger.degrade_actions.append(f"stage1 call failed: {str(e)[:80]}")
                parsed = {"results": [stage1_heuristic(c) for c in batch]}

        result_map = {}
        for row in parsed.get("results") or []:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("id") or "").strip()
            if not cid:
                continue
            result_map[cid] = row

        for c in batch:
            r = result_map.get(c["candidate_id"]) or stage1_heuristic(c)
            keep = bool(r.get("keep"))
            conf = parse_float(r.get("confidence"), 0.5) or 0.5
            direction = str(r.get("direction") or c.get("direction_hint") or "neutral").lower().strip()
            if direction not in {"long", "short", "neutral"}:
                direction = c.get("direction_hint") or "neutral"
            reason = clip(normalize_space(str(r.get("reason") or "")), 80) or "stage1"
            risk_flags = r.get("risk_flags") if isinstance(r.get("risk_flags"), list) else []
            c2 = dict(c)
            c2["stage1_keep"] = keep
            c2["stage1_confidence"] = round(min(1.0, max(0.0, conf)), 4)
            c2["stage1_reason"] = reason
            c2["stage1_direction"] = direction
            c2["stage1_risk_flags"] = [str(x) for x in risk_flags][:5]
            if keep and c2["stage1_confidence"] >= 0.58:
                kept.append(c2)

    kept.sort(key=lambda r: (0.58 * float(r.get("rule_score", 0.0)) + 0.42 * float(r.get("stage1_confidence", 0.0)), str(r.get("event_time") or "")), reverse=True)
    return kept

def should_deep_read(url: str) -> bool:
    if not url:
        return False
    return any(p.search(url) for p in DEEP_READ_URL_PATTERNS)


def extract_pdf_excerpt_from_bytes(pdf_bytes: bytes, max_pages: int, max_chars: int) -> str:
    text = ""
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages[:max_pages]:
                    page_text = page.extract_text() or ""
                    if page_text:
                        text += page_text + "\n"
                    if len(text) >= max_chars:
                        break
                if text:
                    return clip(normalize_space(text), max_chars)
        except Exception:
            pass
    if PyPDF2 is not None:
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages[:max_pages]:
                t = page.extract_text() or ""
                if t:
                    text += t + "\n"
                if len(text) >= max_chars:
                    break
            if text:
                return clip(normalize_space(text), max_chars)
        except Exception:
            pass
    return ""


def fetch_source_context(url: str, max_pages: int, max_chars: int) -> Tuple[str, str]:
    if not url:
        return "", "no_url"
    if not should_deep_read(url):
        return "", "skip_non_deep_url"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=25)
        resp.raise_for_status()
        content_type = (resp.headers.get("Content-Type") or "").lower()
        content = resp.content or b""
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            text = extract_pdf_excerpt_from_bytes(content, max_pages=max_pages, max_chars=max_chars)
            if text:
                return text, "pdf_excerpt"
            return "", "pdf_unparsed"
        try:
            txt = resp.text
            txt = clip(normalize_space(txt), max_chars)
            return txt, "html_text"
        except Exception:
            return "", "binary_unparsed"
    except Exception as e:
        return "", f"fetch_failed:{str(e)[:40]}"


def build_stage2_prompt(candidate: Dict[str, Any], context_text: str, macro_context: List[Dict[str, str]]) -> List[Dict[str, str]]:
    macro_lines = [f"- {x.get('bucket')}: {clip(x.get('summary',''), 80)}" for x in macro_context[:3]]
    base = (
        f"symbol={candidate.get('symbol')} company={candidate.get('company')}\n"
        f"source={candidate.get('source')} subcategory={candidate.get('subcategory')}\n"
        f"title={candidate.get('title')}\n"
        f"summary={clip(candidate.get('summary',''), 300)}\n"
        f"url={candidate.get('url')}\n"
        f"stage1_direction={candidate.get('stage1_direction')} stage1_confidence={candidate.get('stage1_confidence')}\n"
    )
    user_content = (
        "你需要将事件候选转为结构化交易线索。\n"
        "输出严格JSON对象，格式：\n"
        '{"thesis":"","direction":"long|short|neutral","confidence":0.0,"event_strength":0.0,"novelty":0.0,"timeliness":0.0,"evidence":[{"source":"", "fact":""}],"risk_flags":[""],"invalidation":"","horizon":"T+1~T+5"}\n'
        "要求：\n"
        "1) thesis不超过80字；2) evidence最多3条且可验证；3) confidence/event_strength/novelty/timeliness均为0-1。\n\n"
        f"候选信息:\n{base}\n"
        f"宏观背景:\n{chr(10).join(macro_lines) if macro_lines else '- 无'}\n\n"
        f"原文片段(可能为空):\n{clip(context_text, 3200)}"
    )
    return [
        {"role": "system", "content": "你是谨慎的A股事件交易分析师，只输出JSON。"},
        {"role": "user", "content": user_content},
    ]


def stage2_heuristic(candidate: Dict[str, Any], context_text: str) -> Dict[str, Any]:
    title = candidate.get("title") or ""
    summary = candidate.get("summary") or ""
    direction = candidate.get("stage1_direction") or candidate.get("direction_hint") or "neutral"
    confidence = min(0.92, max(0.40, 0.45 + 0.45 * float(candidate.get("stage1_confidence") or 0.5)))
    evidence = [{"source": candidate.get("source"), "fact": clip(title or summary, 120)}]
    risk_flags = list(candidate.get("stage1_risk_flags") or [])
    for p in REGULATORY_RISK_PATTERNS:
        if re.search(p, (title + " " + summary), re.IGNORECASE):
            risk_flags.append("regulatory_risk")
            break
    return {
        "thesis": clip(summary or title, 80),
        "direction": direction,
        "confidence": round(confidence, 4),
        "event_strength": round(min(1.0, max(0.1, float(candidate.get("rule_score") or 0.5))), 4),
        "novelty": 0.55,
        "timeliness": 0.82,
        "evidence": evidence[:3],
        "risk_flags": sorted(set(risk_flags))[:6],
        "invalidation": "若后续公告或价格行为与事件逻辑背离",
        "horizon": "T+1~T+5",
        "source_context_type": "heuristic",
        "source_context_chars": len(context_text or ""),
    }


def run_stage2(stage1_kept: List[Dict[str, Any]], total_input_items: int, llm: LLMClient, ledger: TokenLedger, dry_run: bool, macro_context: List[Dict[str, str]], ratio: float, stage2_max: int, deep_read_max_pages: int, deep_read_max_chars: int, stage2_workers: int) -> List[Dict[str, Any]]:
    if not stage1_kept:
        return []

    ratio = min(0.08, max(0.03, float(ratio)))
    target = int(total_input_items * ratio)
    target = max(8, target)
    target = min(int(max(1, stage2_max)), target)
    selected = stage1_kept[:target]

    contexts: Dict[str, Tuple[str, str]] = {}
    if dry_run:
        for c in selected:
            contexts[c["candidate_id"]] = ("", "dry_run")
    else:
        workers = max(1, min(8, int(stage2_workers)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            future_map = {
                ex.submit(fetch_source_context, c.get("url") or "", deep_read_max_pages, deep_read_max_chars): c["candidate_id"]
                for c in selected
            }
            for fut in concurrent.futures.as_completed(future_map):
                cid = future_map[fut]
                try:
                    contexts[cid] = fut.result()
                except Exception as e:
                    contexts[cid] = ("", f"context_failed:{str(e)[:30]}")

    out: List[Dict[str, Any]] = []
    for c in selected:
        context_text, context_type = contexts.get(c["candidate_id"], ("", "missing"))
        messages = build_stage2_prompt(c, context_text=context_text, macro_context=macro_context)
        est = estimate_tokens("\n".join(m["content"] for m in messages)) + 650
        if not ledger.can_spend("stage2", est):
            ledger.degrade_actions.append("stage2 budget reached; stop remaining stage2 candidates")
            break

        if dry_run or not llm.ready():
            ledger.record_estimated("stage2", est)
            parsed = stage2_heuristic(c, context_text)
        else:
            try:
                content, usage, estimated = llm.chat("stage2", messages=messages, max_tokens=650, temperature=0.0, timeout=90)
                ledger.record("stage2", usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"], estimated)
                obj = extract_json_block(content)
                if not isinstance(obj, dict):
                    obj = stage2_heuristic(c, context_text)
                parsed = obj
            except Exception as e:
                ledger.degrade_actions.append(f"stage2 call failed: {str(e)[:80]}")
                parsed = stage2_heuristic(c, context_text)

        confidence = parse_float(parsed.get("confidence"), c.get("stage1_confidence", 0.5)) or 0.5
        event_strength = parse_float(parsed.get("event_strength"), c.get("rule_score", 0.5)) or 0.5
        novelty = parse_float(parsed.get("novelty"), 0.5) or 0.5
        timeliness = parse_float(parsed.get("timeliness"), 0.8) or 0.8
        direction = str(parsed.get("direction") or c.get("stage1_direction") or c.get("direction_hint") or "neutral").lower().strip()
        if direction not in {"long", "short", "neutral"}:
            direction = "neutral"
        evidence = parsed.get("evidence") if isinstance(parsed.get("evidence"), list) else []
        evidence_clean = []
        for e in evidence[:3]:
            if isinstance(e, dict):
                evidence_clean.append({"source": str(e.get("source") or ""), "fact": clip(str(e.get("fact") or ""), 140)})
        if not evidence_clean:
            evidence_clean = [{"source": c.get("source"), "fact": clip(c.get("title") or c.get("summary") or "", 120)}]
        risk_flags = parsed.get("risk_flags") if isinstance(parsed.get("risk_flags"), list) else []
        risk_flags = [clip(str(x), 30) for x in risk_flags][:8]

        row = dict(c)
        row.update(
            {
                "stage2_thesis": clip(normalize_space(str(parsed.get("thesis") or "")), 120),
                "stage2_direction": direction,
                "stage2_confidence": round(min(1.0, max(0.0, confidence)), 4),
                "stage2_event_strength": round(min(1.0, max(0.0, event_strength)), 4),
                "stage2_novelty": round(min(1.0, max(0.0, novelty)), 4),
                "stage2_timeliness": round(min(1.0, max(0.0, timeliness)), 4),
                "stage2_evidence": evidence_clean,
                "stage2_risk_flags": risk_flags,
                "stage2_invalidation": clip(normalize_space(str(parsed.get("invalidation") or "")), 120),
                "stage2_horizon": clip(str(parsed.get("horizon") or "T+1~T+5"), 24),
                "source_context_type": context_type,
                "source_context_chars": len(context_text or ""),
            }
        )
        out.append(row)
    return out


def aggregate_symbol_source_count(candidates: List[Dict[str, Any]]) -> Dict[str, int]:
    m: Dict[str, set] = {}
    for c in candidates:
        symbol = c.get("symbol") or ""
        src = c.get("source") or ""
        if not symbol:
            continue
        m.setdefault(symbol, set()).add(src)
    return {k: len(v) for k, v in m.items()}


def build_clues(
    date: str,
    stage2_rows: List[Dict[str, Any]],
    stage0_candidates: List[Dict[str, Any]],
    confidence_threshold: float = 0.62,
    max_clues: int = 30,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    source_count = aggregate_symbol_source_count(stage0_candidates)
    all_scored = []
    for r in stage2_rows:
        symbol = r.get("symbol") or ""
        company = r.get("company") or ""
        cross_sources = int(source_count.get(symbol, 1))
        cross_source_score = min(1.0, 0.32 + 0.28 * (cross_sources - 1))
        cross_source_score = max(0.0, min(1.0, cross_source_score))
        risk_flags = sorted(set((r.get("stage1_risk_flags") or []) + (r.get("stage2_risk_flags") or [])))
        risk_penalty = min(0.35, 0.08 * len(risk_flags))
        liquidity_prior = 0.55
        confidence = (
            0.35 * float(r.get("stage2_event_strength") or r.get("rule_score") or 0.5)
            + 0.25 * cross_source_score
            + 0.20 * float(r.get("stage2_novelty") or 0.5)
            + 0.10 * float(r.get("stage2_timeliness") or 0.8)
            + 0.10 * liquidity_prior
            - risk_penalty
        )
        confidence = min(1.0, max(0.0, confidence))
        cid_seed = f"{date}|{symbol}|{r.get('source')}|{r.get('title')}"
        clue_id = "clue-" + hashlib.sha1(cid_seed.encode("utf-8")).hexdigest()[:16]
        clue = {
            "clue_id": clue_id,
            "date": date,
            "symbol": symbol,
            "ts_code": to_ts_code(symbol),
            "company": company,
            "direction": r.get("stage2_direction") or r.get("stage1_direction") or "neutral",
            "thesis": clip(r.get("stage2_thesis") or r.get("title") or "", 120),
            "evidence": r.get("stage2_evidence") or [],
            "risk_flags": risk_flags,
            "invalidation": r.get("stage2_invalidation") or "若后续事实与事件逻辑冲突",
            "horizon": r.get("stage2_horizon") or "T+1~T+5",
            "confidence": round(confidence, 4),
            "source_context_type": r.get("source_context_type"),
            "source_context_chars": r.get("source_context_chars"),
            "source": r.get("source"),
            "subcategory": r.get("subcategory"),
            "url": r.get("url"),
            "event_time": r.get("event_time"),
            "review_required": True,
            "review_status": "pending_review",
            "status": "new",
            "score_components": {
                "event_strength": round(float(r.get("stage2_event_strength") or r.get("rule_score") or 0.5), 4),
                "cross_source": round(cross_source_score, 4),
                "novelty": round(float(r.get("stage2_novelty") or 0.5), 4),
                "timeliness": round(float(r.get("stage2_timeliness") or 0.8), 4),
                "liquidity_prior": liquidity_prior,
                "risk_penalty": round(risk_penalty, 4),
            },
        }
        all_scored.append(clue)

    all_scored.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
    selected = [c for c in all_scored if float(c.get("confidence", 0.0)) >= float(confidence_threshold)][: int(max_clues)]

    rejected = [c for c in all_scored if float(c.get("confidence", 0.0)) < float(confidence_threshold)]
    conf_values = [float(c.get("confidence") or 0.0) for c in all_scored]
    avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0
    debug = {
        "threshold": float(confidence_threshold),
        "max_clues": int(max_clues),
        "input_stage2_count": len(stage2_rows),
        "all_scored_count": len(all_scored),
        "selected_count": len(selected),
        "rejected_count": len(rejected),
        "confidence_stats": {
            "min": round(min(conf_values), 4) if conf_values else 0.0,
            "max": round(max(conf_values), 4) if conf_values else 0.0,
            "avg": round(avg_conf, 4),
        },
        "top_scored_preview": [
            {
                "symbol": c.get("symbol"),
                "company": c.get("company"),
                "confidence": c.get("confidence"),
                "event_strength": (c.get("score_components") or {}).get("event_strength"),
                "cross_source": (c.get("score_components") or {}).get("cross_source"),
                "novelty": (c.get("score_components") or {}).get("novelty"),
                "timeliness": (c.get("score_components") or {}).get("timeliness"),
                "risk_penalty": (c.get("score_components") or {}).get("risk_penalty"),
                "risk_flags": c.get("risk_flags") or [],
                "thesis": c.get("thesis"),
            }
            for c in all_scored[:20]
        ],
        "rejected_preview": [
            {
                "symbol": c.get("symbol"),
                "company": c.get("company"),
                "confidence": c.get("confidence"),
                "gap_to_threshold": round(float(confidence_threshold) - float(c.get("confidence") or 0.0), 4),
                "event_strength": (c.get("score_components") or {}).get("event_strength"),
                "cross_source": (c.get("score_components") or {}).get("cross_source"),
                "novelty": (c.get("score_components") or {}).get("novelty"),
                "timeliness": (c.get("score_components") or {}).get("timeliness"),
                "risk_penalty": (c.get("score_components") or {}).get("risk_penalty"),
                "risk_flags": c.get("risk_flags") or [],
                "thesis": c.get("thesis"),
            }
            for c in rejected[:20]
        ],
    }
    return selected, debug


def _normalize_symbol_for_concept(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", s):
        return s.split(".")[0]
    if re.fullmatch(r"\d{6}", s):
        return s
    return ""


def load_akshare_concept_names(project_dir: Path) -> Tuple[List[str], bool, str]:
    """Load concept names via AkShare Eastmoney methods. Hard fail if unavailable."""
    try:
        import akshare as ak
    except Exception as e:
        raise RuntimeError(f"akshare import failed: {e}")

    # primary: Eastmoney concept name API
    try:
        df = ak.stock_board_concept_name_em()
        names = []
        if df is not None and not df.empty:
            for col in ["板块名称", "name", "板块"]:
                if col in df.columns:
                    names = [str(x).strip() for x in df[col].tolist() if str(x).strip()]
                    break
        names = sorted(set(names))
        if names:
            return names, False, "stock_board_concept_name_em"
    except Exception:
        pass

    # fallback: Eastmoney async concept name API
    try:
        df2 = ak.stock_board_concept_name_em_async()
        names2 = []
        if df2 is not None and not df2.empty:
            for col in ["板块名称", "name", "板块"]:
                if col in df2.columns:
                    names2 = [str(x).strip() for x in df2[col].tolist() if str(x).strip()]
                    break
        names2 = sorted(set(names2))
        if names2:
            return names2, False, "stock_board_concept_name_em_async"
    except Exception:
        pass

    raise RuntimeError(
        "AkShare concept library unavailable: both stock_board_concept_name_em and "
        "stock_board_concept_name_em_async failed"
    )


def map_clue_to_concepts(clue: Dict[str, Any], concept_names: List[str]) -> List[str]:
    text_parts = [
        str(clue.get("thesis") or ""),
        str(clue.get("subcategory") or ""),
        str(clue.get("company") or ""),
        str(clue.get("source") or ""),
    ]
    for e in clue.get("evidence") or []:
        if isinstance(e, dict):
            text_parts.append(str(e.get("fact") or ""))
    text = normalize_space(" ".join(text_parts))
    text_lower = text.lower()

    for src, dst in CONCEPT_MANUAL_ALIASES.items():
        if src.lower() in text_lower:
            text += " " + dst

    concepts = []
    if concept_names:
        for name in concept_names:
            if not name:
                continue
            if name in text:
                concepts.append(name)
            if len(concepts) >= 3:
                break
    return sorted(set(concepts))[:3]


def build_concept_clues(
    clues: List[Dict[str, Any]], project_dir: Path
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
    concept_names, fallback, source = load_akshare_concept_names(project_dir)
    concept_groups: Dict[str, Dict[str, Any]] = {}
    mapped_count = 0

    for clue in clues:
        concepts = map_clue_to_concepts(clue, concept_names)
        clue["linked_concepts"] = concepts
        if concepts:
            mapped_count += 1
        for concept in concepts:
            g = concept_groups.setdefault(
                concept,
                {
                    "concept_name": concept,
                    "linked_symbols": set(),
                    "risk_flags": set(),
                    "event_strength_sum": 0.0,
                    "cross_source_sum": 0.0,
                    "confidence_sum": 0.0,
                    "evidence_count": 0,
                    "count": 0,
                    "latest_event_time": "",
                    "top_thesis": "",
                    "top_confidence": -1.0,
                },
            )
            symbol = _normalize_symbol_for_concept(clue.get("symbol") or "")
            if symbol:
                g["linked_symbols"].add(symbol)
            for rf in clue.get("risk_flags") or []:
                g["risk_flags"].add(str(rf))
            sc = clue.get("score_components") or {}
            evs = float(sc.get("event_strength") or 0.5)
            css = float(sc.get("cross_source") or 0.3)
            conf = float(clue.get("confidence") or 0.5)
            g["event_strength_sum"] += evs
            g["cross_source_sum"] += css
            g["confidence_sum"] += conf
            g["evidence_count"] += len(clue.get("evidence") or [])
            g["count"] += 1
            et = str(clue.get("event_time") or "")
            if et > g["latest_event_time"]:
                g["latest_event_time"] = et
            if conf > g["top_confidence"]:
                g["top_confidence"] = conf
                g["top_thesis"] = str(clue.get("thesis") or "")

    concept_clues = []
    for _, g in concept_groups.items():
        cnt = max(1, int(g["count"]))
        event_strength = g["event_strength_sum"] / cnt
        cross_source = g["cross_source_sum"] / cnt
        confidence = g["confidence_sum"] / cnt
        risk_flags = sorted(g["risk_flags"])
        risk_penalty = min(0.30, 0.06 * len(risk_flags))
        score = 0.6 * event_strength + 0.4 * cross_source - risk_penalty
        concept_clues.append(
            {
                "concept_name": g["concept_name"],
                "score": round(max(0.0, min(1.0, score)), 4),
                "event_strength": round(event_strength, 4),
                "cross_source_score": round(cross_source, 4),
                "confidence": round(confidence, 4),
                "evidence_count": int(g["evidence_count"]),
                "linked_symbols": sorted(g["linked_symbols"]),
                "risk_flags": risk_flags[:8],
                "latest_event_time": g["latest_event_time"],
                "thesis": clip(g["top_thesis"], 120),
            }
        )
    concept_clues.sort(
        key=lambda x: (float(x.get("score") or 0.0), int(len(x.get("linked_symbols") or []))),
        reverse=True,
    )
    concept_clues = [x for x in concept_clues if float(x.get("score") or 0.0) >= 0.35][:20]
    stats = {
        "concept_source": source,
        "concept_library_size": len(concept_names),
        "mapped_clue_count": mapped_count,
        "alias_match_enabled": True,
        "concept_clue_count": len(concept_clues),
    }
    return concept_clues, stats, fallback

def sma(values: List[float], n: int) -> Optional[float]:
    if len(values) < n:
        return None
    return sum(values[-n:]) / float(n)


def ema_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def calc_rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(0.0, d))
        losses.append(max(0.0, -d))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calc_macd_hist(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if len(values) < 35:
        return None, None
    ema12 = ema_series(values, 12)
    ema26 = ema_series(values, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = ema_series(dif, 9)
    hist = [2.0 * (d - e) for d, e in zip(dif, dea)]
    if len(hist) < 2:
        return None, None
    return hist[-1], hist[-2]


class TushareMarket:
    def __init__(self, token: str):
        self.token = (token or "").strip()
        self.ready = bool(self.token and ts is not None)
        self.pro = ts.pro_api(self.token) if self.ready else None
        self.cache: Dict[str, Dict[str, Any]] = {}

    def get_indicators(self, ts_code: str, trade_date: str) -> Dict[str, Any]:
        if ts_code in self.cache:
            return self.cache[ts_code]
        if not self.ready or not ts_code:
            row = {"available": False, "reason": "tushare_not_ready"}
            self.cache[ts_code] = row
            return row
        end_date = dt.datetime.strptime(trade_date, "%Y-%m-%d").strftime("%Y%m%d")
        start_date = (dt.datetime.strptime(trade_date, "%Y-%m-%d") - dt.timedelta(days=220)).strftime("%Y%m%d")
        try:
            df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date, fields="ts_code,trade_date,open,high,low,close,vol,pct_chg")
        except Exception as e:
            row = {"available": False, "reason": f"daily_failed:{str(e)[:40]}"}
            self.cache[ts_code] = row
            return row
        if df is None or df.empty:
            row = {"available": False, "reason": "no_price_data"}
            self.cache[ts_code] = row
            return row
        try:
            recs = list(df.to_dict("records"))
        except Exception:
            recs = []
        if not recs:
            row = {"available": False, "reason": "empty_records"}
            self.cache[ts_code] = row
            return row
        recs.sort(key=lambda x: str(x.get("trade_date") or ""))
        closes = [parse_float(x.get("close"), 0.0) or 0.0 for x in recs]
        vols = [parse_float(x.get("vol"), 0.0) or 0.0 for x in recs]
        pct = parse_float(recs[-1].get("pct_chg"), 0.0) or 0.0
        ma20 = sma(closes, 20)
        ma60 = sma(closes, 60)
        prev_high20 = max(closes[-21:-1]) if len(closes) >= 21 else None
        vol_ratio = None
        if len(vols) >= 21:
            base_vol = sum(vols[-21:-1]) / 20.0
            if base_vol > 0:
                vol_ratio = vols[-1] / base_vol
        rsi14 = calc_rsi(closes, 14)
        macd_hist, macd_hist_prev = calc_macd_hist(closes)
        avg_vol20 = (sum(vols[-20:]) / 20.0) if len(vols) >= 20 else None

        row = {
            "available": True,
            "last_close": closes[-1],
            "ma20": ma20,
            "ma60": ma60,
            "prev_high20": prev_high20,
            "breakout20": bool(prev_high20 is not None and closes[-1] >= prev_high20),
            "vol_ratio": vol_ratio,
            "rsi14": rsi14,
            "macd_hist": macd_hist,
            "macd_hist_prev": macd_hist_prev,
            "pct_chg": pct,
            "avg_vol20": avg_vol20,
        }
        self.cache[ts_code] = row
        return row


def calc_technical_score(ind: Dict[str, Any]) -> Dict[str, Any]:
    if not ind.get("available"):
        return {"available": False, "mode": "unknown", "technical_score": 0.50, "checks": {}, "reason": ind.get("reason", "unavailable")}
    close = parse_float(ind.get("last_close"), 0.0) or 0.0
    ma20 = parse_float(ind.get("ma20"), None)
    ma60 = parse_float(ind.get("ma60"), None)
    vol_ratio = parse_float(ind.get("vol_ratio"), None)
    rsi14 = parse_float(ind.get("rsi14"), None)
    breakout20 = bool(ind.get("breakout20"))
    macd_hist = parse_float(ind.get("macd_hist"), None)
    macd_hist_prev = parse_float(ind.get("macd_hist_prev"), None)

    ma_align = bool(ma20 is not None and ma60 is not None and close > ma20 > ma60)
    trend_score = 0.35 + (0.20 if ma_align else 0.0) + (0.18 if breakout20 else 0.0) + (0.16 if (vol_ratio is not None and vol_ratio >= 1.5) else 0.0) + (0.11 if (rsi14 is not None and 45 <= rsi14 <= 78) else 0.0)
    trend_score = min(1.0, trend_score)

    mr_setup = bool(rsi14 is not None and rsi14 <= 35)
    macd_recover = bool(macd_hist is not None and macd_hist_prev is not None and macd_hist > macd_hist_prev)
    near_ma20 = bool(ma20 is not None and close >= ma20 * 0.95)
    mr_score = 0.30 + (0.24 if mr_setup else 0.0) + (0.20 if macd_recover else 0.0) + (0.14 if near_ma20 else 0.0) + (0.12 if (vol_ratio is not None and vol_ratio >= 1.2) else 0.0)
    mr_score = min(1.0, mr_score)

    mode = "trend_breakout" if trend_score >= mr_score else "mean_reversion"
    score = trend_score if mode == "trend_breakout" else mr_score
    checks = {
        "ma_align": ma_align,
        "breakout20": breakout20,
        "vol_ratio": vol_ratio,
        "rsi14": rsi14,
        "macd_hist": macd_hist,
        "macd_hist_prev": macd_hist_prev,
        "mean_reversion_setup": mr_setup and macd_recover,
    }
    return {"available": True, "mode": mode, "technical_score": round(float(score), 4), "checks": checks}


def has_regulatory_hard_risk(risk_flags: List[str], thesis: str) -> bool:
    text = " ".join((risk_flags or []) + [thesis or ""])
    return any(re.search(p, text, re.IGNORECASE) for p in REGULATORY_RISK_PATTERNS)


def build_trade_candidates(clues: List[Dict[str, Any]], trade_date: str, market: TushareMarket) -> List[Dict[str, Any]]:
    rows = []
    for c in clues:
        ts_code = c.get("ts_code") or to_ts_code(c.get("symbol") or "")
        ind = market.get_indicators(ts_code, trade_date)
        tech = calc_technical_score(ind)
        hard_risk = False
        hard_reasons = []

        company = str(c.get("company") or "")
        if "ST" in company.upper():
            hard_risk = True
            hard_reasons.append("st_company")
        if has_regulatory_hard_risk(c.get("risk_flags") or [], c.get("thesis") or ""):
            hard_risk = True
            hard_reasons.append("regulatory_high_risk")
        if ind.get("available") and parse_float(ind.get("avg_vol20"), 0.0) is not None:
            avg_vol20 = parse_float(ind.get("avg_vol20"), 0.0) or 0.0
            if avg_vol20 < 3000:
                hard_risk = True
                hard_reasons.append("low_liquidity")
        if ind.get("available") and abs(parse_float(ind.get("pct_chg"), 0.0) or 0.0) > 9.8:
            hard_risk = True
            hard_reasons.append("abnormal_volatility")

        clue_conf = float(c.get("confidence") or 0.0)
        info_score = round(clue_conf, 4)
        trade_score = info_score

        if hard_risk:
            recommendation = "reject"
        elif trade_score >= 0.78:
            recommendation = "buy_watch"
        elif trade_score >= 0.65:
            recommendation = "observe"
        else:
            recommendation = "reject"

        row = dict(c)
        row["technical"] = tech
        row["info_score"] = info_score
        row["market_snapshot"] = ind
        row["hard_risk"] = hard_risk
        row["hard_risk_reasons"] = hard_reasons
        row["trade_score"] = trade_score
        row["recommendation"] = recommendation
        rows.append(row)
    rows.sort(key=lambda x: (x.get("recommendation") == "buy_watch", x.get("trade_score", 0.0)), reverse=True)
    return rows


def sync_open_state(state_path: Path, trade_rows: List[Dict[str, Any]], run_meta: Dict[str, Any]) -> Dict[str, Any]:
    state = read_json(state_path, {"updated_at": "", "items": []})
    items = state.get("items") if isinstance(state.get("items"), list) else []
    by_id = {str(x.get("clue_id")): x for x in items if isinstance(x, dict) and x.get("clue_id")}
    for row in trade_rows:
        cid = row.get("clue_id")
        if not cid:
            continue
        existing = by_id.get(cid, {})
        merged = dict(row)
        for k in ["review_status", "review_note", "reviewed_at", "manual_action", "manual_score"]:
            if k in existing:
                merged[k] = existing[k]
        if "review_status" not in merged:
            merged["review_status"] = "pending_review"
        merged["tracking_status"] = existing.get("tracking_status", "open")
        merged["last_seen_at"] = run_meta["generated_at"]
        merged["run_date"] = run_meta["date"]
        by_id[cid] = merged
    merged_items = list(by_id.values())
    merged_items.sort(key=lambda x: (str(x.get("run_date") or ""), float(x.get("trade_score") or 0.0)), reverse=True)
    out = {"updated_at": run_meta["generated_at"], "run_date": run_meta["date"], "items": merged_items}
    write_json(state_path, out)
    return out


def estimate_runtime_seconds(stage0_count: int, stage1_count: int, stage2_count: int, has_market: bool) -> Dict[str, Any]:
    stage0_s = max(3, min(10, int(stage0_count / 80) + 3))
    stage1_s = max(20, min(60, int(stage1_count / 3) + 18))
    stage2_s = max(40, min(120, int(stage2_count * 1.8) + 30))
    tech_s = 0 if not has_market else max(10, min(40, int(stage2_count * 0.8) + 8))
    total_s = stage0_s + stage1_s + stage2_s + tech_s
    return {
        "stage0_sec_est": stage0_s,
        "stage1_sec_est": stage1_s,
        "stage2_sec_est": stage2_s,
        "technical_sec_est": tech_s,
        "total_sec_est": total_s,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate lightweight JSON clues with token budget control")
    ap.add_argument("--date", default="", help="YYYY-MM-DD, default today in Asia/Shanghai")
    ap.add_argument("--provider", default="kimi", help="LLM provider, default kimi")
    ap.add_argument("--token-budget", type=int, default=100000, help="daily token hard cap")
    ap.add_argument("--project-dir", default=str(Path(__file__).resolve().parents[1]), help="project root path")
    ap.add_argument("--dry-run", action="store_true", help="estimate-only mode, no LLM remote calls")
    ap.add_argument("--stage0-limit", type=int, default=220, help="max stage0 candidates")
    ap.add_argument("--stage1-batch-size", type=int, default=12, help="stage1 batch size")
    ap.add_argument("--stage2-ratio", type=float, default=0.05, help="stage2 candidate ratio in [0.03,0.08]")
    ap.add_argument("--stage2-max", type=int, default=80, help="stage2 max candidate count")
    ap.add_argument("--stage2-workers", type=int, default=6, help="context deep-read parallel workers")
    ap.add_argument("--deep-read-max-pages", type=int, default=2, help="pdf pages for deep-read")
    ap.add_argument("--deep-read-max-chars", type=int, default=3500, help="max chars from source context")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    load_dotenv_if_present(project_dir)
    date = args.date or cst_today()
    out_dir = project_dir / "output" / date
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    stage_timers: Dict[str, float] = {}

    data = load_daily_inputs(out_dir)
    llm = LLMClient(args.provider)
    ledger = TokenLedger(args.token_budget)
    if not args.dry_run:
        ok, detail = llm.validate_auth()
        if not ok:
            raise SystemExit(
                "Kimi authentication failed. "
                "Please set a valid key in one of: "
                "KIMI_API_KEY / MOONSHOT_API_KEY / CLUE_LLM_API_KEY / OPENAI_API_KEY. "
                f"detail={detail}"
            )

    t0 = time.perf_counter()
    stage0_rows, stage0_meta = build_stage0_candidates(data, stage0_limit=args.stage0_limit)
    stage_timers["stage0"] = time.perf_counter() - t0

    t1 = time.perf_counter()
    stage1_kept = run_stage1(stage0_rows, llm=llm, ledger=ledger, dry_run=bool(args.dry_run), batch_size=args.stage1_batch_size)
    stage_timers["stage1"] = time.perf_counter() - t1

    t2 = time.perf_counter()
    stage2_rows = run_stage2(
        stage1_kept=stage1_kept,
        total_input_items=stage0_meta["stats"]["total_input_items"],
        llm=llm,
        ledger=ledger,
        dry_run=bool(args.dry_run),
        macro_context=stage0_meta["macro_context"],
        ratio=args.stage2_ratio,
        stage2_max=args.stage2_max,
        deep_read_max_pages=args.deep_read_max_pages,
        deep_read_max_chars=args.deep_read_max_chars,
        stage2_workers=args.stage2_workers,
    )
    stage_timers["stage2"] = time.perf_counter() - t2

    clues, clue_debug = build_clues(
        date=date,
        stage2_rows=stage2_rows,
        stage0_candidates=stage0_rows,
        confidence_threshold=0.62,
        max_clues=30,
    )
    concept_clues = []
    concept_stats = {
        "concept_source": "unavailable",
        "concept_library_size": 0,
        "mapped_clue_count": 0,
        "alias_match_enabled": True,
        "concept_clue_count": 0,
    }
    concept_fallback = True
    concept_warning = ""
    try:
        concept_clues, concept_stats, concept_fallback = build_concept_clues(
            clues=clues, project_dir=project_dir
        )
    except Exception as e:
        concept_warning = f"概念线索已跳过：{str(e)}"
        for clue in clues:
            clue["linked_concepts"] = []

    t3 = time.perf_counter()
    tushare_token = env_first("TUSHARE_TOKEN")
    market = TushareMarket(tushare_token)
    trade_rows = build_trade_candidates(clues=clues, trade_date=date, market=market)
    stage_timers["stage3_technical"] = time.perf_counter() - t3

    run_meta = {"date": date, "generated_at": now_iso(), "provider": args.provider, "dry_run": bool(args.dry_run)}

    clues_doc = {
        "meta": {
            **run_meta,
            "hard_cap_tokens": args.token_budget,
            "stage0": stage0_meta["stats"],
            "stage1_kept": len(stage1_kept),
            "stage2_analyzed": len(stage2_rows),
                "final_clues": len(clues),
                "concept_mapping_fallback": concept_fallback,
                "concept_mapping_stats": concept_stats,
                "concept_mapping_warning": concept_warning,
            },
        "macro_context": stage0_meta["macro_context"],
        "concept_clues": concept_clues,
        "items": clues,
    }
    write_json(out_dir / "clues.json", clues_doc)
    write_json(
        out_dir / "clue_debug.json",
        {
            "meta": {
                **run_meta,
                "stage0_candidates": stage0_meta["stats"]["stage0_candidates"],
                "stage1_kept": len(stage1_kept),
                "stage2_analyzed": len(stage2_rows),
            },
            "clue_debug": clue_debug,
        },
    )

    trade_doc = {"meta": {**run_meta, "final_trade_candidates": len(trade_rows)}, "items": trade_rows}
    write_json(out_dir / "trade_candidates.json", trade_doc)

    runtime_est = estimate_runtime_seconds(
        stage0_count=stage0_meta["stats"]["stage0_candidates"],
        stage1_count=len(stage1_kept),
        stage2_count=len(stage2_rows),
        has_market=market.ready,
    )
    token_doc = {
        "meta": run_meta,
        **ledger.summary(),
        "timing_seconds_actual": {k: round(v, 3) for k, v in stage_timers.items()},
        "timing_seconds_estimated": runtime_est,
    }
    write_json(out_dir / "token_usage.json", token_doc)

    state_dir = project_dir / "state"
    open_state = sync_open_state(state_dir / "open_clues.json", trade_rows, run_meta=run_meta)

    history_rows = []
    for row in trade_rows:
        history_rows.append(
            {
                "ts": run_meta["generated_at"],
                "date": date,
                "event": "generated",
                "clue_id": row.get("clue_id"),
                "symbol": row.get("symbol"),
                "direction": row.get("direction"),
                "confidence": row.get("confidence"),
                "trade_score": row.get("trade_score"),
                "recommendation": row.get("recommendation"),
                "review_status": row.get("review_status", "pending_review"),
            }
        )
    append_jsonl(state_dir / "clue_history.jsonl", history_rows)

    total_elapsed = time.perf_counter() - started
    print(
        json.dumps(
            {
                "date": date,
                "dry_run": bool(args.dry_run),
                "provider": args.provider,
                "stage0_candidates": stage0_meta["stats"]["stage0_candidates"],
                "stage1_kept": len(stage1_kept),
                "stage2_analyzed": len(stage2_rows),
                "final_clues": len(clues),
                "concept_clues": len(concept_clues),
                "trade_candidates": len(trade_rows),
                "open_state_items": len(open_state.get("items") or []),
                "tokens_total": ledger.total_used(),
                "token_remaining": max(0, args.token_budget - ledger.total_used()),
                "elapsed_sec": round(total_elapsed, 2),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
