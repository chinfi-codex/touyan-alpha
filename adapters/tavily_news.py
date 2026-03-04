#!/usr/bin/env python3
"""
Tavily新闻动态收集器 - 严格复制run_monitor.py的搜索方法
"""
import json
import os
import re
from urllib import request
from datetime import datetime, timedelta
from pathlib import Path

# 严格复制run_monitor.py的queries配置
QUERIES = {
    'AI Industry': [
        'OpenAI Anthropic Kimi Zhipu MiniMax revenue funding valuation latest news',
        'data center construction AIDC hyperscale facility orders US Europe Middle East investment',
        '中国数据中心 AIDC 智算中心 建设 订单 招标 投资 2026',
        'Microsoft Google Amazon AWS Azure Meta capex spending cloud infrastructure bonds financing 2026',
        '阿里云 腾讯云 华为云 百度智能云 字节火山引擎 capex 资本开支 投资 融资 债券',
        'NVIDIA AMD Intel GPU new product launch orders partnerships data center AI chip roadmap',
        '华为昇腾 海光 寒武纪 天数智芯 GPU 产品发布 订单 合作 2026'
    ],
    'Macro': [
        'Fed FOMC meeting minutes Powell speech interest rate decision monetary policy latest',
        'US Dollar DXY Treasury yield crude oil gold copper commodity prices latest',
        'US CPI inflation nonfarm payrolls unemployment rate jobs report economic data latest',
        '中国 CPI PPI PMI 社融 社零消费 工业增加值 经济数据 2026'
    ],
    'Robotics': [
        'humanoid robotics embodied AI servo reducer force torque sensor robotaxi warehouse robotics latest',
        'Tesla Optimus Figure Unitree Agility Robotics industrial robot demand supply chain'
    ],
    'Commercial Space': [
        'commercial space launch reusable rocket satellite constellation earth observation space economy latest',
        'SpaceX Starlink Rocket Lab Relativity Firefly satellite manufacturing propulsion trends'
    ]
}

PAYLOAD_TEMPLATE = {
    'search_depth': 'advanced',
    'topic': 'news',
    'max_results': 8,
    'include_raw_content': False,
}


def clean_text(s: str) -> str:
    """严格复制run_monitor.py"""
    s = re.sub(r'\s+', ' ', (s or '')).strip()
    return s


def extract_numbers(text: str) -> list:
    """严格复制run_monitor.py"""
    nums = re.findall(r'\b\d+(?:\.\d+)?(?:%|bps|bp|B|M|K|bn|million|billion|trillion|x|nm|W|kW|MW|GW|TB|GB|nm)?\b', text, flags=re.I)
    seen, out = set(), []
    for n in nums:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
        if len(out) >= 4:
            break
    return out


def extract_subject(title: str) -> str:
    """严格复制run_monitor.py"""
    t = clean_text(title)
    if not t:
        return ''
    m = re.split(r'\s[-|:–—]\s|: | - | \| ', t)
    candidate = m[0] if m else t
    words = candidate.split()
    if len(words) < 2:
        words = t.split()[:6]
        candidate = ' '.join(words)
    return candidate[:60]


def extract_event(snippet: str, body: str, title: str) -> str:
    """严格复制run_monitor.py"""
    source = clean_text(snippet) or clean_text(body) or clean_text(title)
    if not source:
        return ''
    parts = re.split(r'(?<=[\.!?。；;])\s+', source)
    evt = parts[0] if parts else source
    evt = evt.replace('latest', '').replace('update', '').strip(' -:;')
    return evt[:120]


def make_natural_title(subject: str, event: str, nums: list) -> str:
    """严格复制run_monitor.py"""
    subject = re.sub(r'\s+', ' ', subject).strip()[:60]
    event = re.sub(r'\s+', ' ', event).strip()[:120]
    
    if nums:
        headline = f"{subject} {event} ({', '.join(nums)})"
    else:
        headline = f"{subject} {event}"
    
    headline = re.sub(r'\s*[:|]\s*', ' ', headline)
    headline = re.sub(r'\s+', ' ', headline).strip()
    
    if len(headline) > 140:
        headline = headline[:137] + '...'
    
    return headline if headline else 'N/A'


def fetch_news(bucket: str, query: str, api_key: str) -> list:
    """使用Tavily API获取新闻"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    
    body = dict(PAYLOAD_TEMPLATE)
    body['query'] = query
    
    req = request.Request(
        'https://api.tavily.com/search',
        data=json.dumps(body).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    
    try:
        with request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        results = []
        for r in data.get('results', []):
            results.append({
                'bucket': bucket,
                'title': clean_text(r.get('title') or ''),
                'url': clean_text(r.get('url') or ''),
                'snippet': clean_text(r.get('content') or ''),
                'score': float(r.get('score', 0) or 0),
                'query': query,
            })
        return results
    except Exception as e:
        return [{'bucket': bucket, 'title': f'[ERROR] {e}', 'url': '', 'snippet': '', 'score': 0, 'query': query}]


def collect_all_news(api_key: str = None) -> dict:
    """收集所有分类的新闻"""
    if api_key is None:
        api_key = os.getenv('TAVILY_API_KEY', '').strip()
    
    if not api_key:
        return {'error': 'Missing TAVILY_API_KEY', 'data': {}}
    
    all_rows = []
    for bucket, queries in QUERIES.items():
        for q in queries:
            results = fetch_news(bucket, q, api_key)
            all_rows.extend(results)
    
    # 去重，保留高分
    best = {}
    for r in all_rows:
        key = r['url'] or f"err::{r['bucket']}::{r['title']}"
        if key not in best or r['score'] > best[key]['score']:
            best[key] = r
    
    final_rows = list(best.values())
    
    # 按分类组织
    data = {}
    for bucket in QUERIES:
        bucket_rows = [
            r for r in final_rows 
            if r['bucket'] == bucket 
            and not r['title'].startswith('[ERROR]') 
            and r['url']
        ]
        bucket_rows.sort(key=lambda x: -x['score'])
        bucket_rows = bucket_rows[:8]  # 每分类最多8条
        
        # 处理每条新闻
        processed = []
        for r in bucket_rows:
            subject = extract_subject(r['title'])
            event = extract_event(r['snippet'], '', r['title'])
            nums = extract_numbers((r['title'] + ' ' + r['snippet'])[:3000])
            headline = make_natural_title(subject, event, nums)
            
            processed.append({
                'headline': headline,
                'title': r['title'],
                'url': r['url'],
                'snippet': r['snippet'][:300],
                'score': r['score'],
                'numbers': nums,
            })
        
        data[bucket] = processed
    
    return {'error': None, 'data': data}


def generate_bucket_summary(bucket_name: str, news_items: list) -> str:
    """为每个分类生成AI总结"""
    if not news_items:
        return "暂无新闻"
    
    # 准备数据
    headlines = [f"- {item['headline']}" for item in news_items[:5]]
    content = f"请总结【{bucket_name}】领域的最新动态（限60字）：\n" + "\n".join(headlines)
    
    try:
        import openai
        import concurrent.futures
        
        api_key = "7c45a349-5a95-4885-a7b6-df6ed599ed5e"
        base_url = "https://ark.cn-beijing.volces.com/api/v3"
        model_id = "ep-20260103112951-vxd7j"
        
        def _call_api():
            client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=20)
            completion = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "你是金融分析师，用简洁中文总结行业新闻要点，控制在60字以内。"},
                    {"role": "user", "content": content},
                ],
                temperature=0,
                max_tokens=100,
            )
            if hasattr(completion, "choices") and completion.choices:
                return completion.choices[0].message.content.strip()
            return "AI总结失败"
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_call_api)
            return future.result(timeout=15)
            
    except concurrent.futures.TimeoutError:
        return "AI总结超时"
    except Exception as e:
        return f"AI总结失败: {str(e)[:30]}"


def save_news_data(date: str, output_dir: Path) -> bool:
    """收集并保存新闻动态数据"""
    try:
        result = collect_all_news()
        
        if result['error']:
            print(f"新闻收集失败: {result['error']}")
            # 保存空数据
            data = {'date': date, 'categories': {}}
        else:
            # 为每个分类生成AI总结
            categories = {}
            for bucket, items in result['data'].items():
                print(f"  生成{bucket} AI总结...")
                summary = generate_bucket_summary(bucket, items)
                categories[bucket] = {
                    'summary': summary,
                    'items': items,
                    'count': len(items)
                }
            
            data = {
                'date': date,
                'categories': categories
            }
        
        # 保存JSON
        out_path = output_dir / date
        out_path.mkdir(parents=True, exist_ok=True)
        
        json_file = out_path / "tavily_news.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"新闻动态数据已保存: {json_file}")
        return True
        
    except Exception as e:
        print(f"保存新闻动态数据失败: {e}")
        return False


if __name__ == "__main__":
    # 测试
    today = datetime.now().strftime("%Y-%m-%d")
    result = save_news_data(today, Path("output"))
    print(f"结果: {'成功' if result else '失败'}")
