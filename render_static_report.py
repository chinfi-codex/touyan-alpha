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


def render_interaction_section_with_ai(items, limit=40):
    """渲染互动问答区域，顶部带 AI 总结卡片"""
    # 生成 AI 总结（自动从环境变量或 .env 文件获取 API key）
    ai_summary = generate_ai_summary(items)
    
    # 准备表格数据
    rows_html = []
    display_items = top_items(items, limit=limit)
    
    for idx, item in enumerate(display_items):
        row_id = f"interaction-row-{idx}"
        # 默认只显示前5条
        hidden_class = " hidden-row" if idx >= 5 else ""
        
        question = fmt(item.get("title"))
        answer = fmt(item.get("summary"))
        link = (item.get("url") or "").strip()
        link_html = f"<a href='{fmt(link)}' target='_blank'>link</a>" if link else ""
        
        rows_html.append(
            f"<tr id='{row_id}' class='interaction-row{hidden_class}'>"
            f"<td>{fmt(item.get('date'))}</td>"
            f"<td>{fmt(item.get('symbol'))}</td>"
            f"<td>{fmt(item.get('company'))}</td>"
            f"<td class='title'>{question}</td>"
            f"<td class='title'>{answer}</td>"
            f"<td>{link_html}</td>"
            f"</tr>"
        )
    
    body = "\n".join(rows_html) or "<tr><td colspan='6'>无数据</td></tr>"
    total = len(items or [])
    
    return f"""
    <section id="interaction" class="panel">
      <h2>互动问答 <span>({total})</span></h2>
      
      <!-- AI 总结卡片 -->
      <div class="ai-summary-card">
        <div class="ai-summary-header">
          <span class="ai-icon">🤖</span>
          <span class="ai-title">AI 智能总结</span>
        </div>
        <div class="ai-summary-content">
          {html.escape(ai_summary).replace(chr(10), '<br>')}
        </div>
      </div>
      
      <!-- 展开/收起按钮 -->
      <div class="expand-controls">
        <button class="expand-btn" onclick="toggleInteraction()" id="expand-btn">
          展开全部 ({total} 条)
        </button>
      </div>
      
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Symbol</th>
            <th>Company</th>
            <th>Question</th>
            <th>Answer</th>
            <th>URL</th>
          </tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
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
    
    # 尝试从 akshare 获取业绩预告
    akshare_forecast = load_forecast_from_akshare(date)
    if akshare_forecast:
        forecast_items = akshare_forecast
    else:
        # 回退到本地数据
        forecast_items = tushare_forecast.get("items") or []

    # 分类 Tab 导航（点击可滑动到对应区域）
    # 顺序：业绩预告 -> 机构调研 -> 互动问答 -> 公告解读
    tabs = [
        ("业绩预告", "forecast"),
        ("机构调研", "relation"),
        ("互动问答", "interaction"),
        ("公告解读", "notice"),
    ]

    tabs_html = "".join(
        f"""<a class="tab" href="#{anchor}">{label}</a>"""
        for label, anchor in tabs
    )

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
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    /* ============================================
       Investing.com 风格配色系统 - 专业金融风
       ============================================ */
    :root {{
      /* 背景色阶 */
      --bg-primary: #ffffff;
      --bg-secondary: #f8f9fa;
      --bg-tertiary: #f0f2f5;
      --bg-hover: #e8eaed;
      
      /* 文字色阶 */
      --text-primary: #1a1a1a;
      --text-secondary: #5f6368;
      --text-tertiary: #80868b;
      --text-inverse: #ffffff;
      
      /* 边框与分隔线 */
      --border-light: #e8eaed;
      --border-medium: #dadce0;
      --border-dark: #bdc1c6;
      
      /* 金融语义色（红涨绿跌 - A股习惯） */
      --color-up: #00a651;           /* 上涨绿 */
      --color-up-light: #e6f4ea;
      --color-up-bg: #d4edda;
      --color-down: #d93025;         /* 下跌红 */
      --color-down-light: #fce8e6;
      --color-down-bg: #f8d7da;
      --color-warning: #f9ab00;      /* 警示橙 */
      --color-warning-light: #fef3e8;
      --color-warning-bg: #fff3cd;
      --color-info: #1a73e8;         /* 信息蓝 */
      --color-info-light: #e8f0fe;
      --color-info-bg: #cce5ff;
      
      /* 品牌强调色 */
      --accent-primary: #1a73e8;
      --accent-secondary: #00a651;
      --accent-hover: #1557b0;
      
      /* 阴影系统 */
      --shadow-sm: 0 1px 2px 0 rgba(60,64,67,0.08);
      --shadow-md: 0 2px 6px 2px rgba(60,64,67,0.08);
      --shadow-lg: 0 4px 12px 4px rgba(60,64,67,0.08);
      
      /* AI专属色 */
      --ai-bg: #e8f0fe;
      --ai-border: #d2e3fc;
      --ai-text: #1a73e8;
    }}
    
    * {{ box-sizing: border-box; }}
    
    html {{
      scroll-behavior: smooth;
      scroll-padding-top: 80px;
    }}
    
    body {{
      margin: 0;
      font-family: "Noto Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: var(--text-primary);
      background: var(--bg-secondary);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}
    
    .wrap {{ 
      max-width: 1400px; 
      margin: 0 auto; 
      padding: 24px 16px 40px; 
    }}
    
    h1, h2, h3 {{ 
      margin: 0; 
      font-weight: 600;
      letter-spacing: -0.02em;
    }}
    
    h1 {{
      font-size: 26px;
      color: var(--text-primary);
      padding-bottom: 12px;
      border-bottom: 3px solid var(--accent-primary);
      display: inline-block;
    }}
    
    /* ============================================
       导航标签 - 胶囊样式优化
       ============================================ */
    .tabs {{ 
      display: flex; 
      gap: 10px; 
      margin-top: 20px; 
      padding: 12px 4px; 
      border-bottom: 1px solid var(--border-medium); 
      position: sticky; 
      top: 0; 
      background: rgba(248, 249, 250, 0.98); 
      backdrop-filter: blur(12px); 
      z-index: 100;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
    }}
    .tabs::-webkit-scrollbar {{ display: none; }}
    
    .tab {{ 
      padding: 10px 20px; 
      border-radius: 24px; 
      background: var(--bg-primary); 
      border: 1px solid var(--border-medium); 
      color: var(--text-secondary); 
      text-decoration: none; 
      font-size: 14px; 
      font-weight: 500; 
      transition: all 0.2s ease;
      white-space: nowrap;
      box-shadow: var(--shadow-sm);
    }}
    .tab:hover {{ 
      background: var(--bg-hover); 
      color: var(--text-primary);
      transform: translateY(-1px);
      box-shadow: var(--shadow-md);
      border-color: var(--border-dark);
    }}
    .tab:active {{
      transform: translateY(0);
    }}
    
    /* ============================================
       板块卡片系统 - 优化层次
       ============================================ */
    .sections {{ 
      margin-top: 24px; 
      display: grid; 
      gap: 20px; 
    }}
    
    .panel {{ 
      background: var(--bg-primary);
      border-radius: 16px;
      padding: 20px;
      box-shadow: var(--shadow-md);
      border: 1px solid var(--border-light);
      overflow: hidden;
    }}
    
    .panel h2 {{ 
      margin-bottom: 16px;
      font-size: 18px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    
    .panel h2 span {{ 
      color: var(--text-tertiary); 
      font-weight: 500; 
      font-size: 13px;
      background: var(--bg-tertiary);
      padding: 4px 12px;
      border-radius: 12px;
      border: 1px solid var(--border-light);
    }}
    
    .stack {{ 
      display: grid; 
      gap: 16px; 
    }}
    
    .subpanel {{ 
      background: var(--bg-secondary);
      border-radius: 12px;
      padding: 16px;
      border: 1px solid var(--border-light);
      transition: all 0.2s ease;
    }}
    
    .subpanel:hover {{
      box-shadow: var(--shadow-sm);
      border-color: var(--border-medium);
    }}
    
    .subpanel h3 {{ 
      margin-bottom: 12px;
      font-size: 15px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
    }}
    
    .subpanel h3 span {{ 
      color: var(--text-tertiary); 
      font-weight: 500; 
      font-size: 13px;
    }}
    
    /* ============================================
       表格系统 - 斑马纹+优化行高
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
    }}
    
    th {{ 
      color: var(--text-secondary); 
      font-weight: 600; 
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 14px 12px;
      text-align: left;
      border-bottom: 2px solid var(--border-medium);
      background: var(--bg-secondary);
    }}
    
    td {{ 
      padding: 16px 12px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--border-light);
      transition: background-color 0.15s ease;
      line-height: 1.5;
    }}
    
    tbody tr:hover td {{
      background-color: var(--bg-hover);
    }}
    
    tbody tr:nth-child(even) td {{
      background-color: rgba(248, 249, 250, 0.6);
    }}
    
    tbody tr:nth-child(even):hover td {{
      background-color: var(--bg-hover);
    }}
    
    td.title {{ 
      min-width: 240px;
      max-width: 480px;
      line-height: 1.6;
    }}
    
    /* ============================================
       链接样式 - 图标化优化
       ============================================ */
    a {{ 
      color: var(--accent-primary); 
      text-decoration: none;
      font-weight: 500;
      transition: all 0.2s;
    }}
    a:hover {{ 
      color: var(--accent-hover);
      text-decoration: underline;
    }}
    
    a[target="_blank"]::after {{
      content: " ↗";
      font-size: 0.8em;
      opacity: 0.6;
    }}
    
    .empty {{ 
      color: var(--text-tertiary); 
      font-size: 14px;
      text-align: center;
      padding: 48px 20px;
      font-style: italic;
      background: var(--bg-secondary);
      border-radius: 12px;
    }}
    
    /* ============================================
       AI 总结卡片 - 优化样式
       ============================================ */
    .ai-summary-card {{
      background: linear-gradient(135deg, var(--ai-bg) 0%, #f8fbff 100%);
      border: 1px solid var(--ai-border);
      border-radius: 14px;
      padding: 20px;
      margin: 16px 0;
      box-shadow: var(--shadow-sm);
    }}
    .ai-summary-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }}
    .ai-icon {{
      font-size: 22px;
      filter: drop-shadow(0 1px 2px rgba(0,0,0,0.1));
    }}
    .ai-title {{
      font-weight: 600;
      color: var(--ai-text);
      font-size: 15px;
    }}
    .ai-summary-content {{
      color: var(--text-primary);
      font-size: 14px;
      line-height: 1.8;
    }}
    
    /* ============================================
       业绩预告子区域 - 优化卡片
       ============================================ */
    .forecast-company {{
      background: var(--bg-primary);
      border: 1px solid var(--border-light);
      border-radius: 14px;
      padding: 18px;
      box-shadow: var(--shadow-sm);
      transition: all 0.2s ease;
    }}
    .forecast-company:hover {{
      box-shadow: var(--shadow-md);
      border-color: var(--border-medium);
    }}
    .forecast-company h3 {{
      margin-bottom: 12px;
      font-size: 16px;
      color: var(--text-primary);
      font-weight: 600;
    }}
    .forecast-company h3 span {{
      color: var(--text-tertiary);
      font-weight: 500;
      font-size: 14px;
      margin-left: 8px;
      background: var(--bg-tertiary);
      padding: 2px 8px;
      border-radius: 8px;
    }}
    .forecast-metrics {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      margin-bottom: 12px;
      background: var(--bg-secondary);
      border-radius: 8px;
      overflow: hidden;
    }}
    .forecast-metrics thead {{
      position: static;
    }}
    .forecast-metrics th {{
      color: var(--text-secondary);
      font-weight: 600;
      background: var(--bg-tertiary);
      padding: 10px 8px;
      font-size: 12px;
      border-bottom: 1px solid var(--border-medium);
    }}
    .forecast-metrics td {{
      padding: 10px 8px;
      border-bottom: 1px solid var(--border-light);
    }}
    .forecast-reason {{
      color: var(--text-secondary);
      font-size: 13px;
      line-height: 1.7;
      padding: 12px;
      background: var(--bg-secondary);
      border-radius: 10px;
      border-left: 3px solid var(--accent-primary);
    }}
    
    /* ============================================
       AI解读按钮 - 优化触控区域
       ============================================ */
    .ai-analyze-btn {{
      padding: 8px 14px;
      border-radius: 16px;
      background: var(--ai-bg);
      color: var(--ai-text);
      border: 1px solid var(--ai-border);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      min-height: 36px;
      min-width: 72px;
    }}
    .ai-analyze-btn:hover {{
      background: var(--ai-text);
      color: #fff;
      box-shadow: var(--shadow-sm);
    }}
    .ai-analyze-btn.analyzing {{
      opacity: 0.6;
      cursor: not-allowed;
    }}
    .ai-result-row {{
      background: var(--ai-bg);
    }}
    .ai-result-cell {{
      padding: 0;
    }}
    .ai-analyze-result {{
      padding: 16px 20px;
      font-size: 14px;
      line-height: 1.7;
      color: var(--text-primary);
    }}
    .ai-loading {{
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--text-secondary);
    }}
    .ai-analyze-result .ai-icon {{
      font-size: 18px;
    }}
    .ai-error {{
      color: var(--color-down);
      background: var(--color-down-light);
      padding: 12px;
      border-radius: 8px;
      font-weight: 500;
    }}
    
    /* ============================================
       展开/收起按钮 - 统一风格
       ============================================ */
    .expand-controls {{
      margin: 16px 0;
      text-align: right;
    }}
    .expand-btn {{
      padding: 10px 20px;
      border-radius: 20px;
      background: var(--accent-primary);
      color: #fff;
      border: none;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      box-shadow: var(--shadow-sm);
      min-height: 44px;
    }}
    .expand-btn:hover {{
      background: var(--accent-hover);
      box-shadow: var(--shadow-md);
      transform: translateY(-1px);
    }}
    .expand-btn:active {{
      transform: translateY(0);
    }}
    .interaction-row.hidden-row {{
      display: none;
    }}
    
    /* ============================================
       监管函警示样式 - 高对比度优化
       ============================================ */
    .regulatory-warning {{
      background: linear-gradient(135deg, var(--color-warning-light) 0%, #fff 100%);
      border: 1px solid var(--color-warning);
      border-radius: 14px;
      padding: 18px;
      box-shadow: var(--shadow-sm);
    }}
    .regulatory-warning h3 {{
      color: var(--text-primary);
      font-weight: 700;
    }}
    .regulatory-warning h3::before {{
      content: "⚠️ ";
      font-size: 1.2em;
    }}
    .regulatory-row {{
      background: rgba(249, 171, 0, 0.06);
      border-left: 3px solid var(--color-warning);
    }}
    .regulatory-row:hover {{
      background: rgba(249, 171, 0, 0.12);
    }}
    
    /* ============================================
       资本运作公司聚合样式
       ============================================ */
    .capital-companies {{
      display: grid;
      gap: 14px;
    }}
    .capital-company-card {{
      background: var(--bg-primary);
      border: 1px solid var(--border-light);
      border-radius: 12px;
      padding: 16px;
      transition: all 0.25s ease;
      box-shadow: var(--shadow-sm);
    }}
    .capital-company-card:hover {{
      border-color: var(--accent-primary);
      box-shadow: var(--shadow-md);
      transform: translateY(-2px);
    }}
    .capital-company-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
      flex-wrap: wrap;
    }}
    .capital-company-name {{
      font-weight: 700;
      color: var(--text-primary);
      font-size: 15px;
    }}
    .capital-company-symbol {{
      color: var(--text-tertiary);
      font-size: 14px;
      font-weight: 500;
      background: var(--bg-tertiary);
      padding: 2px 8px;
      border-radius: 6px;
    }}
    .capital-count {{
      color: var(--accent-primary);
      font-size: 13px;
      font-weight: 700;
    }}
    .capital-titles {{
      font-size: 14px;
      color: var(--text-secondary);
      line-height: 1.8;
      padding-left: 4px;
    }}
    
    /* ============================================
       移动端适配 - 全面优化
       ============================================ */
    @media (max-width: 1024px) {{
      .wrap {{ padding: 20px 16px; }}
      td.title {{ min-width: 180px; max-width: 350px; }}
    }}
    
    @media (max-width: 768px) {{
      /* 基础调整 */
      html {{ font-size: 16px; }}
      body {{ line-height: 1.5; }}
      
      h1 {{
        font-size: 22px;
        padding-bottom: 10px;
      }}
      
      .wrap {{ padding: 16px 12px; }}
      
      /* Tab导航优化 */
      .tabs {{
        padding: 10px 0;
        gap: 8px;
      }}
      .tab {{
        padding: 8px 16px;
        font-size: 13px;
      }}
      
      /* 卡片调整 */
      .panel {{
        padding: 16px;
        border-radius: 12px;
      }}
      .panel h2 {{
        font-size: 16px;
      }}
      .panel h2 span {{
        font-size: 12px;
        padding: 3px 8px;
      }}
      
      .subpanel {{
        padding: 14px;
        border-radius: 10px;
      }}
      
      /* 表格适配 - 横向滚动 */
      table {{
        display: block;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        white-space: nowrap;
      }}
      
      thead {{
        position: static;
      }}
      
      th, td {{
        padding: 12px 10px;
        font-size: 14px;
      }}
      
      td.title {{
        min-width: 200px;
        max-width: none;
        white-space: normal;
      }}
      
      /* 触控区域优化 */
      .ai-analyze-btn,
      .expand-btn,
      a {{
        min-height: 44px;
        min-width: 44px;
      }}
      
      /* AI卡片调整 */
      .ai-summary-card {{
        padding: 16px;
      }}
      
      /* 资本运作卡片 */
      .capital-company-card {{
        padding: 14px;
      }}
      .capital-company-header {{
        gap: 8px;
      }}
    }}
    
    @media (max-width: 480px) {{
      h1 {{ font-size: 20px; }}
      
      .tab {{
        padding: 6px 12px;
        font-size: 12px;
      }}
      
      .panel {{ padding: 14px 12px; }}
      
      th, td {{
        padding: 10px 8px;
        font-size: 13px;
      }}
      
      .forecast-company {{
        padding: 14px;
      }}
      
      .ai-summary-content {{
        font-size: 13px;
        line-height: 1.7;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>{fmt(date)} Alpha日报</h1>

    <nav class="tabs">{tabs_html}</nav>

    <div class="sections">
      {forecast_section}
      {relation_section}
      {interaction_section}
      {notice_section}
    </div>
  </main>
  
  <script>
    // 互动问答展开/收起功能
    let interactionExpanded = false;
    function toggleInteraction() {{
      const rows = document.querySelectorAll('.interaction-row');
      const btn = document.getElementById('expand-btn');
      
      interactionExpanded = !interactionExpanded;
      
      rows.forEach((row, idx) => {{
        if (idx >= 5) {{
          if (interactionExpanded) {{
            row.classList.remove('hidden-row');
          }} else {{
            row.classList.add('hidden-row');
          }}
        }}
      }});
      
      btn.textContent = interactionExpanded ? '收起' : '展开全部 ({len(p5w_interaction.get("items") or [])} 条)';
    }}
    
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
