#!/usr/bin/env python3
"""
知识星球数据收集器 - 获取星球主题内容
"""
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# 知识星球 API 配置
ZSXQ_COOKIE = os.environ.get("ZSXQ_COOKIE", "")
ZSXQ_GROUP_IDS = os.environ.get("ZSXQ_GROUP_IDS", "")  # 多个星球ID用逗号分隔
ZSXQ_API_TIMEOUT = float(os.environ.get("ZSXQ_API_TIMEOUT", "10"))


class ZsxqApiClient:
    """知识星球 API 客户端"""
    
    def __init__(self, cookie=None):
        self.base_url = "https://api.zsxq.com"
        self.app_version = "3.11.0"
        self.platform = "ios"
        self.secret = "zsxqapi2020"
        self.cookie = cookie or ZSXQ_COOKIE
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Cookie": self.cookie,
            "Origin": "https://wx.zsxq.com",
            "Referer": "https://wx.zsxq.com/"
        }
    
    def _generate_signature(self, path, params=None):
        """生成 API 签名"""
        common_params = {
            "app_version": self.app_version,
            "platform": self.platform,
            "timestamp": str(int(time.time() * 1000))
        }
        
        all_params = common_params.copy()
        if params and isinstance(params, dict):
            all_params.update(params)
        
        sorted_params = sorted(all_params.items(), key=lambda x: x[0])
        params_str = urlencode(sorted_params)
        
        sign_str = f"{path}&{params_str}&{self.secret}"
        
        md5 = hashlib.md5()
        md5.update(sign_str.encode("utf-8"))
        signature = md5.hexdigest()
        
        return signature, common_params["timestamp"]
    
    def _request(self, path, params=None):
        """发送 GET 请求"""
        if not self.cookie:
            return None, "未配置 ZSXQ_COOKIE"
        
        signature, timestamp = self._generate_signature(path, params)
        
        headers = self.headers.copy()
        headers["X-Signature"] = signature
        headers["X-Timestamp"] = timestamp
        
        url = f"{self.base_url}{path}"
        query = urlencode(params) if params else ""
        full_url = f"{url}?{query}" if query else url
        
        try:
            req = Request(full_url, headers=headers, method="GET")
            with urlopen(req, timeout=ZSXQ_API_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("succeeded"):
                    return data.get("resp_data", {}), None
                else:
                    err_msg = data.get("error") or data.get("resp_err") or "未知错误"
                    return None, err_msg
        except Exception as e:
            return None, str(e)
    
    def get_my_groups(self, count=20):
        """获取我的知识星球列表"""
        path = "/v2/groups"
        params = {"count": count}
        
        resp, err = self._request(path, params)
        if err:
            return [], err
        
        return resp.get("groups", []), None
    
    def get_group_topics(self, group_id, count=20, end_time=None):
        """获取星球主题列表"""
        path = f"/v2/groups/{group_id}/topics"
        params = {"count": count}
        if end_time:
            params["end_time"] = end_time
        
        resp, err = self._request(path, params)
        if err:
            return [], None, err
        
        topics = resp.get("topics", [])
        next_end_time = resp.get("end_time")
        return topics, next_end_time, None
    
    def _parse_create_time(self, create_time_str):
        """解析 ISO 8601 格式的时间字符串为毫秒时间戳"""
        if not create_time_str:
            return 0
        try:
            # 处理格式: 2026-03-07T20:26:18.143+0800
            dt = datetime.fromisoformat(create_time_str.replace('+0800', '+08:00'))
            return int(dt.timestamp() * 1000)
        except:
            return 0

    def get_topics_by_date(self, group_id, date, limit=50):
        """获取指定日期的主题"""
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        start_time = int(date_obj.timestamp() * 1000)
        end_time_val = int((date_obj + timedelta(days=1)).timestamp() * 1000)
        
        all_topics = []
        current_end_time = None
        page = 0
        max_pages = 10
        
        while page < max_pages:
            topics, next_end_time, err = self.get_group_topics(
                group_id, count=20, end_time=current_end_time
            )
            if err:
                break
            
            if not topics:
                break
            
            for topic in topics:
                topic_time = self._parse_create_time(topic.get("create_time", ""))
                if start_time <= topic_time < end_time_val:
                    all_topics.append(topic)
                elif topic_time < start_time:
                    # 已经超出日期范围
                    return all_topics[:limit], None
            
            if not next_end_time:
                break
            
            current_end_time = next_end_time
            page += 1
            time.sleep(0.3)  # 避免请求过快
        
        return all_topics[:limit], None


def parse_topic(topic):
    """解析主题数据为统一格式"""
    topic_id = topic.get("topic_id")
    title = topic.get("title", "")
    content = ""
    
    # 提取内容
    talk = topic.get("talk", {})
    if talk:
        content = talk.get("text", "")
        if not title and content:
            # 如果没有标题，取内容前30字作为标题
            title = content[:30] + "..." if len(content) > 30 else content
    
    # 获取作者信息
    author = ""
    owner = topic.get("owner", {})
    if owner:
        author = owner.get("name", "")
    
    # 创建时间格式化
    create_time = topic.get("create_time", "")
    try:
        dt = datetime.fromisoformat(create_time.replace('+0800', '+08:00'))
        create_time_str = dt.strftime("%Y-%m-%d %H:%M")
    except:
        create_time_str = create_time[:16] if create_time else ""
    
    # 主题链接
    topic_url = f"https://wx.zsxq.com/dweb2/index/topic/{topic_id}"
    
    return {
        "type": "zsxq_topic",
        "id": str(topic_id),
        "title": title or "无标题",
        "content": content,
        "author": author,
        "created_at": create_time_str,
        "url": topic_url,
        "source": "知识星球",
    }


def fetch_topics_by_date(date, limit=50):
    """从知识星球获取指定日期的主题
    
    Args:
        date: 日期字符串，格式 YYYY-MM-DD
        limit: 最大返回数量
        
    Returns:
        dict: {"items": [...], "error": ""}
    """
    if not ZSXQ_COOKIE or not ZSXQ_GROUP_IDS:
        return {"items": [], "error": "未配置 ZSXQ_COOKIE 或 ZSXQ_GROUP_IDS"}
    
    client = ZsxqApiClient()
    group_ids = [g.strip() for g in ZSXQ_GROUP_IDS.split(",") if g.strip()]
    
    all_items = []
    errors = []
    
    for group_id in group_ids:
        topics, err = client.get_topics_by_date(group_id, date, limit=limit)
        if err:
            errors.append(f"星球 {group_id}: {err}")
            continue
        
        for topic in topics:
            item = parse_topic(topic)
            item["group_id"] = group_id
            all_items.append(item)
    
    return {
        "items": all_items[:limit],
        "error": "; ".join(errors) if errors else ""
    }


def save_zsxq_data(date: str, output_dir: Path) -> bool:
    """收集并保存知识星球数据
    
    Args:
        date: 日期字符串，格式 YYYY-MM-DD
        output_dir: 输出目录路径
        
    Returns:
        bool: 是否成功
    """
    try:
        result = fetch_topics_by_date(date, limit=50)
        
        data = {
            "date": date,
            "items": result["items"],
            "error": result["error"],
            "count": len(result["items"])
        }
        
        # 保存JSON
        out_path = output_dir / date
        out_path.mkdir(parents=True, exist_ok=True)
        
        json_file = out_path / "zsxq.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"知识星球数据已保存: {json_file} ({data['count']} 条主题)")
        if data['error']:
            print(f"  警告: {data['error']}")
        return True
        
    except Exception as e:
        print(f"保存知识星球数据失败: {e}")
        return False


if __name__ == "__main__":
    # 测试
    today = datetime.now().strftime("%Y-%m-%d")
    result = save_zsxq_data(today, Path("output"))
    print(f"结果: {'成功' if result else '失败'}")
