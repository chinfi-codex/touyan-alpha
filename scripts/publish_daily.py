#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import shutil
from pathlib import Path


def cst_today() -> str:
    return (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%Y-%m-%d")


def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish daily report artifacts to docs/")
    ap.add_argument("--date", default="", help="YYYY-MM-DD, default today in Asia/Shanghai")
    ap.add_argument("--slot", default="", choices=["", "0700", "2200"], help="run slot")
    ap.add_argument("--project-dir", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args()

    project = Path(args.project_dir)
    date = args.date or cst_today()
    slot = args.slot

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

    # publish report
    target_name = "index.html" if not slot else f"index-{slot}.html"
    shutil.copy2(report, daily_dir / target_name)
    # always keep a stable entry for that date
    shutil.copy2(report, daily_dir / "index.html")

    # publish raw json for debugging/inspection
    data_dir = docs / "data" / date
    data_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("*.json"):
        shutil.copy2(p, data_dir / p.name)

    # update manifest
    manifest_path = docs / "manifest.json"
    manifest = {"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "days": {}}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if "days" not in manifest or not isinstance(manifest["days"], dict):
                manifest["days"] = {}
        except Exception:
            manifest = {"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "days": {}}

    s = json.loads(summary.read_text(encoding="utf-8"))
    manifest["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest["days"][date] = {
        "slot": slot,
        "counts": s.get("counts") or {},
        "errors": s.get("errors") or {},
        "page": f"{date}/{target_name}",
    }
    ensure_parent(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # update landing page (latest + recent days)
    recent_days = sorted(manifest["days"].keys(), reverse=True)[:30]
    links = "\n".join(
        f"<li><a href='./{d}/index.html'>{d}</a>"
        + (f"（slot: {manifest['days'][d].get('slot') or 'default'}）" if manifest["days"].get(d) else "")
        + "</li>"
        for d in recent_days
    )

    index_html = f"""<!doctype html>
<html lang='zh-CN'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Touyan Alpha Reports</title>
  <style>
    body {{ font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif; margin: 24px; color:#111; }}
    a {{ color:#0b62d6; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .meta {{ color:#666; margin-bottom: 16px; }}
  </style>
</head>
<body>
  <h1>Touyan Alpha 每日页面</h1>
  <div class='meta'>Last updated (UTC): {manifest['updated_at']}</div>
  <p><a href='./{date}/index.html'>打开最新日报（{date}）</a></p>
  <h2>最近 30 天</h2>
  <ul>
    {links}
  </ul>
</body>
</html>
"""
    (docs / "index.html").write_text(index_html, encoding="utf-8")

    print(f"published docs for {date} slot={slot or 'default'}")


if __name__ == "__main__":
    main()
