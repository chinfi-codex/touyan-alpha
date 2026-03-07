#!/usr/bin/env python3
"""
Clippings API 数据收集器 - 获取当日文件列表
"""
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# Clippings API 配置
CLIPPINGS_API_BASE_URL = os.environ.get(
    "CLIPPINGS_API_BASE_URL", "http://47.90.205.168:8787"
).rstrip("/")
CLIPPINGS_API_TOKEN = os.environ.get(
    "CLIPPINGS_API_TOKEN", "o-RQo6GJCAElSxgcNSbftAwv2rc1tGbOJIiG-BlJxyI"
)
CLIPPINGS_API_TIMEOUT = float(os.environ.get("CLIPPINGS_API_TIMEOUT", "8"))


def fmt_file_size(size):
    """格式化文件大小"""
    try:
        n = int(size)
    except Exception:
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def fetch_files_by_date(date, limit=50):
    """从 clippings-api 获取指定日期的文件
    
    Args:
        date: 日期字符串，格式 YYYY-MM-DD
        limit: 最大返回数量
        
    Returns:
        dict: {"items": [...], "error": ""}
    """
    query = urlencode({"date": date, "limit": limit})
    url = f"{CLIPPINGS_API_BASE_URL}/files?{query}"
    headers = {}
    if CLIPPINGS_API_TOKEN:
        headers["Authorization"] = f"Bearer {CLIPPINGS_API_TOKEN}"
    req = Request(url, headers=headers)

    try:
        with urlopen(req, timeout=CLIPPINGS_API_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"items": [], "error": str(e)}

    raw_items = []
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        for key in ("files", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = value
                break

    items = []
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        path = str(
            row.get("path")
            or row.get("file_path")
            or row.get("filename")
            or row.get("name")
            or ""
        ).strip()
        if not path:
            continue
        created_at = (
            row.get("created_at")
            or row.get("createdAt")
            or row.get("birth_time")
            or row.get("ctime")
            or row.get("mtime")
            or row.get("date")
            or ""
        )
        size_text = fmt_file_size(row.get("size") or row.get("file_size") or row.get("bytes"))
        file_url = f"{CLIPPINGS_API_BASE_URL}/file?{urlencode({'path': path})}"
        items.append(
            {
                "type": "clipping_file",
                "path": path,
                "created_at": str(created_at or ""),
                "size_text": size_text,
                "url": file_url,
                "source": "clippings-api",
            }
        )

    return {"items": items[:limit], "error": ""}


def save_clippings_data(date: str, output_dir: Path) -> bool:
    """收集并保存 clippings-api 数据
    
    Args:
        date: 日期字符串，格式 YYYY-MM-DD
        output_dir: 输出目录路径
        
    Returns:
        bool: 是否成功
    """
    try:
        result = fetch_files_by_date(date, limit=50)
        
        data = {
            "date": date,
            "items": result["items"],
            "error": result["error"],
            "count": len(result["items"])
        }
        
        # 保存JSON
        out_path = output_dir / date
        out_path.mkdir(parents=True, exist_ok=True)
        
        json_file = out_path / "clippings.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"Clippings 数据已保存: {json_file} ({data['count']} 个文件)")
        return True
        
    except Exception as e:
        print(f"保存 Clippings 数据失败: {e}")
        return False


if __name__ == "__main__":
    # 测试
    today = datetime.now().strftime("%Y-%m-%d")
    result = save_clippings_data(today, Path("output"))
    print(f"结果: {'成功' if result else '失败'}")
