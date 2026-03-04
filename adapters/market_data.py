#!/usr/bin/env python3
"""
市场温度数据收集器 - 为Alpha日报提供大盘概览数据
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

try:
    import akshare as ak
    import pandas as pd
    import numpy as np
except ImportError:
    ak = None
    pd = None
    np = None


class MarketDataCollector:
    """大盘数据收集器 - 精简版，聚焦决策关键信息"""
    
    # 指数代码映射
    INDICES = {
        'sh': {'code': 'sh000001', 'name': '上证指数'},
        'cyb': {'code': 'sz399006', 'name': '创业板指'},
    }
    
    def __init__(self):
        self._validate_deps()
    
    def _validate_deps(self):
        """验证依赖是否可用"""
        if ak is None or pd is None:
            raise ImportError("需要安装 akshare 和 pandas: pip install akshare pandas")
    
    def _get_trade_date(self, date_str: str) -> str:
        """获取最近交易日（处理周末和节假日）"""
        date = datetime.strptime(date_str, "%Y-%m-%d")
        # 如果是周末，回退到周五
        while date.weekday() >= 5:  # 5=周六, 6=周日
            date -= timedelta(days=1)
        return date.strftime("%Y-%m-%d")
    
    def get_index_kline(self, symbol: str, days: int = 20) -> Optional[list]:
        """
        获取指数K线数据（蜡烛图格式）
        
        Returns:
            list: [{date, open, high, low, close, volume}, ...]
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 2)  # 预留足够天数过滤非交易日
        
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        df = None
        
        # 尝试多种数据源
        fetchers = [
            # 东方财富数据源
            lambda: ak.index_zh_a_hist(symbol=symbol, period="daily", 
                                       start_date=start_str, end_date=end_str),
            # 备用：腾讯数据源
            lambda: ak.stock_zh_index_daily_tx(symbol=symbol),
        ]
        
        for fetch in fetchers:
            try:
                df = fetch()
                if df is not None and not df.empty:
                    break
            except Exception:
                continue
        
        if df is None or df.empty:
            return None
        
        # 标准化列名
        column_mapping = {
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '成交额': 'amount',
        }
        
        # 重命名列
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df = df.rename(columns={old_col: new_col})
        
        # 确保必要的列存在
        required_cols = ['date', 'open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            # 尝试其他列名
            alt_mapping = {
                'date': ['日期', 'trade_date', 'datetime', 'time'],
                'open': ['开盘', 'open', '开盘价'],
                'high': ['最高', 'high', '最高价'],
                'low': ['最低', 'low', '最低价'],
                'close': ['收盘', 'close', '收盘价'],
                'volume': ['成交量', 'volume', 'vol', '成交'],
            }
            
            for std_col, alt_cols in alt_mapping.items():
                if std_col not in df.columns:
                    for alt in alt_cols:
                        if alt in df.columns:
                            df[std_col] = df[alt]
                            break
        
        # 处理日期
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        df = df.sort_values('date').tail(days)
        
        # 转换为标准格式
        result = []
        for _, row in df.iterrows():
            try:
                item = {
                    'date': row['date'].strftime('%Y-%m-%d'),
                    'open': float(row['open']) if pd.notna(row['open']) else None,
                    'high': float(row['high']) if pd.notna(row['high']) else None,
                    'low': float(row['low']) if pd.notna(row['low']) else None,
                    'close': float(row['close']) if pd.notna(row['close']) else None,
                    'volume': float(row['volume']) if 'volume' in row and pd.notna(row['volume']) else None,
                }
                result.append(item)
            except (ValueError, TypeError):
                continue
        
        return result if result else None
    
    def get_market_overview(self, date: str) -> Optional[dict]:
        """
        获取当日市场概况数据
        
        Returns:
            dict: {up_count, down_count, limit_up, limit_down, turnover, turnover_change}
        """
        date = self._get_trade_date(date)
        
        try:
            # 获取大盘数据
            df = ak.stock_zh_a_spot_em()
            
            if df is None or df.empty:
                return None
            
            # 标准化列名
            col_mapping = {
                '名称': 'name',
                '最新价': 'price',
                '涨跌幅': 'pct',
                '涨跌额': 'change',
                '成交量': 'volume',
                '成交额': 'amount',
            }
            
            for old, new in col_mapping.items():
                if old in df.columns:
                    df[new] = df[old]
            
            # 过滤ST和北交所
            df = df[~df['name'].astype(str).str.contains('ST', na=False)]
            df['code'] = df.get('代码', '').astype(str)
            df = df[~df['code'].str.startswith(('8', '4', '9'), na=False)]  # 排除北交/新三板
            
            # 计算涨跌家数
            df['pct'] = pd.to_numeric(df.get('pct'), errors='coerce')
            df = df.dropna(subset=['pct'])
            
            up_count = int((df['pct'] > 0).sum())
            down_count = int((df['pct'] < 0).sum())
            flat_count = int((df['pct'] == 0).sum())
            
            # 涨跌停统计（按A股规则：±10%，ST±5%，科创/创业±20%）
            df['code_num'] = df['code'].str.extract(r'(\d{6})')[0]
            
            def get_limit_pct(code):
                if pd.isna(code):
                    return 10
                code = str(code)
                if code.startswith(('688', '300', '301')):
                    return 20
                if 'ST' in str(df[df['code'] == code]['name'].values[0] if len(df[df['code'] == code]) > 0 else ''):
                    return 5
                return 10
            
            df['limit_pct'] = df['code_num'].apply(get_limit_pct)
            
            limit_up = int(((df['pct'] >= df['limit_pct'] - 0.5) & (df['pct'] > 9)).sum())
            limit_down = int(((df['pct'] <= -df['limit_pct'] + 0.5) & (df['pct'] < -9)).sum())
            
            # 成交额
            df['amount'] = pd.to_numeric(df.get('amount'), errors='coerce')
            turnover = df['amount'].sum() / 100000000  # 转换为亿元
            
            # 计算成交额变化（需要历史数据，简化处理）
            turnover_change = None
            try:
                hist_df = ak.stock_zh_index_daily_em(symbol="sh000001", 
                                                      start_date=(datetime.strptime(date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y%m%d"),
                                                      end_date=datetime.strptime(date, "%Y-%m-%d").strftime("%Y%m%d"))
                if hist_df is not None and len(hist_df) >= 2:
                    today_amount = hist_df['amount'].iloc[-1] if 'amount' in hist_df.columns else None
                    yest_amount = hist_df['amount'].iloc[-2] if 'amount' in hist_df.columns else None
                    if today_amount and yest_amount:
                        turnover_change = round((today_amount / yest_amount - 1) * 100, 2)
            except Exception:
                pass
            
            return {
                'up_count': up_count,
                'down_count': down_count,
                'flat_count': flat_count,
                'limit_up': limit_up,
                'limit_down': limit_down,
                'turnover': round(turnover, 2),
                'turnover_change': turnover_change,
            }
            
        except Exception as e:
            print(f"获取市场概况失败: {e}")
            return None
    
    def get_sentiment_radar(self, date: str) -> Optional[dict]:
        """
        计算五维情绪雷达数据
        
        Returns:
            dict: {breadth, intensity, consistency, volume, northbound} 各0-100分
        """
        date = self._get_trade_date(date)
        
        try:
            # 获取当日数据
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None
            
            # 标准化
            df['pct'] = pd.to_numeric(df.get('涨跌幅'), errors='coerce')
            df = df.dropna(subset=['pct'])
            
            # 1. 涨跌广度 (breadth): 上涨家数占比
            up_ratio = (df['pct'] > 0).sum() / len(df) * 100
            breadth = min(100, max(0, up_ratio * 2 - 30))  # 映射到0-100，中性50%
            
            # 2. 涨停强度 (intensity): 涨停家数加权
            limit_up_count = (df['pct'] > 9).sum()
            intensity = min(100, limit_up_count * 1.5)  # 60家涨停≈90分
            
            # 3. 连板持续性 (consistency): 通过涨跌幅标准差衡量一致性
            std_pct = df['pct'].std()
            consistency = max(0, 100 - std_pct * 10)  # 标准差越小，一致性越高
            
            # 4. 量能配合 (volume): 与近期平均比较（简化版）
            volume_score = 50  # 默认中性
            try:
                hist = ak.stock_zh_index_daily_em(symbol="sh000001",
                                                  start_date=(datetime.strptime(date, "%Y-%m-%d") - timedelta(days=20)).strftime("%Y%m%d"),
                                                  end_date=datetime.strptime(date, "%Y-%m-%d").strftime("%Y%m%d"))
                if hist is not None and len(hist) >= 5:
                    today_vol = hist['amount'].iloc[-1] if 'amount' in hist.columns else 0
                    avg_vol = hist['amount'].iloc[-5:-1].mean() if 'amount' in hist.columns else 0
                    if avg_vol > 0:
                        vol_change = (today_vol / avg_vol - 1) * 100
                        volume_score = min(100, max(0, 50 + vol_change))
            except Exception:
                pass
            
            # 5. 北向资金 (northbound): 简化处理，使用涨跌中位数作为代理
            median_pct = df['pct'].median()
            northbound = min(100, max(0, 50 + median_pct * 5))
            
            return {
                'breadth': round(breadth, 1),
                'intensity': round(intensity, 1),
                'consistency': round(consistency, 1),
                'volume': round(volume_score, 1),
                'northbound': round(northbound, 1),
            }
            
        except Exception as e:
            print(f"计算情绪雷达失败: {e}")
            return None
    
    def collect(self, date: str) -> dict:
        """
        收集完整的市场温度数据
        
        Returns:
            dict: 包含indices, snapshot, sentiment_radar的完整数据
        """
        result = {
            'date': date,
            'indices': {},
            'snapshot': {},
            'sentiment_radar': {},
        }
        
        # 1. 获取指数K线
        for key, info in self.INDICES.items():
            kline = self.get_index_kline(info['code'], days=20)
            if kline:
                latest = kline[-1] if kline else {}
                prev = kline[-2] if len(kline) > 1 else latest
                
                result['indices'][key] = {
                    'name': info['name'],
                    'code': info['code'],
                    'kline': kline,
                    'current': latest.get('close'),
                    'prev_close': prev.get('close'),
                    'change': round(latest.get('close', 0) - prev.get('close', 0), 2) if latest.get('close') and prev.get('close') else None,
                    'change_pct': round((latest.get('close', 0) / prev.get('close', 0) - 1) * 100, 2) if prev.get('close') else None,
                }
        
        # 2. 获取市场概况
        snapshot = self.get_market_overview(date)
        if snapshot:
            result['snapshot'] = snapshot
        
        # 3. 获取情绪雷达
        radar = self.get_sentiment_radar(date)
        if radar:
            result['sentiment_radar'] = radar
        
        return result


def save_market_data(date: str, output_dir: Path) -> bool:
    """
    收集并保存市场温度数据到JSON文件
    
    Args:
        date: 日期字符串 YYYY-MM-DD
        output_dir: 输出目录
    
    Returns:
        bool: 是否成功
    """
    try:
        collector = MarketDataCollector()
        data = collector.collect(date)
        
        # 确保输出目录存在
        out_path = output_dir / date
        out_path.mkdir(parents=True, exist_ok=True)
        
        # 保存JSON
        json_file = out_path / "market_temperature.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"市场温度数据已保存: {json_file}")
        return True
        
    except Exception as e:
        print(f"保存市场温度数据失败: {e}")
        return False


if __name__ == "__main__":
    # 测试
    today = datetime.now().strftime("%Y-%m-%d")
    result = save_market_data(today, Path("output"))
    print(f"结果: {'成功' if result else '失败'}")
