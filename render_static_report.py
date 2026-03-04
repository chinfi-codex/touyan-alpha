#!/usr/bin/env python3
import argparse
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
    """为单个公司生成AI总结（20秒超时）"""
    if not items:
        return "暂无问答数据"
    
    # 准备数据
    content_parts = []
    for item in items[:8]:  # 限制前8条，减少处理时间
        question = item.get("title", "")
        answer = item.get("summary", "")
        if question:
            content_parts.append(f"问：{question[:60]}\n答：{answer[:80] if answer else '未回复'}")
    
    if not content_parts:
        return "暂无可总结内容"
    
    prompt_text = f"总结【{company_name}】的投资者问答要点（限40字）：\n" + "\n".join(content_parts[:4])
    
    try:
        import openai
        import concurrent.futures
        
        api_key = "7c45a349-5a95-4885-a7b6-df6ed599ed5e"
        base_url = "https://ark.cn-beijing.volces.com/api/v3"
        model_id = "ep-20260103112951-vxd7j"
        
        def _call_api():
            client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=25)
            completion = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "你是金融分析师，用简洁中文总结投资者问答的核心要点，控制在40字以内。"},
                    {"role": "user", "content": prompt_text},
                ],
                temperature=0,
                max_tokens=80,
            )
            if hasattr(completion, "choices") and completion.choices:
                return completion.choices[0].message.content.strip()
            return "AI总结失败"
        
        # 设置20秒超时
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_call_api)
            return future.result(timeout=20)
            
    except concurrent.futures.TimeoutError:
        return "AI总结超时"
    except Exception as e:
        return f"AI总结失败: {str(e)[:30]}"


def render_interaction_section_with_ai(items, limit=100):
    """渲染互动问答区域 - 按公司聚合，剔除股东数问题"""
    
    # 1. 剔除股东数相关问题
    filtered_items = []
    excluded_count = 0
    for item in (items or []):
        question = item.get("title", "")
        answer = item.get("summary", "")
        combined_text = f"{question} {answer}"
        
        if _is_shareholder_question(combined_text):
            excluded_count += 1
            continue
        filtered_items.append(item)
    
    # 2. 按公司聚合
    from collections import defaultdict
    companies = defaultdict(list)
    for item in filtered_items:
        company = item.get("company") or item.get("symbol") or "未知公司"
        companies[company].append(item)
    
    # 3. 为每个公司生成子区域
    company_cards = []
    for idx, (company_name, company_items) in enumerate(sorted(companies.items())):
        symbol = company_items[0].get("symbol", "")
        card_id = f"company-card-{idx}"
        
        # 生成公司AI总结（20秒超时）
        print(f"  生成AI总结: {company_name}...")
        ai_summary = generate_company_ai_summary(company_name, company_items)
        print(f"    完成: {ai_summary[:30]}...")
        
        # 生成该公司的问题列表（可展开）
        qa_rows = []
        for q_idx, item in enumerate(company_items[:20]):  # 每公司最多显示20条
            question = fmt(item.get("title"))
            answer = fmt(item.get("summary"))
            link = (item.get("url") or "").strip()
            link_html = f"<a href='{fmt(link)}' target='_blank'>link</a>" if link else ""
            
            qa_rows.append(
                f"<tr>"
                f"<td>{fmt(item.get('date'))}</td>"
                f"<td class='title'>{question}</td>"
                f"<td class='title'>{answer}</td>"
                f"<td>{link_html}</td>"
                f"</tr>"
            )
        
        qa_table = (
            "<table class='qa-table'><thead><tr><th>Date</th><th>Question</th><th>Answer</th><th>URL</th></tr></thead>"
            f"<tbody>{''.join(qa_rows)}</tbody></table>"
            if qa_rows else "<div class='empty'>无问答数据</div>"
        )
        
        # 超过5条显示计数
        more_count = len(company_items) - 20 if len(company_items) > 20 else 0
        more_hint = f"<span class='more-hint'>还有 {more_count} 条...</span>" if more_count > 0 else ""
        
        # AI总结处理换行
        ai_summary_html = html.escape(ai_summary).replace('\n', '<br>')
        
        company_cards.append(f"""
        <div class="company-interaction-card" id="{card_id}">
          <div class="company-header" onclick="toggleCompanyQa('{card_id}')">
            <div class="company-info">
              <span class="company-name">{fmt(company_name)}</span>
              <span class="company-symbol">{fmt(symbol)}</span>
              <span class="qa-count">({len(company_items)}条)</span>
              {more_hint}
            </div>
            <span class="toggle-icon" id="toggle-{card_id}">▼</span>
          </div>
          <div class="company-ai-summary">
            <span class="ai-tag">🤖 AI</span>
            <span class="ai-text">{ai_summary_html}</span>
          </div>
          <div class="company-qa-list" id="qa-{card_id}">
            {qa_table}
          </div>
        </div>
        """)
    
    total_companies = len(companies)
    total_filtered = len(filtered_items)
    
    return f"""
    <section id="interaction" class="panel">
      <h2>互动问答 <span>({total_companies}家公司, {total_filtered}条)</span></h2>
      
      <div class="interaction-companies">
        {''.join(company_cards) or "<div class='empty'>无互动问答数据</div>"}
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
    """使用豆包AI优化变动原因文本"""
    if not reason_text or len(reason_text) < 20:
        return reason_text
    
    try:
        import openai
        
        api_key = "7c45a349-5a95-4885-a7b6-df6ed599ed5e"
        base_url = "https://ark.cn-beijing.volces.com/api/v3"
        model_id = "ep-20260103112951-vxd7j"
        
        company_info = f"【{company_name}】" if company_name else ""
        prompt = f"""请对以下业绩预告变动原因进行简洁总结，要求：
1. 保留核心关键信息（业务增长原因、市场因素、政策影响等）
2. 去除重复和冗余表述
3. 控制在80字以内
4. 使用简洁专业的金融语言

{company_info}变动原因：
{reason_text[:500]}

请直接输出总结内容，不要添加任何前缀或解释："""
        
        messages = [
            {"role": "system", "content": "你是专业的金融分析师，擅长提炼和总结业绩预告的关键信息。"},
            {"role": "user", "content": prompt},
        ]
        
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        completion = client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=0,
            top_p=0.8,
            max_tokens=150,
        )
        
        if hasattr(completion, "choices") and completion.choices:
            result = completion.choices[0].message.content.strip()
            # 去除可能的引号
            result = result.strip('"').strip("'").strip()
            return result if result else reason_text[:100]
        return reason_text[:100]
    except Exception as e:
        # AI优化失败，返回原文截断版
        return reason_text[:100] + "..." if len(reason_text) > 100 else reason_text


def render_forecast_panel(items):
    """渲染业绩预告面板，按公司聚合"""
    # 按公司分组
    grouped = defaultdict(list)
    for item in items or []:
        company = (item.get("company") or "").strip() or (item.get("symbol") or "").strip() or "未识别公司"
        grouped[company].append(item)
    
    company_blocks = []
    for company, company_items in sorted(grouped.items()):
        # 获取公司代码
        symbol = ""
        for x in company_items:
            if x.get("symbol"):
                symbol = x.get("symbol")
                break
        
        # 收集该公司的所有预测指标
        metrics_rows = []
        seen_reasons = set()  # 用于去重变动原因
        all_reasons = []
        
        for item in company_items:
            forecast_type = item.get("forecast_type", "")
            performance_change = item.get("performance_change", "")
            forecast_value = item.get("forecast_value", "")
            change_reason = item.get("change_reason", "")
            
            if forecast_type and performance_change:
                metrics_rows.append(
                    f"<tr>"
                    f"<td>{fmt(forecast_type)}</td>"
                    f"<td class='title'>{fmt(performance_change)}</td>"
                    f"<td>{fmt(forecast_value)}</td>"
                    f"</tr>"
                )
            
            # 收集变动原因（去重）
            if change_reason and change_reason not in seen_reasons:
                seen_reasons.add(change_reason)
                all_reasons.append(change_reason)
        
        # 构建指标表格
        if metrics_rows:
            metrics_table = f"""
            <table class="forecast-metrics">
                <thead>
                    <tr><th>预测指标</th><th>业绩变动</th><th>预测数值</th></tr>
                </thead>
                <tbody>{''.join(metrics_rows)}</tbody>
            </table>
            """
        else:
            metrics_table = "<div class='empty'>无详细数据</div>"
        
        # 变动原因（使用AI优化）
        reasons_html = ""
        if all_reasons:
            reasons_combined = "；".join(all_reasons)
            # 使用AI优化变动原因
            optimized_reason = optimize_reason_with_ai(reasons_combined, company)
            reasons_html = f"<div class='forecast-reason'><strong>变动原因：</strong>{fmt(optimized_reason)}</div>"
        
        company_blocks.append(
            f"""
            <section class="subpanel forecast-company">
                <h3>{fmt(company)} <span>{fmt(symbol)}</span></h3>
                {metrics_table}
                {reasons_html}
            </section>
            """
        )
    
    if not company_blocks:
        company_blocks.append("<section class='subpanel'><div class='empty'>暂无业绩预告数据</div></section>")
    
    total_companies = len(grouped)
    total_items = len(items or [])
    return f"""
    <section class="panel">
        <h2>业绩预告 <span>({total_companies}家公司, {total_items}条)</span></h2>
        <div class="stack">
            {''.join(company_blocks)}
        </div>
    </section>
    """


def render_relation_section_with_ai(items, limit=40):
    """渲染机构调研区域，带AI解读按钮"""
    rows_html = []
    display_items = top_items(items, limit=limit)
    
    for idx, item in enumerate(display_items):
        row_id = f"relation-row-{idx}"
        symbol = fmt(item.get('symbol'))
        company = fmt(item.get('company'))
        date = fmt(item.get('date'))
        title = fmt(item.get('title'))
        url = (item.get('url') or "").strip()
        
        # 生成唯一的标识符用于AI解读
        item_key = f"{symbol}_{idx}"
        
        link_html = f"<a href='{fmt(url)}' target='_blank'>link</a>" if url else ""
        
        rows_html.append(
            f"<tr id='{row_id}'>"
            f"<td>{date}</td>"
            f"<td>{symbol}</td>"
            f"<td>{company}</td>"
            f"<td class='title'>{title}</td>"
            f"<td>{link_html}</td>"
            f"<td><button class='ai-analyze-btn' onclick='analyzeResearch(\"{item_key}\", \"{fmt(url)}\")' id='btn-{item_key}'>AI解读</button></td>"
            f"</tr>"
            f"<tr id='ai-result-{item_key}' class='ai-result-row' style='display:none;'>"
            f"<td colspan='6' class='ai-result-cell'>"
            f"<div class='ai-analyze-result' id='ai-content-{item_key}'>"
            f"<div class='ai-loading'><span class='ai-icon'>🤖</span> 正在分析PDF内容...</div>"
            f"</div></td></tr>"
        )
    
    body = "\n".join(rows_html) or "<tr><td colspan='6'>无数据</td></tr>"
    total = len(items or [])
    
    return f"""
    <section id="relation" class="panel">
      <h2>机构调研 <span>({total})</span></h2>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Symbol</th>
            <th>Company</th>
            <th>Title</th>
            <th>URL</th>
            <th>AI解读</th>
          </tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


def render_notice_panel(items):
    """渲染公告解读面板，按指定顺序和特殊样式展示"""
    # 定义分类排序权重（数字越小越靠前）
    # 顺序：重大合作/投资 > 增减持 > 监管函 > 回复函 > 资本运作
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
    
    # 判断是否为监管函类
    def is_regulatory(sub):
        regulatory_keywords = ["监管", "问询", "关注函", "警示", "立案", "调查", "处罚"]
        return any(kw in sub for kw in regulatory_keywords)
    
    # 判断是否为资本运作类
    def is_capital_operation(sub):
        capital_keywords = ["资本运作", "增发", "定向", "配股", "可转债", "发行", "融资", "募投", "募资"]
        return any(kw in sub for kw in capital_keywords)
    
    # 判断公告是否应被剔除（根据标题内容）
    def should_exclude_item(item):
        title = (item.get("title") or "").strip()
        subcategory = (item.get("subcategory") or "").strip()
        
        # 1. 增持/减持类：只保留预披露/计划类，剔除进度/结果类
        if "增持" in subcategory or "减持" in subcategory:
            # 只保留这些关键词
            plan_keywords = ["预披露", "计划", "方案", "提示性公告", "拟减持", "拟增持"]
            # 剔除这些关键词
            progress_keywords = [
                "结果", "完成", "完毕", "实施完成", "期限届满",
                "进展", "实施进展", "减持进展", "增持进展",
                "触及1%", "触及5%", "达到1%", "达到5%",
                "权益变动", "简式权益变动", "详式权益变动",
                "提前终止", "终止", "届满暨实施", "届满",
            ]
            
            # 如果包含进度关键词，剔除
            if any(kw in title for kw in progress_keywords):
                return True, "增减持非计划类"
            # 如果不包含计划关键词，也剔除
            if not any(kw in title for kw in plan_keywords):
                return True, "增减持非预披露"
        
        # 2. 资本运作类：剔除中介机构意见
        if is_capital_operation(subcategory) or "资本运作" in subcategory:
            # 剔除券商、律所、会计师等中介机构文件
            intermediary_keywords = [
                "核查意见",
                "保荐机构",
                "保荐人",
                "保荐书",
                "发行保荐书",
                "上市保荐书",
                "主办券商",
                "独立财务顾问",
                "法律意见书",
                "律师",
                "律师事务所",
                "审计报告",
                "验资报告",
                "验资",
                "验证报告",
                "会计师",
                "会计师事务所",
                "合规性报告",
                "合规性之法律意见",
                "发行过程和认购对象合规性",
                "信用评级报告",
                "评级报告",
                "资信评级",
            ]
            if any(kw in title for kw in intermediary_keywords):
                return True, "剔除中介机构文件"
        
        # 3. 剔除募集资金内部结构调整类公告（非重大事项）
        trivial_capital_keywords = [
            "调整募集资金投资项目内部结构",
            "调整募投项目",
            "募集资金专户存储",
            "募集资金三方监管",
            "募集资金置换",
            "闲置募集资金现金管理",
            "募集资金临时补充流动资金",
            "募集资金归还",
        ]
        for kw in trivial_capital_keywords:
            if kw in title:
                return True, f"剔除琐碎资金调整: {kw}"
        
        # 4. 员工持股计划只保留激励预案（剔除实施进展、解锁等）
        if "员工持股" in subcategory or "员工持股" in title:
            # 只保留预案类，剔除其他
            if not any(kw in title for kw in ["预案", "计划草案", "计划摘要"]):
                return True, "员工持股非预案类"
        
        # 5. 问询回复类剔除券商意见（保留监管机构和公司问答）
        if "回复" in subcategory or "回复" in title:
            # 剔除券商/保荐机构的核查意见
            if any(kw in title for kw in [
                "核查意见",
                "保荐机构",
                "保荐人",
                "主办券商",
                "独立财务顾问",
                "会计师回复",
                "律师回复",
                "中介机构",
            ]):
                return True, "剔除中介机构意见"
        
        return False, ""
    
    # 按分类分组
    grouped = defaultdict(lambda: defaultdict(list))
    excluded_count = 0
    for item in items or []:
        sub = (item.get("subcategory") or "").strip()
        if not sub or is_other_subcategory(sub) or is_excluded_subcategory(sub):
            continue
        
        # 应用新的过滤规则
        should_exclude, reason = should_exclude_item(item)
        if should_exclude:
            excluded_count += 1
            continue
        
        company = (item.get("company") or "").strip() or (item.get("symbol") or "").strip() or "未识别公司"
        grouped[sub][company].append(item)
    
    def get_sort_key(item):
        """获取排序键"""
        subcategory = item[0]
        # 先按权重排序，没有的放最后
        weight = category_order.get(subcategory, 999)
        # 再按总数排序（多的在前）
        total_count = sum(len(v) for v in item[1].values())
        return (weight, -total_count, subcategory)
    
    sub_blocks = []
    sorted_categories = sorted(grouped.items(), key=get_sort_key)
    
    for subcategory, company_map in sorted_categories:
        # 判断分类类型
        is_regulatory_cat = is_regulatory(subcategory)
        is_capital_cat = is_capital_operation(subcategory)
        
        # 监管函类添加警示样式
        warning_icon = "⚠️ " if is_regulatory_cat else ""
        subpanel_class = "subpanel regulatory-warning" if is_regulatory_cat else "subpanel"
        
        # 资本运作类：按公司聚合为子区域
        if is_capital_cat:
            company_cards = []
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
                
                # 收集所有标题
                all_titles = "<br>".join([f"• {fmt((x.get('title') or '').strip())}" for x in company_items[:5]])
                if len(company_items) > 5:
                    all_titles += f"<br>• ... 等共 {len(company_items)} 条公告"
                
                latest_url = ""
                for x in company_items:
                    if x.get("url"):
                        latest_url = x.get("url")
                        break
                link_html = f"<a href='{fmt(latest_url)}' target='_blank'>查看最新</a>" if latest_url else ""
                
                company_cards.append(
                    f"""
                    <div class="capital-company-card">
                        <div class="capital-company-header">
                            <span class="capital-company-name">{fmt(company)}</span>
                            <span class="capital-company-symbol">{fmt(symbol)}</span>
                            <span class="capital-count">({len(company_items)}条)</span>
                            {link_html}
                        </div>
                        <div class="capital-titles">{all_titles}</div>
                    </div>
                    """
                )
            
            body = "".join(company_cards) or "<div class='empty'>无数据</div>"
            sub_blocks.append(
                f"""
                <section class="{subpanel_class}">
                  <h3>{warning_icon}{fmt(subcategory)} <span>({sum(len(v) for v in company_map.values())})</span></h3>
                  <div class="capital-companies">
                    {body}
                  </div>
                </section>
                """
            )
        
        else:
            # 其他分类：保持表格形式
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
                
                # 监管函类行添加警示样式
                row_class = "regulatory-row" if is_regulatory_cat else ""
                rows.append(
                    f"<tr class='{row_class}'>"
                    f"<td>{fmt(company)}</td>"
                    f"<td>{fmt(symbol)}</td>"
                    f"<td>{len(company_items)}</td>"
                    f"<td class='title'>{fmt(sample_titles)}</td>"
                    f"<td>{link_html}</td>"
                    f"</tr>"
                )

            body = "\n".join(rows) or "<tr><td colspan='5'>无数据</td></tr>"
            sub_blocks.append(
                f"""
                <section class="{subpanel_class}">
                  <h3>{warning_icon}{fmt(subcategory)} <span>({sum(len(v) for v in company_map.values())})</span></h3>
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
        sub_blocks.append("<section class='subpanel'><h3>公告解读</h3><div class='empty'>无非「其他」公告</div></section>")

    total = sum(len(v) for companies in grouped.values() for v in companies.values())
    original_count = len([i for i in (items or []) if not is_other_subcategory((i.get("subcategory") or "").strip())])
    filtered_info = f" 已过滤{excluded_count}条次要公告" if excluded_count > 0 else ""
    
    return f"""
    <section class="panel">
      <h2>公告解读 <span>({total}条{filtered_info})</span></h2>
      <div class="stack">
        {''.join(sub_blocks)}
      </div>
    </section>
    """


def load_market_temperature(out_dir: Path) -> dict:
    """加载市场温度数据"""
    path = out_dir / "market_temperature.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_tavily_news(out_dir: Path) -> dict:
    """加载新闻动态数据"""
    path = out_dir / "tavily_news.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def render_kline_chart(div_id: str, data: dict, title: str) -> str:
    """渲染K线图表HTML"""
    if not data or not data.get('kline'):
        return f'<div class="chart-empty">暂无{title}数据</div>'
    
    kline = data['kline']
    dates = [k['date'] for k in kline]
    values = [[k['open'], k['close'], k['low'], k['high']] for k in kline]
    volumes = [k.get('volume', 0) or 0 for k in kline]
    
    current = data.get('current', 0)
    change_pct = data.get('change_pct', 0)
    change_class = 'up' if change_pct and change_pct > 0 else 'down' if change_pct and change_pct < 0 else ''
    change_sign = '+' if change_pct and change_pct > 0 else ''
    current_str = f"{current:.2f}" if isinstance(current, (int, float)) else str(current)
    change_pct_str = f"{change_pct:.2f}" if isinstance(change_pct, (int, float)) else "-"
    
    return f'''
    <div class="index-card">
      <div class="index-header">
        <span class="index-name">{title}</span>
        <span class="index-value {change_class}">{current_str}</span>
        <span class="index-change {change_class}">{change_sign}{change_pct_str}%</span>
      </div>
      <div id="{div_id}" class="kline-chart"></div>
    </div>
    <script>
    (function(){{
      var chart = echarts.init(document.getElementById('{div_id}'));
      var option = {{
        animation: false,
        grid: {{ top: 10, left: 40, right: 10, bottom: 20 }},
        xAxis: {{ 
          type: 'category', 
          data: {json.dumps(dates)},
          axisLine: {{ lineStyle: {{ color: '#dfe2ea' }} }},
          axisLabel: {{ show: false }},
          axisTick: {{ show: false }}
        }},
        yAxis: {{ 
          type: 'value', 
          scale: true,
          splitLine: {{ lineStyle: {{ color: '#f0f2f5' }} }},
          axisLine: {{ show: false }},
          axisLabel: {{ color: '#8b92a5', fontSize: 10 }}
        }},
        series: [{{
          type: 'candlestick',
          data: {json.dumps(values)},
          itemStyle: {{
            color: '#f24957',
            color0: '#13b77f',
            borderColor: '#f24957',
            borderColor0: '#13b77f'
          }}
        }}]
      }};
      chart.setOption(option);
    }})();
    </script>
    '''


def render_sentiment_radar(div_id: str, data: dict) -> str:
    """渲染情绪雷达图"""
    if not data:
        return '<div class="chart-empty">暂无情绪数据</div>'
    
    indicators = [
        {{'name': '涨跌广度', 'max': 100}},
        {{'name': '涨停强度', 'max': 100}},
        {{'name': '一致性', 'max': 100}},
        {{'name': '量能配合', 'max': 100}},
        {{'name': '资金态度', 'max': 100}},
    ]
    values = [
        data.get('breadth', 50),
        data.get('intensity', 50),
        data.get('consistency', 50),
        data.get('volume', 50),
        data.get('northbound', 50),
    ]
    
    # 计算综合得分
    avg_score = round(sum(values) / len(values), 1)
    
    # 情绪标签
    if avg_score >= 70:
        mood_label, mood_class = '🔥 积极', 'up'
    elif avg_score >= 50:
        mood_label, mood_class = '⚖️ 中性', ''
    else:
        mood_label, mood_class = '❄️ 谨慎', 'down'
    
    return f'''
    <div class="sentiment-card">
      <div class="sentiment-header">
        <span class="sentiment-title">市场情绪</span>
        <span class="sentiment-score {mood_class}">{avg_score}分 {mood_label}</span>
      </div>
      <div id="{div_id}" class="radar-chart"></div>
    </div>
    <script>
    (function(){{
      var chart = echarts.init(document.getElementById('{div_id}'));
      var option = {{
        animation: false,
        radar: {{
          indicator: {json.dumps(indicators)},
          radius: '65%',
          axisName: {{ color: '#586171', fontSize: 11 }},
          splitArea: {{
            areaStyle: {{
              color: ['#fff', '#fafafc', '#f5f6fa', '#f0f2f5']
            }}
          }},
          axisLine: {{ lineStyle: {{ color: '#dfe2ea' }} }},
          splitLine: {{ lineStyle: {{ color: '#dfe2ea' }} }}
        }},
        series: [{{
          type: 'radar',
          data: [{{
            value: {json.dumps(values)},
            name: '今日情绪',
            areaStyle: {{ color: 'rgba(255, 102, 0, 0.2)' }},
            lineStyle: {{ color: '#ff6600', width: 2 }},
            itemStyle: {{ color: '#ff6600' }}
          }}]
        }}]
      }};
      chart.setOption(option);
    }})();
    </script>
    '''


def render_market_temperature_section(data: dict) -> str:
    """渲染市场温度板块"""
    if not data:
        return '<section id="market" class="panel"><h2>🌡️ 市场温度</h2><div class="empty">暂无市场数据</div></section>'
    
    indices = data.get('indices', {})
    snapshot = data.get('snapshot', {})
    radar = data.get('sentiment_radar', {})
    
    # 指数K线
    sh_chart = render_kline_chart('kline-sh', indices.get('sh'), '上证指数') if indices.get('sh') else ''
    cyb_chart = render_kline_chart('kline-cyb', indices.get('cyb'), '创业板指') if indices.get('cyb') else ''
    
    # 关键数据
    up_count = snapshot.get('up_count', '-')
    down_count = snapshot.get('down_count', '-')
    limit_up = snapshot.get('limit_up', '-')
    limit_down = snapshot.get('limit_down', '-')
    turnover = snapshot.get('turnover', '-')
    turnover_change = snapshot.get('turnover_change')
    
    turnover_change_str = f"+{turnover_change}%" if turnover_change and turnover_change > 0 else f"{turnover_change}%" if turnover_change else ''
    turnover_change_class = 'up' if turnover_change and turnover_change > 0 else 'down' if turnover_change and turnover_change < 0 else ''
    
    # 雷达图
    radar_chart = render_sentiment_radar('sentiment-radar', radar)
    
    return f'''
    <section id="market" class="panel">
      <h2>🌡️ 市场温度</h2>
      
      <!-- 指数K线区 -->
      <div class="market-indices">
        {sh_chart}
        {cyb_chart}
      </div>
      
      <!-- 关键数据条 -->
      <div class="market-snapshot">
        <div class="snapshot-item">
          <span class="snapshot-label">涨跌比</span>
          <span class="snapshot-value up">{up_count}</span>
          <span class="snapshot-separator">:</span>
          <span class="snapshot-value down">{down_count}</span>
        </div>
        <div class="snapshot-item">
          <span class="snapshot-label">涨停</span>
          <span class="snapshot-value up">{limit_up}</span>
        </div>
        <div class="snapshot-item">
          <span class="snapshot-label">跌停</span>
          <span class="snapshot-value down">{limit_down}</span>
        </div>
        <div class="snapshot-item">
          <span class="snapshot-label">成交额</span>
          <span class="snapshot-value">{turnover}亿</span>
          <span class="snapshot-change {turnover_change_class}">{turnover_change_str}</span>
        </div>
      </div>
      
      <!-- 情绪雷达 -->
      {radar_chart}
    </section>
    '''


def render_news_section(data: dict) -> str:
    """渲染新闻动态板块 - 按分类聚合展示"""
    if not data or not data.get('categories'):
        return '<section id="news" class="panel"><h2>📰 新闻动态</h2><div class="empty">暂无新闻数据</div></section>'
    
    categories = data.get('categories', {})
    
    # 分类名称映射（中文）
    name_mapping = {
        'AI Industry': 'AI产业',
        'Macro': '宏观',
        'Robotics': '机器人',
        'Commercial Space': '商业航天'
    }
    
    bucket_cards = []
    for idx, (bucket, cat_data) in enumerate(categories.items()):
        bucket_id = f"news-bucket-{idx}"
        cn_name = name_mapping.get(bucket, bucket)
        summary = cat_data.get('summary', '暂无总结')
        items = cat_data.get('items', [])
        count = cat_data.get('count', 0)
        
        # 生成新闻列表
        news_items_html = []
        for i, item in enumerate(items):
            headline = html.escape(item.get('headline', 'N/A'))
            url = item.get('url', '')
            url_html = f"<a href='{html.escape(url)}' target='_blank'>link</a>" if url else ""
            score = item.get('score', 0)
            
            news_items_html.append(f"""
            <div class="news-item">
              <span class="news-index">{i+1}.</span>
              <span class="news-headline">{headline}</span>
              <span class="news-score">{score:.2f}</span>
              {url_html}
            </div>
            """)
        
        bucket_cards.append(f"""
        <div class="news-bucket-card" id="{bucket_id}">
          <div class="bucket-header" onclick="toggleNewsBucket('{bucket_id}')">
            <div class="bucket-info">
              <span class="bucket-name">{cn_name}</span>
              <span class="bucket-count">({count}条)</span>
            </div>
            <span class="toggle-icon" id="toggle-{bucket_id}">▶</span>
          </div>
          <div class="bucket-summary">
            <span class="ai-tag">🤖 AI</span>
            <span class="ai-text">{html.escape(summary)}</span>
          </div>
          <div class="bucket-news-list collapsed" id="list-{bucket_id}">
            {''.join(news_items_html) or "<div class='empty'>暂无新闻</div>"}
          </div>
        </div>
        """)
    
    total_count = sum(c.get('count', 0) for c in categories.values())
    
    return f"""
    <section id="news" class="panel">
      <h2>📰 新闻动态 <span>({len(categories)}个分类, {total_count}条)</span></h2>
      
      <div class="news-buckets">
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
    market_temperature = load_market_temperature(out_dir)
    tavily_news = load_tavily_news(out_dir)
    
    # 尝试从 akshare 获取业绩预告
    akshare_forecast = load_forecast_from_akshare(date)
    if akshare_forecast:
        forecast_items = akshare_forecast
    else:
        # 回退到本地数据
        forecast_items = tushare_forecast.get("items") or []

    # 分类 Tab 导航（点击可滑动到对应区域）
    # 顺序：市场温度 -> 业绩预告 -> 机构调研 -> 互动问答 -> 公告解读
    tabs = [
        ("🌡️ 市场温度", "market"),
        ("📰 新闻动态", "news"),
        ("业绩预告", "forecast"),
        ("机构调研", "relation"),
        ("互动问答", "interaction"),
        ("公告解读", "notice"),
    ]

    tabs_html = "".join(
        f"""<a class="tab" href="#{anchor}">{label}</a>"""
        for label, anchor in tabs
    )

    # 渲染市场温度板块
    market_section = render_market_temperature_section(market_temperature)
    
    # 渲染新闻动态板块
    news_section = render_news_section(tavily_news)
    
    # 使用新的聚合方式渲染业绩预告
    forecast_section = f'<section id="forecast">{render_forecast_panel(forecast_items)}</section>'

    # 机构调研使用自定义渲染，添加AI解读按钮
    relation_section = render_relation_section_with_ai(cninfo_relation.get("items") or [], limit=40)

    # 互动问答区域（带AI总结）
    interaction_section = render_interaction_section_with_ai(
        p5w_interaction.get("items") or [], limit=40
    )

    notice_section = f'<section id="notice">{render_notice_panel(cninfo_fulltext.get("items") or [])}</section>'

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{fmt(date)} Alpha日报</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <style>
    /* ============================================
       Modern Bright UI - "Moomoo Style"
       ============================================ */
    :root {{
      /* Background */
      --bg-primary: #ffffff;
      --bg-secondary: #f4f5f9;
      --bg-tertiary: #ffffff;
      --bg-hover: #f0f2f5;
      
      /* Text */
      --text-primary: #12161b;
      --text-secondary: #586171;
      --text-tertiary: #8b92a5;
      --text-inverse: #ffffff;
      
      /* Borders & Shadows */
      --border-light: #eaecf1;
      --border-medium: #dfe2ea;
      --border-dark: #c4c8d4;
      --shadow-card: 0 4px 16px rgba(0, 0, 0, 0.04);
      --shadow-hover: 0 6px 24px rgba(0, 0, 0, 0.08);
      
      /* Financial Colors (A-shares: Red Up, Green Down) */
      --color-up: #f24957;           /* Moomoo Red */
      --color-up-bg: rgba(242, 73, 87, 0.08);
      --color-down: #13b77f;         /* Moomoo Green */
      --color-down-bg: rgba(19, 183, 127, 0.08);
      --color-warning: #ff8f00;      /* Orange */
      --color-info: #0066ff;         /* Bright Blue */
      
      /* Accents */
      --accent-primary: #ff6600;     /* Moomoo Brand Orange */
      --accent-hover: #ff8533;
      --accent-gradient: linear-gradient(135deg, #ff6600, #ff8f00);
      
      /* AI */
      --ai-bg: #f5f9ff;
      --ai-border: #d6e8ff;
      --ai-text: #0055ff;
    }}
    
    * {{ box-sizing: border-box; }}
    
    html {{
      scroll-behavior: smooth;
      scroll-padding-top: 80px;
    }}
    
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: var(--text-primary);
      background: var(--bg-secondary);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}
    
    .wrap {{ 
      max-width: 1400px; 
      margin: 0 auto; 
      padding: 24px 24px 60px; 
    }}
    
    h1, h2, h3 {{ 
      margin: 0; 
      font-weight: 700;
    }}
    
    h1 {{
      font-size: 28px;
      color: var(--text-primary);
      padding-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    
    h1::before {{
      content: '';
      display: inline-block;
      width: 6px;
      height: 28px;
      background: var(--accent-gradient);
      border-radius: 4px;
    }}
    
    /* ============================================
       Tabs - Modern Pill shapes
       ============================================ */
    .tabs {{ 
      display: flex; 
      gap: 12px; 
      margin-top: 20px; 
      padding: 12px 0; 
      position: sticky; 
      top: 0; 
      background: rgba(244, 245, 249, 0.9); 
      backdrop-filter: blur(12px); 
      -webkit-backdrop-filter: blur(12px);
      z-index: 100;
      overflow-x: auto;
      scrollbar-width: none;
    }}
    .tabs::-webkit-scrollbar {{ display: none; }}
    
    .tab {{ 
      padding: 10px 24px; 
      border-radius: 20px; 
      background: var(--bg-primary); 
      border: 1px solid var(--border-light); 
      color: var(--text-secondary); 
      text-decoration: none; 
      font-size: 15px; 
      font-weight: 600; 
      transition: all 0.2s ease;
      white-space: nowrap;
      box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }}
    .tab:hover {{ 
      color: var(--accent-primary);
      border-color: var(--accent-primary);
      background: #fff8f5;
    }}
    
    /* ============================================
       Panels - Clean White Cards
       ============================================ */
    .sections {{ 
      margin-top: 24px; 
      display: grid; 
      gap: 24px; 
    }}
    
    .panel {{ 
      background: var(--bg-primary);
      border-radius: 16px;
      padding: 28px;
      box-shadow: var(--shadow-card);
      border: 1px solid var(--border-light);
    }}
    
    .panel h2 {{ 
      margin-bottom: 20px;
      font-size: 20px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    
    .panel h2 span {{ 
      color: var(--accent-primary); 
      font-weight: 600; 
      font-size: 14px;
      background: #fff0e5;
      padding: 4px 12px;
      border-radius: 20px;
    }}
    
    .stack {{ 
      display: grid; 
      gap: 16px; 
    }}
    
    .subpanel {{ 
      background: #fafafc;
      border-radius: 12px;
      padding: 20px;
      border: 1px solid var(--border-light);
      transition: all 0.2s ease;
    }}
    
    .subpanel:hover {{
      background: #ffffff;
      box-shadow: var(--shadow-hover);
      border-color: var(--border-medium);
    }}
    
    .subpanel h3 {{ 
      margin-bottom: 16px;
      font-size: 16px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    
    .subpanel h3 span {{ 
      color: var(--text-tertiary); 
      font-weight: 500; 
      font-size: 13px;
    }}
    
    /* ============================================
       Tables - Crisp and Readable
       ============================================ */
    table {{ 
      width: 100%; 
      border-collapse: separate;
      border-spacing: 0;
      font-size: 14px;
    }}
    
    thead {{
      position: sticky;
      top: 60px;
      z-index: 50;
      background: var(--bg-primary);
    }}
    
    th {{ 
      color: var(--text-secondary); 
      font-weight: 500; 
      font-size: 13px;
      padding: 14px 12px;
      text-align: left;
      border-bottom: 1px solid var(--border-medium);
      background: #fafafc;
      border-radius: 0;
    }}
    
    .panel > table th:first-child {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
    .panel > table th:last-child {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
    
    td {{ 
      padding: 16px 12px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--border-light);
      transition: background-color 0.2s ease;
      line-height: 1.6;
    }}
    
    tbody tr:hover td {{
      background-color: var(--bg-hover);
    }}
    
    td.title {{ 
      min-width: 260px;
      max-width: 500px;
      color: var(--text-primary);
    }}
    
    /* ============================================
       Links & Buttons - Brand Accent
       ============================================ */
    a {{ 
      color: var(--color-info); 
      text-decoration: none;
      font-weight: 500;
      transition: all 0.2s;
    }}
    
    a:hover {{ 
      color: #0044cc;
      text-decoration: underline;
    }}
    
    .empty {{ 
      color: var(--text-tertiary); 
      font-size: 14px;
      text-align: center;
      padding: 40px 20px;
      background: #fafafc;
      border-radius: 12px;
      border: 1px dashed var(--border-medium);
    }}
    
    /* ============================================
       AI Summary Card - Crisp Tech Vibe
       ============================================ */
    .ai-summary-card {{
      background: var(--ai-bg);
      border: 1px solid var(--ai-border);
      border-radius: 12px;
      padding: 20px;
      margin: 16px 0;
    }}
    
    .ai-summary-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }}
    
    .ai-icon {{
      font-size: 20px;
    }}
    
    .ai-title {{
      font-weight: 700;
      color: var(--ai-text);
      font-size: 15px;
    }}
    
    .ai-summary-content {{
      color: var(--text-primary);
      font-size: 14px;
      line-height: 1.7;
    }}
    
    /* ============================================
       Forecast Section - Dynamic Cards
       ============================================ */
    .forecast-company {{
      background: var(--bg-primary);
      border: 1px solid var(--border-light);
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    }}
    
    .forecast-company h3 {{
      font-size: 17px;
      color: var(--text-primary);
    }}
    
    .forecast-company h3 span {{
      background: #f0f2f5;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 12px;
      color: var(--text-secondary);
    }}
    
    .forecast-metrics {{
      width: 100%;
      margin: 16px 0;
      border: 1px solid var(--border-light);
      border-radius: 8px;
    }}
    
    .forecast-metrics th:first-child {{
      border-top-left-radius: 8px;
    }}
    .forecast-metrics th:last-child {{
      border-top-right-radius: 8px;
    }}
    
    .forecast-metrics th {{
      background: #fafafc;
      border-bottom: 1px solid var(--border-light);
    }}
    
    .forecast-metrics td {{
      border-bottom: 1px solid var(--border-light);
    }}
    
    .forecast-metrics tr:last-child td {{ border-bottom: none; }}
    
    .forecast-reason {{
      color: var(--text-secondary);
      font-size: 13.5px;
      padding: 14px 16px;
      background: #fafafc;
      border-radius: 8px;
      border-left: 3px solid var(--accent-primary);
    }}
    
    /* ============================================
       Buttons
       ============================================ */
    .ai-analyze-btn, .expand-btn {{
      padding: 8px 16px;
      border-radius: 6px;
      background: var(--ai-bg);
      color: var(--ai-text);
      border: 1px solid var(--ai-border);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }}
    
    .ai-analyze-btn:hover, .expand-btn:hover {{
      background: #e0edff;
    }}
    
    .expand-controls {{
      margin: 16px 0;
      text-align: right;
    }}
    
    .expand-btn {{
      background: var(--accent-primary);
      border: none;
      color: #fff;
    }}
    
    .expand-btn:hover {{
      background: var(--accent-hover);
    }}
    
    /* ============================================
       Market Temperature Section
       ============================================ */
    .market-indices {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 20px;
      margin-bottom: 20px;
    }}
    
    .index-card {{
      background: #fafafc;
      border-radius: 12px;
      padding: 16px;
      border: 1px solid var(--border-light);
    }}
    
    .index-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    
    .index-name {{
      font-weight: 600;
      font-size: 14px;
      color: var(--text-secondary);
    }}
    
    .index-value {{
      font-size: 22px;
      font-weight: 700;
      color: var(--text-primary);
    }}
    
    .index-value.up {{ color: var(--color-up); }}
    .index-value.down {{ color: var(--color-down); }}
    
    .index-change {{
      font-size: 13px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 4px;
      background: #f0f2f5;
    }}
    
    .index-change.up {{ 
      color: var(--color-up); 
      background: var(--color-up-bg);
    }}
    .index-change.down {{ 
      color: var(--color-down); 
      background: var(--color-down-bg);
    }}
    
    .kline-chart {{
      height: 160px;
      width: 100%;
    }}
    
    .market-snapshot {{
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 32px;
      padding: 16px 24px;
      background: #fafafc;
      border-radius: 12px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}
    
    .snapshot-item {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    
    .snapshot-label {{
      font-size: 13px;
      color: var(--text-secondary);
    }}
    
    .snapshot-value {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text-primary);
    }}
    
    .snapshot-value.up {{ color: var(--color-up); }}
    .snapshot-value.down {{ color: var(--color-down); }}
    
    .snapshot-separator {{
      font-size: 14px;
      color: var(--text-tertiary);
      margin: 0 2px;
    }}
    
    .snapshot-change {{
      font-size: 12px;
      margin-left: 4px;
    }}
    
    .snapshot-change.up {{ color: var(--color-up); }}
    .snapshot-change.down {{ color: var(--color-down); }}
    
    .sentiment-card {{
      background: #fafafc;
      border-radius: 12px;
      padding: 16px;
      border: 1px solid var(--border-light);
    }}
    
    .sentiment-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }}
    
    .sentiment-title {{
      font-weight: 600;
      font-size: 14px;
      color: var(--text-secondary);
    }}
    
    .sentiment-score {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text-primary);
    }}
    
    .sentiment-score.up {{ color: var(--color-up); }}
    .sentiment-score.down {{ color: var(--color-down); }}
    
    .radar-chart {{
      height: 220px;
      width: 100%;
    }}
    
    .chart-empty {{
      padding: 40px;
      text-align: center;
      color: var(--text-tertiary);
      background: #fafafc;
      border-radius: 12px;
      font-size: 14px;
    }}
    
    @media (max-width: 768px) {{
      .market-indices {{
        grid-template-columns: 1fr;
      }}
      .market-snapshot {{
        gap: 16px;
        padding: 12px 16px;
      }}
      .snapshot-item {{
        flex: 1 1 40%;
        justify-content: center;
      }}
    }}
    
    /* ============================================
       Interaction Section - Company Aggregated
       ============================================ */
    .interaction-companies {{
      display: grid;
      gap: 16px;
    }}
    
    .company-interaction-card {{
      background: #ffffff;
      border: 1px solid var(--border-light);
      border-radius: 12px;
      overflow: hidden;
      transition: all 0.2s ease;
    }}
    
    .company-interaction-card:hover {{
      border-color: var(--border-medium);
      box-shadow: var(--shadow-hover);
    }}
    
    .company-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 20px;
      background: #fafafc;
      cursor: pointer;
      user-select: none;
      transition: background 0.2s;
    }}
    
    .company-header:hover {{
      background: #f0f2f5;
    }}
    
    .company-info {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    
    .company-name {{
      font-weight: 600;
      font-size: 15px;
      color: var(--text-primary);
    }}
    
    .company-symbol {{
      font-size: 12px;
      color: var(--text-secondary);
      background: #e8eaed;
      padding: 2px 8px;
      border-radius: 4px;
    }}
    
    .qa-count {{
      font-size: 13px;
      color: var(--accent-primary);
      font-weight: 500;
    }}
    
    .more-hint {{
      font-size: 12px;
      color: var(--text-tertiary);
    }}
    
    .toggle-icon {{
      font-size: 12px;
      color: var(--text-tertiary);
      transition: transform 0.2s;
    }}
    
    .toggle-icon.collapsed {{
      transform: rotate(-90deg);
    }}
    
    .company-ai-summary {{
      padding: 12px 20px;
      background: var(--ai-bg);
      border-bottom: 1px solid var(--ai-border);
      display: flex;
      align-items: flex-start;
      gap: 10px;
    }}
    
    .ai-tag {{
      font-size: 12px;
      color: var(--ai-text);
      font-weight: 600;
      white-space: nowrap;
    }}
    
    .ai-text {{
      font-size: 13px;
      color: var(--text-secondary);
      line-height: 1.7;
      word-break: break-word;
      white-space: pre-wrap;
    }}
    
    .company-qa-list {{
      max-height: 500px;
      overflow-y: auto;
      overflow-x: hidden;
      transition: max-height 0.3s ease;
      border-top: 1px solid var(--border-light);
    }}
    
    .company-qa-list.collapsed {{
      max-height: 0;
      overflow: hidden;
    }}
    
    .company-qa-list .qa-table {{
      width: 100%;
      font-size: 13px;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    
    .company-qa-list .qa-table th {{
      background: #f0f2f5;
      padding: 10px 12px;
      font-weight: 600;
      font-size: 12px;
      color: var(--text-secondary);
      text-align: left;
      border-bottom: 2px solid var(--border-medium);
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    
    .company-qa-list .qa-table th:first-child {{
      width: 90px;
    }}
    
    .company-qa-list .qa-table th:nth-child(2) {{
      width: 35%;
    }}
    
    .company-qa-list .qa-table th:nth-child(3) {{
      width: 55%;
    }}
    
    .company-qa-list .qa-table th:last-child {{
      width: 60px;
      text-align: center;
    }}
    
    .company-qa-list .qa-table td {{
      padding: 12px;
      border-bottom: 1px solid #f0f2f5;
      vertical-align: top;
      background: #fff;
    }}
    
    .company-qa-list .qa-table td.title {{
      min-width: 200px;
      max-width: 400px;
      word-break: break-word;
    }}
    
    .company-qa-list .qa-table tr:hover td {{
      background: #fafafc;
    }}
    
    .company-qa-list .qa-table tr:last-child td {{
      border-bottom: none;
    }}
    
    @media (max-width: 768px) {{
      .company-header {{
        padding: 12px 16px;
      }}
      .company-ai-summary {{
        padding: 10px 16px;
      }}
      .company-qa-list .qa-table td {{
        padding: 10px;
      }}
    }}
    
    /* ============================================
       Regulatory Warning & Capital
       ============================================ */
    .regulatory-warning {{
      background: #fffcf5;
      border: 1px solid #ffd599;
    }}
    
    .regulatory-warning h3 {{
      color: var(--color-warning);
    }}
    
    .regulatory-row td {{
      background: #fffcf5;
    }}
    
    .regulatory-row td:first-child {{
      border-left: 3px solid var(--color-warning);
    }}
    
    .capital-companies {{ display: grid; gap: 16px; }}
    
    .capital-company-card {{
      background: #ffffff;
      border: 1px solid var(--border-light);
      border-radius: 12px;
      padding: 16px;
      transition: all 0.2s;
    }}
    
    .capital-company-card:hover {{
      border-color: var(--border-medium);
      box-shadow: var(--shadow-hover);
    }}
    
    .capital-company-header {{
      display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
    }}
    
    .capital-company-name {{ font-weight: 600; font-size: 15px; color: var(--text-primary); }}
    
    .capital-company-symbol {{
      background: #f0f2f5;
      padding: 2px 8px; border-radius: 6px; font-size: 13px; color: var(--text-secondary);
    }}
    
    .capital-count {{ color: var(--accent-primary); font-weight: 600; font-size: 13px; }}
    
    .capital-titles {{ color: var(--text-secondary); font-size: 14px; line-height: 1.7; }}
    
    /* ============================================
       News Section Styles
       ============================================ */
    .news-buckets {{
      display: grid;
      gap: 16px;
    }}
    
    .news-bucket-card {{
      background: #ffffff;
      border: 1px solid var(--border-light);
      border-radius: 12px;
      overflow: hidden;
      transition: all 0.2s ease;
    }}
    
    .news-bucket-card:hover {{
      border-color: var(--border-medium);
      box-shadow: var(--shadow-hover);
    }}
    
    .bucket-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 20px;
      background: #fafafc;
      cursor: pointer;
      user-select: none;
      transition: background 0.2s;
    }}
    
    .bucket-header:hover {{
      background: #f0f2f5;
    }}
    
    .bucket-info {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    
    .bucket-name {{
      font-weight: 600;
      font-size: 15px;
      color: var(--text-primary);
    }}
    
    .bucket-count {{
      font-size: 13px;
      color: var(--accent-primary);
      font-weight: 500;
    }}
    
    .bucket-summary {{
      padding: 12px 20px;
      background: var(--ai-bg);
      border-bottom: 1px solid var(--ai-border);
      display: flex;
      align-items: flex-start;
      gap: 10px;
    }}
    
    .bucket-news-list {{
      max-height: 600px;
      overflow-y: auto;
      transition: max-height 0.3s ease;
      padding: 12px 20px;
    }}
    
    .bucket-news-list.collapsed {{
      max-height: 0;
      overflow: hidden;
      padding: 0 20px;
    }}
    
    .news-item {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 10px 0;
      border-bottom: 1px solid #f0f2f5;
      font-size: 13px;
      line-height: 1.6;
    }}
    
    .news-item:last-child {{
      border-bottom: none;
    }}
    
    .news-index {{
      color: var(--text-tertiary);
      font-weight: 500;
      min-width: 24px;
    }}
    
    .news-headline {{
      flex: 1;
      color: var(--text-primary);
    }}
    
    .news-score {{
      font-size: 11px;
      color: var(--text-tertiary);
      background: #f0f2f5;
      padding: 2px 6px;
      border-radius: 4px;
    }}
    
    /* ============================================
       Mobile Optimizations
       ============================================ */
    @media (max-width: 1024px) {{
      .wrap {{ padding: 24px 16px; }}
      td.title {{ min-width: 200px; max-width: 350px; }}
    }}
    
    @media (max-width: 768px) {{
      h1 {{ font-size: 24px; }}
      .tabs {{ padding: 12px 0; gap: 8px; }}
      .tab {{ padding: 8px 16px; font-size: 13px; }}
      
      .panel {{ padding: 20px; border-radius: 12px; }}
      
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
      th, td {{ padding: 12px; }}
      td.title {{ white-space: normal; min-width: 220px; }}
    }}
</style>
</head>
<body>
  <main class="wrap">
    <h1>{fmt(date)} Alpha日报</h1>

    <nav class="tabs">{tabs_html}</nav>

    <div class="sections">
      {market_section}
      {news_section}
      {forecast_section}
      {relation_section}
      {interaction_section}
      {notice_section}
    </div>
  </main>
  
  <script>
    // 互动问答 - 公司QA展开/收起功能
    function toggleCompanyQa(cardId) {{
      const qaList = document.getElementById('qa-' + cardId);
      const toggleIcon = document.getElementById('toggle-' + cardId);
      
      if (qaList.classList.contains('collapsed')) {{
        qaList.classList.remove('collapsed');
        toggleIcon.classList.remove('collapsed');
        toggleIcon.textContent = '▼';
      }} else {{
        qaList.classList.add('collapsed');
        toggleIcon.classList.add('collapsed');
        toggleIcon.textContent = '▶';
      }}
    }}
    
    // 新闻动态 - 分类展开/收起功能
    function toggleNewsBucket(bucketId) {{
      const newsList = document.getElementById('list-' + bucketId);
      const toggleIcon = document.getElementById('toggle-' + bucketId);
      
      if (newsList.classList.contains('collapsed')) {{
        newsList.classList.remove('collapsed');
        toggleIcon.textContent = '▼';
      }} else {{
        newsList.classList.add('collapsed');
        toggleIcon.textContent = '▶';
      }}
    }}
    
    // 默认收起所有详细内容
    document.addEventListener('DOMContentLoaded', function() {{
      // 收起互动问答
      const cards = document.querySelectorAll('.company-interaction-card');
      cards.forEach((card) => {{
        const cardId = card.id;
        const qaList = document.getElementById('qa-' + cardId);
        const toggleIcon = document.getElementById('toggle-' + cardId);
        if (qaList) {{
          qaList.classList.add('collapsed');
        }}
        if (toggleIcon) {{
          toggleIcon.classList.add('collapsed');
          toggleIcon.textContent = '▶';
        }}
      }});
      
      // 收起新闻动态（已默认收起，通过CSS和HTML设置）
    }});
    
    // 机构调研AI解读功能
    async function analyzeResearch(itemKey, pdfUrl) {{
      const resultRow = document.getElementById('ai-result-' + itemKey);
      const contentDiv = document.getElementById('ai-content-' + itemKey);
      const btn = document.getElementById('btn-' + itemKey);
      
      // 如果已经展开，则收起
      if (resultRow.style.display !== 'none') {{
        resultRow.style.display = 'none';
        btn.textContent = 'AI解读';
        return;
      }}
      
      // 显示加载状态
      resultRow.style.display = 'table-row';
      btn.textContent = '收起';
      btn.classList.add('analyzing');
      
      try {{
        // 调用本地API进行AI解读
        const response = await fetch('http://localhost:8888/analyze', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{url: pdfUrl}})
        }});
        
        if (!response.ok) {{
          throw new Error('API请求失败: ' + response.status);
        }}
        
        const data = await response.json();
        contentDiv.innerHTML = `<div class="ai-summary-header"><span class="ai-icon">🤖</span><span class="ai-title">AI解读</span></div><div class="ai-summary-content">${{data.summary || '暂无解读内容'}}</div>`;
      }} catch (error) {{
        // API不可用时的备用方案：显示提示信息
        contentDiv.innerHTML = `<div class="ai-error">⚠️ AI解读服务暂不可用<br>请确保已启动本地API服务 (python ai_server.py)<br>错误: ${{error.message}}</div>`;
      }} finally {{
        btn.classList.remove('analyzing');
      }}
    }}
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
