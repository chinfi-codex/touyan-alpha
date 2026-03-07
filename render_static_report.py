#!/usr/bin/env python3
import argparse
import concurrent.futures
import html
import json
import os
from collections import defaultdict
from datetime import datetime
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


def clip_text(text, limit=120):
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def first_sentence(text, limit=88):
    value = " ".join(str(text or "").split())
    if not value:
        return ""
    for sep in ("。", "；", ";", ".", "！", "!", "？", "?"):
        pos = value.find(sep)
        if 0 < pos < limit:
            return value[: pos + 1]
    return clip_text(value, limit=limit)


def get_kimi_api_key():
    """从环境变量或 .env 文件获取 Kimi API key"""
    # 首先尝试从环境变量获取
    api_key = os.environ.get("KIMI_API_KEY")
    if api_key:
        return api_key
    
    # 尝试从 .env 文件读取
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() == "KIMI_API_KEY":
                    return value.strip().strip('"\'')
    return None


def generate_ai_summary(items):
    """使用豆包 API 生成互动问答的 AI 总结"""
    if not items:
        return "暂无数据"
    
    # 准备数据
    content_parts = []
    for item in items[:50]:  # 限制前50条，避免超出token限制
        company = item.get("company") or item.get("symbol") or "未知公司"
        question = item.get("title") or ""
        answer = item.get("summary") or ""
        if question or answer:
            content_parts.append(f"【{company}】\n问：{question}\n答：{answer}")
    
    if not content_parts:
        return "暂无有效数据"
    
    prompt_text = "请对以下投资者互动问答内容进行总结，提炼关键信息和热点话题：\n\n" + "\n\n".join(content_parts[:20])
    
    # 豆包 API 配置
    try:
        import openai
        
        api_key = "7c45a349-5a95-4885-a7b6-df6ed599ed5e"
        base_url = "https://ark.cn-beijing.volces.com/api/v3"
        model_id = "ep-20260103112951-vxd7j"
        system_message = """你是专业的金融分析师，擅长总结投资者互动问答内容。
请遵循以下规则：
1. 去除股东人数相关信息
2. 每个公司的总结单独一行，格式为"公司名：核心内容"
3. 用简洁的中文总结主要观点，突出重点
4. 控制在300字以内"""
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt_text},
        ]
        
        # openai>=1.x
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(api_key=api_key, base_url=base_url)
            completion = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0,
                top_p=0.8,
            )
            if hasattr(completion, "choices") and completion.choices:
                return completion.choices[0].message.content
        else:
            # openai<1.x
            openai.api_key = api_key
            openai.api_base = base_url
            completion = openai.ChatCompletion.create(
                model=model_id,
                messages=messages,
                temperature=0,
                top_p=0.8,
            )
            choices = completion.get("choices", []) if isinstance(completion, dict) else []
            if choices:
                return choices[0]["message"]["content"]
        
        return "AI总结请求失败"
        
    except Exception as e:
        return f"AI总结生成失败: {str(e)[:100]}"


def _is_shareholder_question(text: str) -> bool:
    """判断是否为股东数相关问题"""
    if not text:
        return False
    text = text.lower()
    shareholder_keywords = [
        "股东人数", "股东户数", "股东数量", "股东名数", "股东名册",
        "股东总户数", "股东总人数", "股东总数量", "股东总共有",
        "最新股东", "截至.*股东", "期末.*股东", "报告期.*股东",
        "股东情况", "股东信息", "持股户数",
    ]
    import re
    for kw in shareholder_keywords:
        if re.search(kw, text):
            return True
    return False


def generate_company_ai_summary(company_name: str, items: list) -> str:
    """Build a short local summary without remote AI calls."""
    if not items:
        return "??????"

    topics = []
    for item in items[:4]:
        question = clip_text(item.get("title") or "", 28)
        answer = clip_text(item.get("summary") or "", 36)
        fragment = question or answer
        if answer and question:
            fragment = f"{question}?{answer}"
        if fragment:
            topics.append(fragment)

    if not topics:
        return "???????"
    return clip_text("?".join(topics), 90)


def render_interaction_section_with_ai(items, limit=100):
    """Render grouped interaction Q&A with compact accordion blocks."""

    filtered_items = []
    for item in (items or []):
        combined_text = f"{item.get('title', '')} {item.get('summary', '')}"
        if not _is_shareholder_question(combined_text):
            filtered_items.append(item)

    companies = defaultdict(list)
    for item in filtered_items:
        company = item.get("company") or item.get("symbol") or "未知公司"
        companies[company].append(item)

    cards = []
    ordered_companies = sorted(companies.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for idx, (company_name, company_items) in enumerate(ordered_companies):
        symbol = company_items[0].get("symbol", "")
        card_id = f"interaction-{idx}"
        ai_summary = generate_company_ai_summary(company_name, company_items)
        teaser = clip_text(ai_summary, limit=80)

        rows = []
        for item in company_items[:20]:
            link = (item.get("url") or "").strip()
            link_html = f"<a href='{fmt(link)}' target='_blank'>原文</a>" if link else ""
            rows.append(
                "<tr>"
                f"<td>{fmt(item.get('date'))}</td>"
                f"<td class='title'>{fmt(item.get('title'))}</td>"
                f"<td class='title'>{fmt(clip_text(item.get('summary'), 140))}</td>"
                f"<td>{link_html}</td>"
                "</tr>"
            )

        more_count = max(0, len(company_items) - 20)
        more_hint = f"<span class='meta-badge subtle'>+{more_count}</span>" if more_count else ""
        detail_html = (
            "<table class='detail-table qa-table'>"
            "<thead><tr><th>日期</th><th>问题</th><th>摘要</th><th>链接</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            if rows
            else "<div class='empty'>暂无互动问答数据</div>"
        )

        cards.append(
            f"""
        <article class="accordion-block interaction-block" id="{card_id}">
          <button class="accordion-trigger" type="button" data-target="{card_id}-body" aria-expanded="false">
            <span class="accordion-main">
              <span class="accordion-title">{fmt(company_name)}</span>
              <span class="meta-badge">{fmt(symbol)}</span>
              <span class="meta-badge strong">{len(company_items)}问</span>
              {more_hint}
            </span>
            <span class="accordion-summary">{fmt(teaser)}</span>
            <span class="accordion-icon" aria-hidden="true">&#9662;</span>
          </button>
          <div class="accordion-body collapsed" id="{card_id}-body">
            <div class="inline-summary">
              <span class="inline-summary-label">AI</span>
              <div class="inline-summary-text clamp-3">{fmt(ai_summary)}</div>
            </div>
            {detail_html}
          </div>
        </article>
        """
        )

    total_companies = len(companies)
    total_items = len(filtered_items)
    return f"""
    <section id="interaction" class="panel compact-panel">
      <div class="section-head">
        <h2>互动问答</h2>
        <span class="meta-badge strong">{total_companies}家公司 / {total_items}条</span>
      </div>
      <div class="section-summary">按公司聚合展示，默认折叠明细，仅保留核心摘要与问答数。</div>
      <div class="accordion-list">
        {''.join(cards) or "<div class='empty'>暂无互动问答数据</div>"}
      </div>
    </section>
    """


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


def is_excluded_subcategory(sub):
    """排除快报等分类"""
    excluded = {"快报"}
    return sub in excluded


def optimize_reason_with_ai(reason_text, company_name=""):
    """Local fallback summary for forecast reasons."""
    if not reason_text:
        return ""
    summary = " ".join(str(reason_text).split())
    return clip_text(summary, 100)


def render_forecast_panel(items):
    """Render compact forecast section grouped by company."""
    grouped = defaultdict(list)
    for item in items or []:
        company = (item.get("company") or "").strip() or (item.get("symbol") or "").strip() or "未知公司"
        grouped[company].append(item)

    ordered_companies = sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    top_company = ordered_companies[0][0] if ordered_companies else None
    blocks = []

    for idx, (company, company_items) in enumerate(ordered_companies):
        symbol = next((x.get("symbol") for x in company_items if x.get("symbol")), "")
        card_id = f"forecast-{idx}"
        seen_reasons = set()
        reason_parts = []
        metrics_rows = []

        for item in company_items:
            forecast_type = item.get("forecast_type", "")
            performance_change = item.get("performance_change", "")
            forecast_value = item.get("forecast_value", "")
            change_reason = item.get("change_reason", "")
            if forecast_type and performance_change:
                metrics_rows.append(
                    "<tr>"
                    f"<td>{fmt(forecast_type)}</td>"
                    f"<td class='title'>{fmt(performance_change)}</td>"
                    f"<td>{fmt(forecast_value)}</td>"
                    "</tr>"
                )
            if change_reason and change_reason not in seen_reasons:
                seen_reasons.add(change_reason)
                reason_parts.append(change_reason)

        optimized_reason = ""
        if reason_parts:
            optimized_reason = optimize_reason_with_ai("；".join(reason_parts), company)
        summary_text = clip_text(optimized_reason or "暂无核心变动原因", 96)
        detail_table = (
            "<table class='detail-table forecast-metrics'>"
            "<thead><tr><th>预测指标</th><th>业绩变动</th><th>预测数值</th></tr></thead>"
            f"<tbody>{''.join(metrics_rows)}</tbody></table>"
            if metrics_rows
            else "<div class='empty'>暂无详细业绩指标</div>"
        )

        expanded = False
        blocks.append(
            f"""
        <article class="accordion-block forecast-block" id="{card_id}">
          <button class="accordion-trigger" type="button" data-target="{card_id}-body" aria-expanded="{'true' if expanded else 'false'}">
            <span class="accordion-main">
              <span class="accordion-title">{fmt(company)}</span>
              <span class="meta-badge">{fmt(symbol)}</span>
              <span class="meta-badge strong">{len(company_items)}项</span>
            </span>
            <span class="accordion-summary">{fmt(summary_text)}</span>
            <span class="accordion-icon{' is-open' if expanded else ''}" aria-hidden="true">&#9662;</span>
          </button>
          <div class="accordion-body{' open' if expanded else ' collapsed'}" id="{card_id}-body">
            <div class="inline-summary">
              <span class="inline-summary-label">原因</span>
              <div class="inline-summary-text clamp-3">{fmt(optimized_reason or '暂无核心变动原因')}</div>
            </div>
            {detail_table}
          </div>
        </article>
        """
        )

    total_companies = len(grouped)
    total_items = len(items or [])
    return f"""
    <section id="forecast" class="panel compact-panel">
      <div class="section-head">
        <h2>业绩预告</h2>
        <span class="meta-badge strong">{total_companies}家公司 / {total_items}条</span>
      </div>
      <div class="section-summary">默认全部折叠，点击展开查看详情，减少纵向占用。</div>
      <div class="accordion-list">
        {''.join(blocks) or "<div class='empty'>暂无业绩预告数据</div>"}
      </div>
    </section>
    """


def render_relation_section_with_ai(items, limit=40):
    """Render compact relation table with merged action column."""
    rows_html = []
    display_items = top_items(items, limit=limit)

    for idx, item in enumerate(display_items):
        symbol = fmt(item.get('symbol'))
        company = fmt(item.get('company'))
        company_label = f"{company} <span class='inline-symbol'>{symbol}</span>" if symbol else company
        date = fmt(item.get('date'))
        title = fmt(item.get('title'))
        url = (item.get('url') or "").strip()
        item_key = f"relation_{idx}"
        link_html = f"<a href='{fmt(url)}' target='_blank'>原文</a>" if url else ""

        rows_html.append(
            "<tr>"
            f"<td>{date}</td>"
            f"<td class='title'>{company_label}</td>"
            f"<td class='title'>{title}</td>"
            f"<td><div class='action-group'>{link_html}</div></td>"
            "</tr>"
        )

    body = "\n".join(rows_html) or "<tr><td colspan='4'>暂无机构调研数据</td></tr>"
    total = len(items or [])
    return f"""
    <section id="relation" class="panel compact-panel">
      <div class="section-head">
        <h2>机构调研</h2>
        <span class="meta-badge strong">{total}条</span>
      </div>
      <div class="section-summary">保留表格形态，压缩为日期、公司、标题、操作四列。</div>
      <table class="detail-table relation-table">
        <thead>
          <tr><th>日期</th><th>公司</th><th>标题</th><th>操作</th></tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


def render_notice_panel(items):
    """Render compact notice section grouped by category and company."""
    category_order = {
        "重大合作": 0,
        "重大合作/投资项目": 0,
        "合作项目": 0,
        "投资项目": 0,
        "增持": 1,
        "增持股": 1,
        "大股东增持": 1,
        "减持": 1,
        "减持股": 1,
        "大股东减持": 1,
        "监管函": 2,
        "监管工作函": 2,
        "问询函": 2,
        "关注函": 2,
        "回复函": 3,
        "回复公告": 3,
        "资本运作": 4,
        "定向增发": 4,
        "增发": 4,
        "配股": 4,
        "可转债": 4,
    }

    def is_regulatory(sub):
        return any(kw in sub for kw in ["监管", "问询", "关注函", "警示", "立案", "调查", "处罚"])

    def is_capital_operation(sub):
        return any(kw in sub for kw in ["资本运作", "增发", "定向", "配股", "可转债", "发行", "融资", "募投", "募资"])

    def should_exclude_item(item):
        title = (item.get("title") or "").strip()
        subcategory = (item.get("subcategory") or "").strip()

        if "增持" in subcategory or "减持" in subcategory:
            plan_keywords = ["预披露", "计划", "方案", "提示性公告", "拟减持", "拟增持"]
            progress_keywords = ["结果", "完成", "完毕", "实施完成", "期限届满", "进展", "实施进展", "减持进展", "增持进展", "触及1%", "触及5%", "达到1%", "达到5%", "权益变动", "简式权益变动", "详式权益变动", "提前终止", "终止", "届满暨实施"]
            if any(kw in title for kw in progress_keywords):
                return True
            if not any(kw in title for kw in plan_keywords):
                return True

        if is_capital_operation(subcategory):
            intermediary_keywords = ["核查意见", "保荐机构", "保荐人", "发行保荐书", "上市保荐书", "主办券商", "独立财务顾问", "法律意见书", "律师", "律师事务所", "审计报告", "验资报告", "验资", "验证报告", "会计师", "会计师事务所", "合规性报告", "合规性之法律意见", "发行过程和认购对象合规性", "信用评级报告", "评级报告", "资信评级"]
            if any(kw in title for kw in intermediary_keywords):
                return True

        trivial_capital_keywords = ["调整募集资金投资项目内部结构", "调整募投项目", "募集资金专户存储", "募集资金三方监管", "募集资金置换", "闲置募集资金现金管理", "募集资金临时补充流动资金", "募集资金归还"]
        if any(kw in title for kw in trivial_capital_keywords):
            return True

        if "员工持股" in subcategory or "员工持股" in title:
            if not any(kw in title for kw in ["预案", "计划草案", "计划摘要"]):
                return True

        if "回复" in subcategory or "回复" in title:
            if any(kw in title for kw in ["核查意见", "保荐机构", "保荐人", "主办券商", "独立财务顾问", "会计师回复", "律师回复", "中介机构"]):
                return True

        return False

    grouped = defaultdict(lambda: defaultdict(list))
    excluded_count = 0
    for item in items or []:
        sub = (item.get("subcategory") or "").strip()
        if not sub or is_other_subcategory(sub) or is_excluded_subcategory(sub):
            continue
        if should_exclude_item(item):
            excluded_count += 1
            continue
        company = (item.get("company") or "").strip() or (item.get("symbol") or "").strip() or "未知公司"
        grouped[sub][company].append(item)

    def get_sort_key(entry):
        subcategory = entry[0]
        total_count = sum(len(v) for v in entry[1].values())
        return (category_order.get(subcategory, 999), -total_count, subcategory)

    blocks = []
    for idx, (subcategory, company_map) in enumerate(sorted(grouped.items(), key=get_sort_key)):
        block_id = f"notice-{idx}"
        total_count = sum(len(v) for v in company_map.values())
        is_regulatory_cat = is_regulatory(subcategory)
        is_capital_cat = is_capital_operation(subcategory)
        header_note = "监管类优先关注" if is_regulatory_cat else ("资本运作按公司聚合" if is_capital_cat else "默认展示前 5 个公司项")

        ordered_companies = sorted(company_map.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        company_rows = []
        for company, company_items in ordered_companies[:5]:
            symbol = next((x.get("symbol") for x in company_items if x.get("symbol")), "")
            latest_url = next((x.get("url") for x in company_items if x.get("url")), "")
            link_html = f"<a href='{fmt(latest_url)}' target='_blank'>原文</a>" if latest_url else ""
            titles = [clip_text((x.get("title") or "").strip(), 56) for x in company_items[:3]]
            preview = "；".join([t for t in titles if t]) or "暂无标题"
            row_class = "notice-company-row regulatory" if is_regulatory_cat else "notice-company-row"
            company_rows.append(
                f"""
            <div class="{row_class}">
              <div class="notice-company-main">
                <span class="accordion-title">{fmt(company)}</span>
                <span class="meta-badge">{fmt(symbol)}</span>
                <span class="meta-badge strong">{len(company_items)}条</span>
              </div>
              <div class="notice-company-text">{fmt(preview)}</div>
              <div class="notice-company-link">{link_html}</div>
            </div>
            """
            )

        extra_count = max(0, len(ordered_companies) - 5)
        extra_html = f"<div class='section-footnote'>另有 {extra_count} 家公司未展开</div>" if extra_count else ""
        blocks.append(
            f"""
        <article class="accordion-block notice-block{' regulatory-warning' if is_regulatory_cat else ''}" id="{block_id}">
          <button class="accordion-trigger" type="button" data-target="{block_id}-body" aria-expanded="false">
            <span class="accordion-main">
              <span class="accordion-title">{fmt(subcategory)}</span>
              <span class="meta-badge strong">{total_count}条</span>
            </span>
            <span class="accordion-summary">{fmt(header_note)}</span>
            <span class="accordion-icon" aria-hidden="true">&#9662;</span>
          </button>
          <div class="accordion-body collapsed" id="{block_id}-body">
            <div class="company-list">
              {''.join(company_rows) or "<div class='empty'>暂无公告数据</div>"}
            </div>
            {extra_html}
          </div>
        </article>
        """
        )

    total = sum(len(v) for companies in grouped.values() for v in companies.values())
    filtered_info = f"已过滤 {excluded_count} 条低价值公告" if excluded_count > 0 else "按分类和公司聚合展示"
    return f"""
    <section id="notice" class="panel compact-panel">
      <div class="section-head">
        <h2>公告解读</h2>
        <span class="meta-badge strong">{total}条</span>
      </div>
      <div class="section-summary">{fmt(filtered_info)}</div>
      <div class="accordion-list">
        {''.join(blocks) or "<div class='empty'>暂无公告解读数据</div>"}
      </div>
    </section>
    """


def load_tavily_news(out_dir: Path) -> dict:
    """加载新闻动态数据"""
    path = out_dir / "tavily_news.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def render_news_section(data: dict) -> str:
    """Render compact news buckets with summary-first accordion."""
    if not data or not data.get("categories"):
        return '<section id="news" class="panel compact-panel"><div class="section-head"><h2>新闻动态</h2></div><div class="empty">暂无新闻数据</div></section>'

    categories = data.get("categories", {})
    name_mapping = {
        "AI Industry": "AI产业",
        "Macro": "宏观",
        "Robotics": "机器人",
        "Commercial Space": "商业航天",
    }

    bucket_cards = []
    for idx, (bucket, cat_data) in enumerate(categories.items()):
        bucket_id = f"news-{idx}"
        cn_name = name_mapping.get(bucket, bucket)
        summary = cat_data.get("summary", "暂无总结")
        items = cat_data.get("items", [])
        count = cat_data.get("count", 0)
        teaser = first_sentence(summary, limit=88)
        expanded = False

        news_items_html = []
        for i, item in enumerate(items):
            headline = html.escape(item.get("headline", "N/A"))
            url = item.get("url", "")
            url_html = f"<a href='{html.escape(url)}' target='_blank'>原文</a>" if url else ""
            score = item.get("score", 0)
            news_items_html.append(
                f"""
            <div class="news-item">
              <span class="news-index">{i + 1}</span>
              <span class="news-headline">{headline}</span>
              <span class="news-score">{score:.2f}</span>
              {url_html}
            </div>
            """
            )

        bucket_cards.append(
            f"""
        <article class="accordion-block news-block" id="{bucket_id}">
          <button class="accordion-trigger" type="button" data-target="{bucket_id}-body" aria-expanded="{'true' if expanded else 'false'}">
            <span class="accordion-main">
              <span class="accordion-title">{fmt(cn_name)}</span>
              <span class="meta-badge strong">{count}条</span>
            </span>
            <span class="accordion-summary">{fmt(teaser)}</span>
            <span class="accordion-icon{' is-open' if expanded else ''}" aria-hidden="true">&#9662;</span>
          </button>
          <div class="accordion-body{' open' if expanded else ' collapsed'}" id="{bucket_id}-body">
            <div class="inline-summary">
              <span class="inline-summary-label">AI</span>
              <div class="inline-summary-text clamp-3">{fmt(summary)}</div>
            </div>
            <div class="news-list">
              {''.join(news_items_html) or "<div class='empty'>暂无新闻</div>"}
            </div>
          </div>
        </article>
        """
        )

    total_count = sum(c.get("count", 0) for c in categories.values())
    return f"""
    <section id="news" class="panel compact-panel">
      <div class="section-head">
        <h2>新闻动态</h2>
        <span class="meta-badge strong">{len(categories)}类 / {total_count}条</span>
      </div>
      <div class="section-summary">按主题聚合，默认展开首个分类，其余保留单行 AI 摘要。</div>
      <div class="accordion-list">
        {''.join(bucket_cards) or "<div class='empty'>暂无新闻动态数据</div>"}
      </div>
    </section>
    """


def load_forecast_from_akshare(date):
    """使用 akshare 获取业绩预告数据"""
    try:
        import akshare as ak
        
        # 将日期转换为报告期格式 (YYYY-MM-DD -> YYYYMMDD)
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        # 获取最近一个报告期（季度末）
        year = date_obj.year
        month = date_obj.month
        
        # 确定最近的报告期
        if month <= 3:
            report_date = f"{year}0331"
        elif month <= 6:
            report_date = f"{year}0630"
        elif month <= 9:
            report_date = f"{year}0930"
        else:
            report_date = f"{year}1231"
        
        # 获取业绩预告数据
        df = ak.stock_yjyg_em(date=report_date)
        
        if df is None or df.empty:
            return []
        
        # 转换为标准格式
        items = []
        for _, row in df.iterrows():
            item = {
                "date": date,
                "symbol": str(row.get("股票代码", "")).strip(),
                "company": str(row.get("股票简称", "")).strip(),
                "forecast_type": str(row.get("预测指标", "")).strip(),
                "performance_change": str(row.get("业绩变动", "")).strip(),
                "forecast_value": str(row.get("预测数值", "")).strip(),
                "change_reason": str(row.get("业绩变动原因", "")).strip(),
                "title": f"{row.get('股票简称', '')} - {row.get('预测指标', '')}",
                "summary": f"业绩变动: {row.get('业绩变动', '')}, 预测值: {row.get('预测数值', '')}",
            }
            items.append(item)
        
        return items
    except Exception as e:
        print(f"从 akshare 获取业绩预告失败: {e}")
        return []


def render_report(date, base_dir):
    out_dir = base_dir / "output" / date
    summary = load_json(out_dir / "summary.json")

    cninfo_fulltext = load_json(out_dir / "cninfo_fulltext.json")
    cninfo_relation = load_json(out_dir / "cninfo_relation.json")
    p5w_interaction = load_json(out_dir / "p5w_interaction.json")
    tushare_forecast = load_json(out_dir / "tushare_forecast.json")
    tavily_news = load_tavily_news(out_dir)

    forecast_items = tushare_forecast.get("items") or []

    relation_items = cninfo_relation.get("items") or []
    interaction_items = p5w_interaction.get("items") or []
    notice_items = cninfo_fulltext.get("items") or []
    news_categories = tavily_news.get("categories") or {}
    news_total = sum(cat.get("count", 0) for cat in news_categories.values())

    tabs = [
        ("新闻动态", "news"),
        ("业绩预告", "forecast"),
        ("机构调研", "relation"),
        ("互动问答", "interaction"),
        ("公告解读", "notice"),
    ]
    tabs_html = "".join(f"<a class='tab' href='#{anchor}'>{label}</a>" for label, anchor in tabs)

    news_section = render_news_section(tavily_news)
    forecast_section = render_forecast_panel(forecast_items)
    relation_section = render_relation_section_with_ai(relation_items, limit=40)
    interaction_section = render_interaction_section_with_ai(interaction_items, limit=40)
    notice_section = render_notice_panel(notice_items)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    coverage_count = len([1 for dataset in [news_total, len(forecast_items), len(relation_items), len(interaction_items), len(notice_items)] if dataset])

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{fmt(date)} Alpha日报</title>
  <style>
    :root {{
      --bg: #eef1f5;
      --panel: #ffffff;
      --panel-soft: #f7f8fb;
      --line: #dde3eb;
      --line-strong: #cdd5df;
      --text: #161c24;
      --muted: #667085;
      --muted-2: #8a94a6;
      --accent: #ff6a00;
      --accent-soft: #fff2e8;
      --ai-bg: #f4f8ff;
      --ai-border: #d7e5ff;
      --shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
      --shadow-soft: 0 4px 12px rgba(15, 23, 42, 0.04);
      --warn-bg: #fff8ec;
      --warn-line: #ffd8a8;
    }}

    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; scroll-padding-top: 68px; }}
    body {{ margin: 0; background: linear-gradient(180deg, #f7f8fa 0%, var(--bg) 220px); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    a {{ color: #0b63ce; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    button {{ font: inherit; }}
    .wrap {{ max-width: 1440px; margin: 0 auto; padding: 16px 16px 32px; }}
    .report-header {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; padding: 4px 0 10px; border-bottom: 1px solid rgba(205,213,223,.75); }}
    .report-title-wrap {{ display: grid; gap: 6px; }}
    .report-kicker {{ display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
    .report-kicker::before {{ content: ''; width: 8px; height: 8px; border-radius: 999px; background: var(--accent); box-shadow: 0 0 0 4px rgba(255,106,0,.12); }}
    h1 {{ margin: 0; font-size: 24px; line-height: 1.1; }}
    .report-subtitle {{ color: var(--muted); font-size: 13px; }}
    .report-meta {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }}
    .meta-badge {{ display: inline-flex; align-items: center; gap: 6px; min-height: 24px; padding: 0 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel-soft); color: var(--muted); font-size: 12px; white-space: nowrap; }}
    .meta-badge.strong {{ background: var(--accent-soft); border-color: #ffd0b2; color: #ad4d00; font-weight: 600; }}
    .meta-badge.subtle {{ color: var(--muted-2); }}
    .tabs {{ display: flex; gap: 8px; margin-top: 12px; padding: 8px 0; position: sticky; top: 0; z-index: 20; overflow-x: auto; background: rgba(238,241,245,.92); backdrop-filter: blur(10px); }}
    .tabs::-webkit-scrollbar {{ display: none; }}
    .tab {{ display: inline-flex; align-items: center; height: 36px; padding: 0 14px; border: 1px solid var(--line); border-radius: 999px; background: rgba(255,255,255,.92); color: var(--muted); font-size: 13px; font-weight: 600; white-space: nowrap; }}
    .tab:hover {{ border-color: #ffc59b; color: #a74b00; background: #fff7f1; text-decoration: none; }}
    .content-grid {{ display: grid; grid-template-columns: 1fr; gap: 14px; margin-top: 14px; }}
    .panel {{ background: var(--panel); border: 1px solid rgba(221,227,235,.95); border-radius: 12px; box-shadow: var(--shadow); padding: 16px; }}
    .compact-panel {{ scroll-margin-top: 72px; }}
    .section-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }}
    h2 {{ margin: 0; font-size: 17px; line-height: 1.2; }}
    .section-summary {{ margin-bottom: 10px; color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .accordion-list {{ display: grid; gap: 10px; }}
    .accordion-block {{ border: 1px solid var(--line); border-radius: 10px; background: var(--panel-soft); overflow: hidden; }}
    .accordion-trigger {{ width: 100%; border: 0; padding: 11px 12px; background: transparent; display: grid; grid-template-columns: minmax(0, auto) minmax(0, 1fr) auto; align-items: center; gap: 10px; text-align: left; cursor: pointer; }}
    .accordion-main {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }}
    .accordion-title {{ font-size: 14px; font-weight: 700; color: var(--text); }}
    .accordion-summary {{ min-width: 0; color: var(--muted); font-size: 12px; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .accordion-icon {{ color: var(--muted-2); font-size: 12px; transition: transform .2s ease; }}
    .accordion-icon.is-open {{ transform: rotate(180deg); }}
    .accordion-body {{ border-top: 1px solid var(--line); padding: 12px; background: #fff; }}
    .accordion-body.collapsed {{ display: none; }}
    .accordion-body.open {{ display: block; }}
    .inline-summary {{ display: grid; grid-template-columns: auto 1fr; gap: 8px; align-items: start; padding: 10px 12px; margin-bottom: 10px; border: 1px solid var(--ai-border); border-radius: 10px; background: var(--ai-bg); }}
    .inline-summary-label {{ display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 22px; padding: 0 8px; border-radius: 999px; background: #fff; color: #2452b6; font-size: 11px; font-weight: 700; }}
    .inline-summary-text {{ color: var(--text); font-size: 13px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }}
    .clamp-3 {{ display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
    .detail-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .detail-table thead th {{ position: sticky; top: 68px; z-index: 5; background: #f7f8fb; color: var(--muted); font-size: 12px; font-weight: 600; text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line-strong); }}
    .detail-table td {{ padding: 9px 10px; border-bottom: 1px solid #edf1f5; vertical-align: top; line-height: 1.5; }}
    .detail-table tr:last-child td {{ border-bottom: 0; }}
    .detail-table td.title {{ max-width: 0; }}
    .detail-table tbody tr:hover td {{ background: #fbfcfd; }}
    .inline-symbol {{ color: var(--muted-2); font-size: 12px; margin-left: 6px; }}
    .action-group {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}

    .news-list {{ display: grid; gap: 2px; }}
    .news-item {{ display: grid; grid-template-columns: 20px minmax(0, 1fr) auto auto; gap: 8px; align-items: start; padding: 7px 0; border-bottom: 1px solid #edf1f5; font-size: 12px; }}
    .news-item:last-child {{ border-bottom: 0; }}
    .news-index {{ color: var(--muted-2); }}
    .news-headline {{ color: var(--text); line-height: 1.45; }}
    .news-score {{ display: inline-flex; align-items: center; height: 20px; padding: 0 6px; border-radius: 999px; background: #f0f3f6; color: var(--muted); font-size: 11px; }}
    .company-list {{ display: grid; gap: 8px; }}
    .notice-company-row {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) auto; gap: 10px; align-items: start; padding: 10px 0; border-bottom: 1px solid #edf1f5; }}
    .notice-company-row:last-child {{ border-bottom: 0; }}
    .notice-company-row.regulatory {{ padding-left: 10px; border-left: 3px solid #f59e0b; }}
    .notice-company-main {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .notice-company-text {{ color: var(--muted); font-size: 12px; line-height: 1.5; }}
    .notice-company-link {{ text-align: right; white-space: nowrap; }}
    .section-footnote {{ margin-top: 8px; color: var(--muted-2); font-size: 12px; }}
    .regulatory-warning {{ background: linear-gradient(180deg, var(--warn-bg), #fff); border-color: var(--warn-line); }}
    .empty {{ padding: 20px 14px; border: 1px dashed var(--line-strong); border-radius: 10px; background: #fafbfd; color: var(--muted-2); text-align: center; font-size: 13px; }}

    @media (max-width: 768px) {{
      .wrap {{ padding: 14px 12px 28px; }}
      .report-header {{ align-items: flex-start; flex-direction: column; }}
      .report-meta {{ justify-content: flex-start; }}
      h1 {{ font-size: 22px; }}
      .panel {{ padding: 14px; }}
      .accordion-trigger {{ grid-template-columns: 1fr auto; }}
      .accordion-summary {{ grid-column: 1 / -1; white-space: normal; }}
      .news-item {{ grid-template-columns: 20px minmax(0, 1fr); }}
      .notice-company-row {{ grid-template-columns: 1fr; }}
      .detail-table {{ display: block; overflow-x: auto; white-space: nowrap; }}
      .detail-table td.title, .detail-table th {{ white-space: normal; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <header class="report-header">
      <div class="report-title-wrap">
        <span class="report-kicker">Alpha Daily</span>
        <h1>{fmt(date)} Alpha日报</h1>
        <div class="report-subtitle">先总览后下钻：压缩空白，优先呈现高价值模块。</div>
      </div>
      <div class="report-meta">
        <span class="meta-badge">生成时间 {fmt(generated_at)}</span>
        <span class="meta-badge">数据覆盖 {coverage_count}/5</span>
        <span class="meta-badge strong">当日输出 {fmt(date)}</span>
      </div>
    </header>

    <nav class="tabs">{tabs_html}</nav>

    <section class="content-grid">
      {news_section}
      {forecast_section}
      {relation_section}
      {interaction_section}
      {notice_section}
    </section>
  </main>

  <script>
    function setAccordionState(trigger, expanded) {{
      const targetId = trigger.getAttribute('data-target');
      const body = document.getElementById(targetId);
      const icon = trigger.querySelector('.accordion-icon');
      if (!body) return;
      trigger.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      body.classList.toggle('collapsed', !expanded);
      body.classList.toggle('open', expanded);
      if (icon) icon.classList.toggle('is-open', expanded);
    }}

    function bindAccordions() {{
      document.querySelectorAll('.accordion-trigger').forEach((trigger) => {{
        trigger.addEventListener('click', () => {{
          const expanded = trigger.getAttribute('aria-expanded') === 'true';
          setAccordionState(trigger, !expanded);
        }});
      }});
    }}

    document.addEventListener('DOMContentLoaded', function() {{
      bindAccordions();
      document.querySelectorAll('.accordion-trigger').forEach((trigger) => {{
        setAccordionState(trigger, trigger.getAttribute('aria-expanded') === 'true');
      }});
    }});

  </script>
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
