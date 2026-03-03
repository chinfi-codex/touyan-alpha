#!/usr/bin/env python3
import argparse
import html
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(v):
    return html.escape(str(v or ""))


def is_other_subcategory(value):
    s = (value or "").strip()
    return s in {"其他", "鍏朵粬"}


def top_items(items, limit=30):
    rows = list(items or [])
    rows.sort(key=lambda x: (str(x.get("date") or ""), str(x.get("event_time") or "")), reverse=True)
    return rows[:limit]


def domain_of(url):
    try:
        return (urlparse((url or "").strip()).netloc or "").lower()
    except Exception:
        return ""


def fmt_pct(v):
    if v is None or v == "":
        return ""
    try:
        return f"{float(v):.2f}%"
    except Exception:
        return str(v)


def render_simple_table(title, items, columns, empty_text="无数据", limit=30):
    rows_html = []
    for item in top_items(items, limit=limit):
        tds = []
        for col in columns:
            kind = col["key"]
            if kind == "url":
                link = (item.get("url") or "").strip()
                cell = f"<a href='{fmt(link)}' target='_blank'>link</a>" if link else ""
            elif kind == "domain":
                cell = fmt(domain_of(item.get("url")))
            elif col.get("type") == "pct":
                cell = fmt(fmt_pct(item.get(kind)))
            else:
                cell = fmt(item.get(kind))
            cls = " class='title'" if col.get("title") else ""
            tds.append(f"<td{cls}>{cell}</td>")
        rows_html.append("<tr>" + "".join(tds) + "</tr>")

    body = "\n".join(rows_html) or f"<tr><td colspan='{len(columns)}'>{fmt(empty_text)}</td></tr>"
    head = "".join(f"<th>{fmt(col['label'])}</th>" for col in columns)
    return f"""
    <section class="panel">
      <h2>{fmt(title)} <span>({len(items or [])})</span></h2>
      <table>
        <thead><tr>{head}</tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


def render_notice_panel(items):
    grouped = defaultdict(lambda: defaultdict(list))
    for item in items or []:
        sub = (item.get("subcategory") or "").strip()
        if not sub or is_other_subcategory(sub):
            continue
        company = (item.get("company") or "").strip() or (item.get("symbol") or "").strip() or "未识别公司"
        grouped[sub][company].append(item)

    sub_blocks = []
    for subcategory, company_map in sorted(grouped.items(), key=lambda kv: (-sum(len(v) for v in kv[1].values()), kv[0])):
        rows = []
        ordered_companies = sorted(
            company_map.items(),
            key=lambda kv: (-len(kv[1]), kv[0]),
        )
        for company, company_items in ordered_companies:
            symbol = ""
            for x in company_items:
                if x.get("symbol"):
                    symbol = x.get("symbol")
                    break
            sample_titles = "；".join((x.get("title") or "").strip() for x in company_items[:3])
            latest_url = ""
            for x in company_items:
                if x.get("url"):
                    latest_url = x.get("url")
                    break
            link_html = f"<a href='{fmt(latest_url)}' target='_blank'>link</a>" if latest_url else ""
            rows.append(
                "<tr>"
                f"<td>{fmt(company)}</td>"
                f"<td>{fmt(symbol)}</td>"
                f"<td>{len(company_items)}</td>"
                f"<td class='title'>{fmt(sample_titles)}</td>"
                f"<td>{link_html}</td>"
                "</tr>"
            )

        body = "\n".join(rows) or "<tr><td colspan='5'>无数据</td></tr>"
        sub_blocks.append(
            f"""
            <section class="subpanel">
              <h3>{fmt(subcategory)} <span>({sum(len(v) for v in company_map.values())})</span></h3>
              <table>
                <thead>
                  <tr><th>公司</th><th>代码</th><th>条数</th><th>样本标题</th><th>URL</th></tr>
                </thead>
                <tbody>{body}</tbody>
              </table>
            </section>
            """
        )

    if not sub_blocks:
        sub_blocks.append("<section class='subpanel'><h3>公告</h3><div class='empty'>无非“其他”公告</div></section>")

    total = sum(len(v) for companies in grouped.values() for v in companies.values())
    return f"""
    <section class="panel">
      <h2>公告 <span>({total})</span></h2>
      <div class="stack">
        {''.join(sub_blocks)}
      </div>
    </section>
    """


def render_report(date, base_dir):
    out_dir = base_dir / "output" / date
    summary = load_json(out_dir / "summary.json")

    cninfo_fulltext = load_json(out_dir / "cninfo_fulltext.json")
    cninfo_relation = load_json(out_dir / "cninfo_relation.json")
    p5w_interaction = load_json(out_dir / "p5w_interaction.json")
    tushare_forecast = load_json(out_dir / "tushare_forecast.json")

    # 分类 Tab 导航（点击可滑动到对应区域）
    tabs = [
        ("业绩预告", "forecast"),
        ("机构调研", "relation"),
        ("互动问答", "interaction"),
        ("公告", "notice"),
    ]

    tabs_html = "".join(
        f"""<a class="tab" href="#{anchor}">{label}</a>"""
        for label, anchor in tabs
    )

    forecast_section = f'<section id="forecast">{render_simple_table("业绩预告", tushare_forecast.get("items") or [], [{"label": "Date", "key": "date"}, {"label": "Symbol", "key": "symbol"}, {"label": "Company", "key": "company"}, {"label": "变动下限", "key": "change_range_min", "type": "pct"}, {"label": "变动上限", "key": "change_range_max", "type": "pct"}, {"label": "变动原因", "key": "change_reason", "title": True}, {"label": "Summary", "key": "summary", "title": True}, {"label": "URL", "key": "url"}], limit=30)}</section>'



    relation_section = f'<section id="relation">{render_simple_table("机构调研", cninfo_relation.get("items") or [], [{"label": "Date", "key": "date"}, {"label": "Symbol", "key": "symbol"}, {"label": "Company", "key": "company"}, {"label": "Title", "key": "title", "title": True}, {"label": "URL", "key": "url"}], limit=40)}</section>'

    interaction_section = f'<section id="interaction">{render_simple_table("互动问答", p5w_interaction.get("items") or [], [{"label": "Date", "key": "date"}, {"label": "Symbol", "key": "symbol"}, {"label": "Company", "key": "company"}, {"label": "Question", "key": "title", "title": True}, {"label": "Answer", "key": "summary", "title": True}, {"label": "URL", "key": "url"}], limit=40)}</section>'

    notice_section = f'<section id="notice">{render_notice_panel(cninfo_fulltext.get("items") or [])}</section>'

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Touyan Alpha Report - {fmt(date)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg0:#f3f6f9;
      --bg1:#ffffff;
      --ink:#10212f;
      --muted:#537089;
      --line:#d4e0ea;
      --accent:#0f6ba8;
      --accent2:#0b8f6a;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      font-family:"Noto Sans SC","Sora",sans-serif;
      color:var(--ink);
      background:
        radial-gradient(1200px 500px at 10% -10%, #dff4ef, transparent 65%),
        radial-gradient(1000px 500px at 90% -20%, #dcebf8, transparent 65%),
        var(--bg0);
    }}
    .wrap {{ max-width:1360px; margin:0 auto; padding:28px 20px 40px; }}
    h1,h2,h3 {{ margin:0; font-family:"Sora","Noto Sans SC",sans-serif; }}
    .meta {{ margin-top:8px; color:var(--muted); font-size:14px; }}
    .cards {{
      margin-top:20px;
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
      gap:12px;
    }}
    .card, .panel, .subpanel {{
      background:var(--bg1);
      border:1px solid var(--line);
      border-radius:14px;
      box-shadow:0 8px 20px rgba(16,33,47,.06);
    }}
    .tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:16px; padding:12px 0; border-bottom:1px solid var(--line); position:sticky; top:0; background:rgba(243,246,249,0.95); backdrop-filter:blur(8px); z-index:100; }}
    .tab {{ padding:8px 16px; border-radius:20px; background:var(--bg1); border:1px solid var(--line); color:var(--ink); text-decoration:none; font-size:13px; font-weight:500; transition:all 0.2s; }}
    .tab:hover {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
    .card {{ padding:14px; }}
    .k {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.7px; }}
    .v {{ margin-top:6px; font-size:28px; font-weight:700; color:var(--accent); }}
    .sections {{ margin-top:18px; display:grid; gap:14px; }}
    .panel {{ padding:14px; overflow:auto; }}
    .panel h2 {{ margin-bottom:10px; }}
    .panel h2 span, .subpanel h3 span {{ color:var(--muted); font-weight:500; font-size:13px; }}
    .stack {{ display:grid; gap:12px; }}
    .subpanel {{ padding:12px; }}
    .subpanel h3 {{ margin-bottom:8px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:8px 6px; text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:600; }}
    td.title {{ min-width:320px; }}
    a {{ color:var(--accent); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .empty {{ color:var(--muted); font-size:14px; }}
    @media (max-width:980px) {{
      td.title {{ min-width:220px; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>Touyan Alpha 静态日报</h1>
    <div class="meta">Date: {fmt(summary.get("date") or date)}</div>

    <nav class="tabs">{tabs_html}</nav>

    <div class="sections">
      {forecast_section}
      {relation_section}
      {interaction_section}
      {notice_section}
    </div>
  </main>
</body>
</html>
"""

    out_file = out_dir / "report.html"
    out_file.write_text(html_doc, encoding="utf-8")
    return out_file


def main():
    ap = argparse.ArgumentParser(description="Render static HTML report from output data")
    ap.add_argument("--date", required=True, help="Report date YYYY-MM-DD")
    ap.add_argument("--project-dir", default=str(Path(__file__).resolve().parent), help="Project dir")
    args = ap.parse_args()
    out = render_report(args.date, Path(args.project_dir))
    print(str(out))


if __name__ == "__main__":
    main()
