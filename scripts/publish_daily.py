#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo


REPO = "chinfi-codex/touyan-alpha"
WORKFLOW_FILE = "daily-update-pages.yml"
ACTIONS_URL = f"https://github.com/{REPO}/actions/workflows/{WORKFLOW_FILE}"
RUNS_API_URL = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=14"
SH_TZ = ZoneInfo("Asia/Shanghai")
UTC_TZ = ZoneInfo("UTC")


def cst_today() -> str:
    return dt.datetime.now(SH_TZ).strftime("%Y-%m-%d")


def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def load_manifest(path: Path) -> dict:
    base = {"updated_at": dt.datetime.now(UTC_TZ).isoformat(), "days": {}}
    if not path.exists():
        return base
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return base
    if not isinstance(data, dict):
        return base
    if not isinstance(data.get("days"), dict):
        data["days"] = {}
    if not data.get("updated_at"):
        data["updated_at"] = base["updated_at"]
    return data


def build_entries(days: dict) -> list[dict]:
    items = []
    for date, raw in days.items():
        if not isinstance(raw, dict):
            continue
        counts = raw.get("counts") if isinstance(raw.get("counts"), dict) else {}
        errors = raw.get("errors") if isinstance(raw.get("errors"), dict) else {}
        total = 0
        for value in counts.values():
            try:
                total += int(value or 0)
            except Exception:
                continue
        items.append(
            {
                "date": date,
                "page": raw.get("page") or f"{date}/index.html",
                "counts": counts,
                "errors": errors,
                "count_total": total,
                "error_count": sum(1 for value in errors.values() if value),
            }
        )
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


def build_summary(manifest: dict, entries: list[dict]) -> dict:
    latest = entries[0] if entries else {}
    return {
        "latest_date": latest.get("date", ""),
        "latest_page": latest.get("page", ""),
        "latest_counts": latest.get("counts", {}),
        "days_7": len(entries[:7]),
        "days_30": len(entries[:30]),
        "last_updated": manifest.get("updated_at", ""),
    }


def build_index_html(manifest: dict, entries: list[dict], summary: dict) -> str:
    manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    entries_json = json.dumps(entries[:30], ensure_ascii=False, separators=(",", ":"))
    summary_json = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    actions_url_json = json.dumps(ACTIONS_URL, ensure_ascii=False)
    runs_api_json = json.dumps(RUNS_API_URL, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Touyan Alpha Dashboard</title>
  <meta name="description" content="Touyan Alpha 每日投研汇总与 GitHub Action 状态看板">
  <style>
    :root{{--bg:#081018;--panel:#0e1a26;--panel2:#122232;--text:#e9eef4;--muted:#8ca1b3;--line:rgba(143,173,196,.16);--accent:#62d2ff;--mint:#71efc6;--ok:#50d389;--bad:#ff7171;--warn:#f3c55d;--run:#65b6ff;--shadow:0 20px 60px rgba(0,0,0,.35);--radius:24px;--sans:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;--mono:Consolas,"SFMono-Regular",monospace}}
    *{{box-sizing:border-box}} html{{color-scheme:dark}} body{{margin:0;font-family:var(--sans);color:var(--text);background:radial-gradient(circle at top left,rgba(98,210,255,.14),transparent 28%),radial-gradient(circle at top right,rgba(113,239,198,.12),transparent 22%),linear-gradient(180deg,#061019,#081018 55%,#09121c)}} body::before{{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(180deg,rgba(0,0,0,.45),transparent)}} a{{color:inherit;text-decoration:none}}
    .shell{{width:min(calc(100vw - 32px),1240px);margin:0 auto;padding:32px 0 56px;position:relative;z-index:1}} .hero,.panel{{border:1px solid var(--line);box-shadow:var(--shadow)}} .hero{{overflow:hidden;position:relative;padding:28px;border-radius:28px;background:linear-gradient(135deg,rgba(14,35,52,.94),rgba(7,18,28,.96))}} .hero::after{{content:"";position:absolute;width:280px;height:280px;right:-80px;top:-120px;border-radius:50%;background:radial-gradient(circle,rgba(98,210,255,.22),transparent 68%)}}
    .eyebrow{{display:inline-flex;gap:8px;align-items:center;padding:8px 12px;border-radius:999px;font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--mint);background:rgba(113,239,198,.08);border:1px solid rgba(113,239,198,.18)}} .hero-grid{{margin-top:18px;display:grid;grid-template-columns:minmax(0,1.35fr) minmax(320px,.9fr);gap:20px;align-items:end}} h1{{margin:0;font-size:clamp(34px,5vw,58px);line-height:.96;letter-spacing:-.04em;max-width:8ch}} .copy{{margin-top:16px;max-width:54ch;color:#b7c5d2;line-height:1.7;font-size:15px}}
    .actions{{display:flex;flex-wrap:wrap;gap:12px;margin-top:24px}} .btn{{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 16px;border-radius:999px;font-weight:700;transition:transform .16s ease,border-color .16s ease,background .16s ease}} .btn:hover{{transform:translateY(-1px)}} .btn-primary{{color:#04121d;background:linear-gradient(135deg,var(--accent),#a2e7ff)}} .btn-secondary{{background:rgba(255,255,255,.04);border:1px solid rgba(143,173,196,.18)}}
    .hero-side,.stack,.day-list{{display:grid;gap:12px}} .signal,.panel{{background:linear-gradient(180deg,rgba(11,27,40,.92),rgba(9,20,30,.94))}} .signal{{padding:18px;border-radius:20px;border:1px solid rgba(143,173,196,.14)}} .label{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}} .value{{margin-top:10px;font-size:28px;font-weight:700;letter-spacing:-.03em}} .meta{{margin-top:10px;font-size:13px;line-height:1.5;color:var(--muted)}}
    .layout{{margin-top:24px;display:grid;gap:20px}} .grid-3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}} .panel{{overflow:hidden;position:relative;border-radius:24px}} .panel-head{{display:flex;justify-content:space-between;gap:16px;padding:22px 22px 0}} .panel-body{{padding:18px 22px 22px}} .panel h2{{margin:0;font-size:18px;letter-spacing:-.02em}} .sub{{margin-top:6px;color:var(--muted);font-size:13px;line-height:1.55}}
    .metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}} .metric,.row,.day-row{{padding:14px;border-radius:16px;background:rgba(255,255,255,.03);border:1px solid rgba(143,173,196,.1)}} .metric-value{{margin-top:10px;font-size:28px;font-weight:700;letter-spacing:-.04em}} .foot{{margin-top:8px;font-size:12px;color:var(--muted);line-height:1.5}}
    .row{{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:center}} .source-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px 14px;border-radius:14px;background:rgba(255,255,255,.03);border:1px solid rgba(143,173,196,.08)}} .mono{{font-family:var(--mono)}} .muted{{color:var(--muted)}} .strong{{font-weight:600}}
    .badge{{display:inline-flex;align-items:center;justify-content:center;min-height:30px;padding:0 12px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap}} .success{{color:#dcfff0;background:rgba(80,211,137,.16);border:1px solid rgba(80,211,137,.24)}} .failure{{color:#ffe4e4;background:rgba(255,113,113,.16);border:1px solid rgba(255,113,113,.24)}} .warning{{color:#fff2cb;background:rgba(243,197,93,.16);border:1px solid rgba(243,197,93,.24)}} .running{{color:#e1f0ff;background:rgba(101,182,255,.16);border:1px solid rgba(101,182,255,.24)}} .neutral{{color:#d7e2eb;background:rgba(143,173,196,.12);border:1px solid rgba(143,173,196,.2)}}
    .day-row{{display:grid;grid-template-columns:104px minmax(0,1fr) auto;gap:12px;align-items:center}} .day-state{{position:relative;padding-left:18px;font-size:13px;color:#c7d3dd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}} .day-state::before{{content:"";position:absolute;left:0;top:50%;width:9px;height:9px;border-radius:50%;transform:translateY(-50%);background:var(--muted)}} .day-state.success::before{{background:var(--ok)}} .day-state.failure::before{{background:var(--bad)}} .day-state.warning::before{{background:var(--warn)}} .day-state.running::before{{background:var(--run)}}
    .table-wrap{{overflow:auto;border-radius:18px;border:1px solid rgba(143,173,196,.1);background:rgba(2,9,14,.26)}} table{{width:100%;border-collapse:collapse;min-width:760px}} th,td{{text-align:left;padding:14px 16px;border-bottom:1px solid rgba(143,173,196,.08);vertical-align:middle}} th{{color:var(--muted);font-size:12px;letter-spacing:.08em;text-transform:uppercase;font-weight:600;background:rgba(255,255,255,.02)}} tr:last-child td{{border-bottom:none}} .link{{color:var(--accent);font-weight:600}} .hidden{{display:none!important}} .footer-note{{margin-top:10px;color:var(--muted);font-size:12px;line-height:1.6}}
    @media (max-width:1100px){{.hero-grid,.grid-3,.metrics{{grid-template-columns:1fr}}}} @media (max-width:720px){{.shell{{width:min(calc(100vw - 20px),1240px);padding:16px 0 28px}} .hero,.panel-head,.panel-body{{padding-left:16px;padding-right:16px}} .hero{{padding-top:20px;padding-bottom:20px}} .panel-head{{padding-top:18px}} .panel-body{{padding-bottom:18px}} .row,.day-row{{grid-template-columns:1fr}} h1{{max-width:none}}}}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Touyan Alpha / Daily Intelligence Monitor</div>
      <div class="hero-grid">
        <div>
          <h1>每日投研汇总 Dashboard</h1>
          <div class="copy">聚合最近日报、数据覆盖情况和 GitHub Action 运行状态。首页保持纯静态发布，运行状态通过公开 GitHub API 实时刷新，API 不可用时自动降级。</div>
          <div class="actions">
            <a id="latest-report-button" class="btn btn-primary" href="./">打开最新日报</a>
            <a class="btn btn-secondary" href="{ACTIONS_URL}" target="_blank" rel="noreferrer">查看 GitHub Actions</a>
          </div>
        </div>
        <div class="hero-side">
          <div class="signal">
            <div class="label">最新日报</div>
            <div id="hero-latest-date" class="value mono">--</div>
            <div id="hero-latest-meta" class="meta">等待首页数据加载</div>
          </div>
          <div class="signal">
            <div class="label">最近一次运行</div>
            <div id="hero-run-status" class="value">加载中</div>
            <div id="hero-run-meta" class="meta">正在获取 GitHub Actions 运行状态</div>
          </div>
        </div>
      </div>
    </section>
    <section class="layout">
      <div class="grid-3">
        <article class="panel">
          <div class="panel-head"><div><h2>数据覆盖</h2><div class="sub">基于站内 manifest 统计最近日报数量和最新一天的来源覆盖情况。</div></div></div>
          <div class="panel-body">
            <div class="metrics">
              <div class="metric"><div class="label">最近 7 天日报</div><div id="metric-days-7" class="metric-value mono">0</div><div class="foot">按 manifest 中已有日期计数</div></div>
              <div class="metric"><div class="label">最近 30 天日报</div><div id="metric-days-30" class="metric-value mono">0</div><div class="foot">首页默认展示最近 30 天</div></div>
              <div class="metric"><div class="label">最新日报总条数</div><div id="metric-latest-total" class="metric-value mono">0</div><div class="foot">按最新日报各源 count 合计</div></div>
            </div>
            <div id="source-list" class="stack"></div>
          </div>
        </article>
        <article class="panel">
          <div class="panel-head"><div><h2>运行状态</h2><div class="sub">读取公开 GitHub Actions API，按上海日期归档最近运行情况。</div></div></div>
          <div class="panel-body">
            <div id="status-list" class="stack"></div>
            <div id="status-fallback" class="footer-note hidden">实时状态暂不可用。首页仍可浏览最近日报，详细运行记录可在 <a class="link" href="{ACTIONS_URL}" target="_blank" rel="noreferrer">GitHub Actions</a> 查看。</div>
          </div>
        </article>
        <article class="panel">
          <div class="panel-head"><div><h2>近 7 天趋势</h2><div class="sub">每天只取当天最新一条 workflow 运行，展示 success、failure、running 等状态。</div></div></div>
          <div class="panel-body"><div id="day-list" class="day-list"></div></div>
        </article>
      </div>
      <article class="panel">
        <div class="panel-head"><div><h2>最近日报列表</h2><div class="sub">展示最近 30 天日报入口、主要数据源条数和错误数。</div></div></div>
        <div class="panel-body">
          <div class="table-wrap">
            <table>
              <thead><tr><th>日期</th><th>日报入口</th><th>来源条数</th><th>错误数</th><th>主要来源</th></tr></thead>
              <tbody id="reports-table-body"></tbody>
            </table>
          </div>
          <div class="footer-note">更新时间 <span id="footer-updated-at" class="mono">--</span> UTC。实时运行状态与站内 manifest 独立获取，互不阻塞。</div>
        </div>
      </article>
    </section>
  </main>
  <script>
    const ACTIONS_URL = {actions_url_json};
    const RUNS_API_URL = {runs_api_json};
    const INITIAL_MANIFEST = {manifest_json};
    const INITIAL_ENTRIES = {entries_json};
    const INITIAL_SUMMARY = {summary_json};
    const SOURCE_LABELS = {{
      cninfo_fulltext: "公告全文",
      cninfo_relation: "机构调研",
      p5w_interaction: "互动问答",
      tushare_forecast: "业绩预告",
      tavily_news: "新闻动态",
      zsxq: "知识星球",
      clippings: "Clippings",
    }};
    const STATUS_META = {{
      success: {{ label: "成功", tone: "success" }},
      failure: {{ label: "失败", tone: "failure" }},
      cancelled: {{ label: "取消", tone: "warning" }},
      skipped: {{ label: "跳过", tone: "warning" }},
      timed_out: {{ label: "超时", tone: "failure" }},
      action_required: {{ label: "待处理", tone: "warning" }},
      queued: {{ label: "排队中", tone: "warning" }},
      in_progress: {{ label: "运行中", tone: "running" }},
      completed: {{ label: "已完成", tone: "neutral" }},
      unavailable: {{ label: "不可用", tone: "neutral" }},
      unknown: {{ label: "未知", tone: "neutral" }},
    }};
    const state = {{ manifest: INITIAL_MANIFEST, entries: INITIAL_ENTRIES, summary: INITIAL_SUMMARY }};

    function fmtNum(value) {{
      return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
    }}

    function fmtUtc(iso) {{
      if (!iso) return "--";
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return "--";
      return new Intl.DateTimeFormat("zh-CN", {{
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        hour12: false, timeZone: "UTC",
      }}).format(d);
    }}

    function fmtSh(iso) {{
      if (!iso) return "--";
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return "--";
      return new Intl.DateTimeFormat("zh-CN", {{
        month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
        hour12: false, timeZone: "Asia/Shanghai",
      }}).format(d);
    }}

    function shDay(iso) {{
      if (!iso) return "";
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return "";
      const parts = new Intl.DateTimeFormat("en-CA", {{
        timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
      }}).formatToParts(d);
      const out = {{}};
      for (const p of parts) if (p.type !== "literal") out[p.type] = p.value;
      return `${{out.year}}-${{out.month}}-${{out.day}}`;
    }}

    function esc(value) {{
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }}

    function badgeClass(tone) {{
      return `badge ${{tone || "neutral"}}`;
    }}

    function sourceLabel(key) {{
      return SOURCE_LABELS[key] || key;
    }}

    function countTotal(counts) {{
      return Object.values(counts || {{}}).reduce((sum, value) => sum + (Number(value) || 0), 0);
    }}

    function topSources(counts, limit = 3) {{
      return Object.entries(counts || {{}})
        .sort((a, b) => (Number(b[1]) || 0) - (Number(a[1]) || 0))
        .slice(0, limit)
        .map(([key, value]) => `${{sourceLabel(key)}} ${{fmtNum(value)}}`);
    }}

    function normalizeRun(run) {{
      const status = run.status || "unknown";
      const conclusion = run.conclusion || "";
      let stateKey = "unknown";
      if (status === "in_progress") stateKey = "in_progress";
      else if (status === "queued") stateKey = "queued";
      else if (status === "completed") stateKey = conclusion || "completed";
      const meta = STATUS_META[stateKey] || STATUS_META.unknown;
      const started = run.run_started_at || run.created_at || "";
      const updated = run.updated_at || "";
      let duration = null;
      if (started && updated) {{
        const ms = new Date(updated).getTime() - new Date(started).getTime();
        if (!Number.isNaN(ms) && ms >= 0) duration = Math.round(ms / 60000);
      }}
      return {{
        ...run,
        stateKey,
        label: meta.label,
        tone: meta.tone,
        shanghaiDay: shDay(started || updated || run.created_at),
        durationMinutes: duration,
      }};
    }}

    function renderManifest() {{
      const latest = state.entries[0] || null;
      const latestCounts = state.summary.latest_counts || {{}};
      const latestTotal = countTotal(latestCounts);
      document.getElementById("hero-latest-date").textContent = state.summary.latest_date || "--";
      document.getElementById("hero-latest-meta").textContent = latest
        ? `最新日报共 ${{fmtNum(latestTotal)}} 条，${{topSources(latestCounts, 2).join(" / ") || "暂无数据"}}`
        : "暂无已发布日报";
      document.getElementById("latest-report-button").setAttribute("href", latest ? `./${{latest.page}}` : "./");
      document.getElementById("metric-days-7").textContent = fmtNum(state.summary.days_7 || 0);
      document.getElementById("metric-days-30").textContent = fmtNum(state.summary.days_30 || 0);
      document.getElementById("metric-latest-total").textContent = fmtNum(latestTotal);
      document.getElementById("footer-updated-at").textContent = fmtUtc(state.summary.last_updated || state.manifest.updated_at);

      const sourceList = document.getElementById("source-list");
      const sourceEntries = Object.entries(latestCounts).sort((a, b) => (Number(b[1]) || 0) - (Number(a[1]) || 0));
      sourceList.innerHTML = sourceEntries.length
        ? sourceEntries.map(([key, value]) => `
            <div class="source-row">
              <div><div class="strong">${{esc(sourceLabel(key))}}</div><div class="muted">最新日报来源条数</div></div>
              <div class="mono strong">${{fmtNum(value)}}</div>
            </div>
          `).join("")
        : `<div class="source-row"><div class="muted">最新日报暂无来源计数</div><div class="mono strong">0</div></div>`;

      document.getElementById("reports-table-body").innerHTML = state.entries.length
        ? state.entries.map((entry) => `
            <tr>
              <td class="mono strong">${{esc(entry.date)}}</td>
              <td><a class="link" href="./${{esc(entry.page)}}">打开日报</a></td>
              <td class="mono">${{fmtNum(entry.count_total)}}</td>
              <td class="mono">${{fmtNum(entry.error_count)}}</td>
              <td>${{esc(topSources(entry.counts).join(" / ") || "暂无")}}</td>
            </tr>
          `).join("")
        : `<tr><td colspan="5" class="muted">暂无已发布日报</td></tr>`;
    }}

    function renderRunFallback() {{
      document.getElementById("hero-run-status").textContent = "实时状态不可用";
      document.getElementById("hero-run-meta").textContent = "GitHub API 获取失败，已降级为仅展示日报数据";
      document.getElementById("status-fallback").classList.remove("hidden");
      document.getElementById("status-list").innerHTML = `
        <div class="row">
          <span class="${{badgeClass("neutral")}}">不可用</span>
          <div><div class="strong">GitHub Actions API 暂时不可达</div><div class="muted">不影响首页日报浏览，可直接打开 Actions 页面查看运行详情。</div></div>
          <a class="link" href="${{ACTIONS_URL}}" target="_blank" rel="noreferrer">查看</a>
        </div>
      `;
      document.getElementById("day-list").innerHTML = `
        <div class="day-row">
          <div class="mono">--</div>
          <div class="day-state">暂无实时运行趋势</div>
          <a class="link" href="${{ACTIONS_URL}}" target="_blank" rel="noreferrer">打开</a>
        </div>
      `;
    }}

    function renderRuns(rawRuns) {{
      const runs = (rawRuns || []).map(normalizeRun);
      const latest = runs[0] || null;
      const today = shDay(new Date().toISOString());
      const todayRun = runs.find((run) => run.shanghaiDay === today) || null;
      const byDay = new Map();
      for (const run of runs) if (run.shanghaiDay && !byDay.has(run.shanghaiDay)) byDay.set(run.shanghaiDay, run);
      const days = Array.from(byDay.values()).sort((a, b) => String(b.shanghaiDay).localeCompare(String(a.shanghaiDay))).slice(0, 7);
      document.getElementById("status-fallback").classList.add("hidden");

      if (latest) {{
        document.getElementById("hero-run-status").textContent = latest.label;
        document.getElementById("hero-run-meta").textContent =
          `#${{latest.run_number}} · ${{fmtSh(latest.run_started_at || latest.created_at)}} · ${{latest.event || "unknown"}}` +
          `${{latest.durationMinutes != null ? ` · ${{latest.durationMinutes}} 分钟` : ""}}`;
      }} else {{
        document.getElementById("hero-run-status").textContent = "暂无运行记录";
        document.getElementById("hero-run-meta").textContent = "GitHub API 没有返回最近运行记录";
      }}

      const rows = [];
      if (latest) rows.push(`
        <div class="row">
          <span class="${{badgeClass(latest.tone)}}">${{esc(latest.label)}}</span>
          <div><div class="strong">最近一次运行 #${{esc(latest.run_number)}}</div><div class="muted">触发方式 ${{esc(latest.event || "unknown")}}，开始于 ${{esc(fmtSh(latest.run_started_at || latest.created_at))}}</div></div>
          <a class="link" href="${{esc(latest.html_url || ACTIONS_URL)}}" target="_blank" rel="noreferrer">详情</a>
        </div>
      `);
      if (todayRun) rows.push(`
        <div class="row">
          <span class="${{badgeClass(todayRun.tone)}}">${{esc(todayRun.label)}}</span>
          <div><div class="strong">今日运行状态</div><div class="muted">${{esc(todayRun.shanghaiDay)}} 的最新运行，${{todayRun.durationMinutes != null ? `耗时 ${{todayRun.durationMinutes}} 分钟` : "耗时待定"}}。</div></div>
          <a class="link" href="${{esc(todayRun.html_url || ACTIONS_URL)}}" target="_blank" rel="noreferrer">详情</a>
        </div>
      `);
      else rows.push(`
        <div class="row">
          <span class="${{badgeClass("warning")}}">未见运行</span>
          <div><div class="strong">今日尚未检测到运行</div><div class="muted">按上海日期归档，当前没有今天的 workflow 记录。</div></div>
          <a class="link" href="${{ACTIONS_URL}}" target="_blank" rel="noreferrer">查看</a>
        </div>
      `);
      if (latest) rows.push(`
        <div class="row">
          <span class="${{badgeClass(latest.tone)}}">${{esc(latest.event || "unknown")}}</span>
          <div><div class="strong">运行耗时与触发方式</div><div class="muted">${{latest.durationMinutes != null ? `${{latest.durationMinutes}} 分钟` : "耗时未知"}}，actor ${{esc((latest.actor && latest.actor.login) || "unknown")}}。</div></div>
          <a class="link" href="${{esc(latest.html_url || ACTIONS_URL)}}" target="_blank" rel="noreferrer">详情</a>
        </div>
      `);
      document.getElementById("status-list").innerHTML = rows.join("");

      document.getElementById("day-list").innerHTML = days.length
        ? days.map((run) => `
            <div class="day-row">
              <div class="mono strong">${{esc(run.shanghaiDay)}}</div>
              <div class="day-state ${{esc(run.tone)}}">#${{esc(run.run_number)}} · ${{esc(run.label)}} · ${{esc(run.event || "unknown")}}</div>
              <a class="link" href="${{esc(run.html_url || ACTIONS_URL)}}" target="_blank" rel="noreferrer">详情</a>
            </div>
          `).join("")
        : `<div class="day-row"><div class="mono">--</div><div class="day-state">暂无趋势数据</div><a class="link" href="${{ACTIONS_URL}}" target="_blank" rel="noreferrer">打开</a></div>`;
    }}

    async function loadManifest() {{
      try {{
        const res = await fetch("./manifest.json", {{ cache: "no-store" }});
        if (!res.ok) throw new Error("manifest");
        const manifest = await res.json();
        if (manifest && typeof manifest === "object" && manifest.days && typeof manifest.days === "object") {{
          const entries = Object.entries(manifest.days).map(([date, raw]) => {{
            const counts = raw && typeof raw.counts === "object" ? raw.counts : {{}};
            const errors = raw && typeof raw.errors === "object" ? raw.errors : {{}};
            return {{
              date,
              page: raw.page || `${{date}}/index.html`,
              counts,
              errors,
              count_total: countTotal(counts),
              error_count: Object.values(errors).filter(Boolean).length,
            }};
          }}).sort((a, b) => String(b.date).localeCompare(String(a.date)));
          state.manifest = manifest;
          state.entries = entries.slice(0, 30);
          state.summary = {{
            latest_date: state.entries[0] ? state.entries[0].date : "",
            latest_page: state.entries[0] ? state.entries[0].page : "",
            latest_counts: state.entries[0] ? state.entries[0].counts : {{}},
            days_7: state.entries.slice(0, 7).length,
            days_30: state.entries.slice(0, 30).length,
            last_updated: manifest.updated_at || INITIAL_SUMMARY.last_updated,
          }};
        }}
      }} catch (_e) {{
      }}
      renderManifest();
    }}

    async function loadRuns() {{
      try {{
        const res = await fetch(RUNS_API_URL, {{
          headers: {{ Accept: "application/vnd.github+json" }},
          cache: "no-store",
        }});
        if (!res.ok) throw new Error("runs");
        const payload = await res.json();
        renderRuns(Array.isArray(payload.workflow_runs) ? payload.workflow_runs : []);
      }} catch (_e) {{
        renderRunFallback();
      }}
    }}

    renderManifest();
    loadManifest();
    loadRuns();
  </script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish daily report artifacts to docs/")
    ap.add_argument("--date", default="", help="YYYY-MM-DD, default today in Asia/Shanghai")
    ap.add_argument("--project-dir", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args()

    project = Path(args.project_dir)
    date = args.date or cst_today()
    out_dir = project / "output" / date
    report = out_dir / "report.html"
    summary = out_dir / "summary.json"
    if not report.exists():
        raise SystemExit(f"report not found: {report}")
    if not summary.exists():
        raise SystemExit(f"summary not found: {summary}")

    docs = project / "docs"
    daily_dir = docs / date
    daily_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report, daily_dir / "index.html")

    data_dir = docs / "data" / date
    data_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("*.json"):
        shutil.copy2(p, data_dir / p.name)

    manifest_path = docs / "manifest.json"
    manifest = load_manifest(manifest_path)
    s = json.loads(summary.read_text(encoding="utf-8"))
    manifest["updated_at"] = dt.datetime.now(UTC_TZ).isoformat()
    manifest["days"][date] = {
        "counts": s.get("counts") or {},
        "errors": s.get("errors") or {},
        "page": f"{date}/index.html",
    }
    ensure_parent(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    entries = build_entries(manifest["days"])
    index_html = build_index_html(manifest, entries, build_summary(manifest, entries))
    (docs / "index.html").write_text(index_html, encoding="utf-8")
    print(f"published docs for {date}")


if __name__ == "__main__":
    main()
