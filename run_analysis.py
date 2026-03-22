#!/usr/bin/env python3
"""
期货期权综合分析
包含所有模块，无外部依赖导入问题
"""

import os
import sys
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ==================== 波动率信号模块 ====================

def calculate_iv_rank(current_iv: float, iv_history: list) -> float:
    if len(iv_history) < 2:
        return 50.0
    iv_min, iv_max = min(iv_history), max(iv_history)
    if iv_max == iv_min:
        return 50.0
    return round((current_iv - iv_min) / (iv_max - iv_min) * 100, 2)


def calculate_iv_percentile(current_iv: float, iv_history: list) -> float:
    if len(iv_history) < 2:
        return 50.0
    percentile = sum(1 for iv in iv_history if iv < current_iv) / len(iv_history) * 100
    return round(percentile, 2)


def calculate_iv_skew(put_iv: float, call_iv: float) -> dict:
    skew = put_iv - call_iv
    sentiment = "偏空" if skew > 0.5 else ("偏多" if skew < -0.5 else "中性")
    return {"skew": round(skew, 4), "sentiment": sentiment, "put_iv": put_iv, "call_iv": call_iv}


def calculate_basis_iv_signal(basis: float, current_iv: float, iv_history: list) -> dict:
    iv_rank = calculate_iv_rank(current_iv, iv_history)
    if basis > 0:
        if iv_rank > 60:
            return {"basis": round(basis, 4), "iv_rank": iv_rank, "signal": "多信号共振偏多", "direction": "多", "confidence": "高", "reason": "贴水 + IV偏高"}
        elif iv_rank < 40:
            return {"basis": round(basis, 4), "iv_rank": iv_rank, "signal": "矛盾信号", "direction": "观望", "confidence": "低", "reason": "贴水但IV偏低"}
        else:
            return {"basis": round(basis, 4), "iv_rank": iv_rank, "signal": "偏多", "direction": "多", "confidence": "中", "reason": "贴水结构"}
    else:
        if iv_rank > 60:
            return {"basis": round(basis, 4), "iv_rank": iv_rank, "signal": "矛盾信号", "direction": "观望", "confidence": "低", "reason": "升水但IV偏高"}
        elif iv_rank < 40:
            return {"basis": round(basis, 4), "iv_rank": iv_rank, "signal": "空信号共振", "direction": "空", "confidence": "高", "reason": "升水 + IV偏低"}
        else:
            return {"basis": round(basis, 4), "iv_rank": iv_rank, "signal": "偏空", "direction": "空", "confidence": "中", "reason": "升水结构"}


def composite_signal(iv_rank: float, skew: float, basis_signal: dict, momentum: str = "neutral") -> dict:
    score = 0
    signals = []
    if iv_rank < 20:
        score += 2
        signals.append("IV极低→波动即将放大")
    elif iv_rank > 80:
        score -= 2
        signals.append("IV极高→注意风险")
    if skew > 1:
        score -= 1
        signals.append("看跌Skew→市场担忧下跌")
    elif skew < -1:
        score += 1
        signals.append("看涨Skew→市场看涨")
    if basis_signal["direction"] == "多":
        score += 2
        signals.append(f"基差信号偏多({basis_signal['reason']})")
    elif basis_signal["direction"] == "空":
        score -= 2
        signals.append(f"基差信号偏空({basis_signal['reason']})")
    if momentum == "bullish":
        score += 1
        signals.append("价格动量向上")
    elif momentum == "bearish":
        score -= 1
        signals.append("价格动量向下")
    if score >= 3:
        recommendation, action = "建议做多", "long"
    elif score <= -3:
        recommendation, action = "建议做空", "short"
    else:
        recommendation, action = "建议观望", "watch"
    return {"score": score, "recommendation": recommendation, "action": action, "signals": signals, "confidence": "高" if abs(score) >= 3 else ("中" if abs(score) >= 1 else "低")}


# ==================== 技术指标模块 ====================

def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['histogram'] = df['macd'] - df['signal']
    df['bb_mid'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df


def detect_momentum(df: pd.DataFrame, lookback: int = 5) -> str:
    if len(df) < lookback:
        return "neutral"
    recent = df.tail(lookback)
    ma5, ma20 = recent['close'].mean(), df['close'].rolling(20).mean().iloc[-1]
    return "bullish" if ma5 > ma20 * 1.02 else ("bearish" if ma5 < ma20 * 0.98 else "neutral")


def calculate_volume_profile(df: pd.DataFrame) -> tuple:
    volume = df['volume'].iloc[-1] if len(df) > 0 else 0
    volume_ma = df['volume'].rolling(20).mean().iloc[-1] if len(df) >= 20 else volume
    return volume, volume / volume_ma if volume_ma > 0 else 1.0


# ==================== 数据获取模块 ====================

def get_futures_daily(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    使用AKShare获取期货日线数据
    symbol格式: 如 'M2509' 表示豆粕2509
    """
    try:
        import akshare as ak
        
        # 期货合约代码映射
        futures_map = {
            'M2509': ('M', '2509'),   # 豆粕
            'CU2509': ('CU', '2509'), # 铜
            'AU2509': ('AU', '2509'), # 黄金
            'AG2509': ('AG', '2509'), # 白银
            'RU2509': ('RU', '2509'), # 橡胶
            'SC2509': ('SC', '2509'), # 原油
        }
        
        # 解析合约
        contract_code = symbol.upper()
        
        # 获取主力合约历史K线
        try:
            # 方法1: 期货主力连续合约
            df = ak.futures_zh_daily_sina(symbol=contract_code)
            print(f"✅ {symbol} 数据获取成功 ({len(df)}条)")
        except Exception as e1:
            print(f"方法1失败: {e1}")
            df = pd.DataFrame()
        
        # 方法2: 如果方法1失败，尝试获取特定合约
        if df.empty:
            try:
                # 获取大商所期货数据
                df = ak.futures_daily_sina(symbol=contract_code)
                print(f"✅ {symbol} 方法2获取成功 ({len(df)}条)")
            except Exception as e2:
                print(f"方法2失败: {e2}")
        
        # 方法3: 尝试东方财富期货数据
        if df.empty:
            try:
                df = ak.stock_zh_a_hist(symbol='M2509', period='daily', start_date=start_date, end_date=end_date.replace('',''))
                print(f"✅ {symbol} 方法3获取成功 ({len(df)}条)")
            except Exception as e3:
                print(f"方法3失败: {e3}")
        
        if df.empty:
            print(f"⚠️ {symbol} 所有方法均失败")
            return pd.DataFrame()
        
        # 统一列名
        if '日期' in df.columns:
            df = df.rename(columns={'日期': 'date'})
        if 'date' not in df.columns and '日期' not in df.columns:
            if 'trade_date' in df.columns:
                df = df.rename(columns={'trade_date': 'date'})
        
        # 转换日期格式
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        # 筛选日期范围
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
        
        # 确保必要的列存在
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                # 尝试中文列名
                if col == 'open' and '开盘' in df.columns:
                    df = df.rename(columns={'开盘': 'open'})
                elif col == 'high' and '最高' in df.columns:
                    df = df.rename(columns={'最高': 'high'})
                elif col == 'low' and '最低' in df.columns:
                    df = df.rename(columns={'最低': 'low'})
                elif col == 'close' and '收盘' in df.columns:
                    df = df.rename(columns={'收盘': 'close'})
                elif col == 'volume' and '成交量' in df.columns:
                    df = df.rename(columns={'成交量': 'volume'})
        
        return df
        
    except Exception as e:
        print(f"获取期货数据失败: {e}")
        return pd.DataFrame()


def get_realtime_quote(symbol: str) -> dict:
    """获取期货实时行情"""
    try:
        import akshare as ak
        # 尝试获取实时行情
        df = ak.futures_zh_spot()
        # 筛选对应合约
        contract = symbol.upper()
        if contract in df['symbol'].values:
            row = df[df['symbol'] == contract].iloc[0]
            return {
                'symbol': contract,
                'open': float(row.get('open', 0)),
                'high': float(row.get('high', 0)),
                'low': float(row.get('low', 0)),
                'close': float(row.get('close', row.get('current', 0))),
                'volume': int(row.get('volume', 0)),
                'change': float(row.get('change', 0)),
            }
    except Exception as e:
        print(f"获取实时行情失败: {e}")
    return {}


# ==================== 飞书推送模块 ====================

class FeishuPusher:
    DEFAULT_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/8148922b-04f5-469f-994e-ae3e17d6b256"
    
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK") or self.DEFAULT_WEBHOOK
    
    def send_card(self, card: dict) -> bool:
        try:
            resp = requests.post(self.webhook_url, json={"msg_type": "interactive", "card": card}, timeout=10)
            result = resp.json()
            return result.get("code") == 0 or result.get("StatusCode") == 0
        except Exception as e:
            print(f"推送失败: {e}")
            return False
    
    def send_analysis_report(self, results: list) -> bool:
        card = {
            "header": {"title": {"tag": "plain_text", "content": "📊 期货期权日度分析"}, "template": "purple"},
            "elements": []
        }
        for r in results:
            comp = r.get("composite", {})
            action = comp.get("action", "watch")
            emoji = {"long": "🟢", "short": "🔴", "watch": "⚪"}.get(action, "⚪")
            iv = r.get("iv_signal", {})
            signals_text = "\n".join([f"• {s}" for s in comp.get("signals", [])]) or "无"
            content = (
                f"{emoji} **{r['symbol']}**: {comp.get('recommendation', 'N/A')}\n\n"
                f"📈 IV Rank: {iv.get('iv_rank', 'N/A')}%\n"
                f"📉 IV Skew: {iv.get('skew', 'N/A')} ({iv.get('sentiment', 'N/A')})\n"
                f"🎯 置信度: {comp.get('confidence', 'N/A')}\n\n"
                f"📋 信号:\n{signals_text}"
            )
            card["elements"].append({"tag": "div", "text": {"tag": "lark_md", "content": content}})
            card["elements"].append({"tag": "hr"})
        card["elements"].append({"tag": "note", "elements": [{"tag": "plain_text", "content": "⚠️ 本分析仅供参考，不构成投资建议"}]})
        return self.send_card(card)


# ==================== 分析引擎 ====================

class FuturesOptionsAnalyzer:
    def __init__(self, symbol: str, iv_history: list = None, put_iv: float = None, call_iv: float = None):
        self.symbol = symbol
        self.iv_history = iv_history or []
        self.put_iv = put_iv
        self.call_iv = call_iv
    
    def analyze(self, futures_data: dict) -> dict:
        result = {"title": f"{self.symbol} 期货期权分析", "symbol": self.symbol, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "iv_signal": {}, "composite": {}, "signals": []}
        if self.iv_history and self.put_iv and self.call_iv:
            avg_iv = (self.put_iv + self.call_iv) / 2
            skew_info = calculate_iv_skew(self.put_iv, self.call_iv)
            result["iv_signal"] = {"iv_rank": calculate_iv_rank(avg_iv, self.iv_history), "iv_percentile": calculate_iv_percentile(avg_iv, self.iv_history), "skew": skew_info["skew"], "sentiment": skew_info["sentiment"], "put_iv": self.put_iv, "call_iv": self.call_iv}
        basis = futures_data.get("basis", 0)
        basis_signal = calculate_basis_iv_signal(basis, (self.put_iv + self.call_iv) / 2 if self.put_iv and self.call_iv else 50, self.iv_history) if self.iv_history else {"direction": "观望", "reason": "IV数据不足"}
        df = futures_data.get("df")
        momentum = "neutral"
        if df is not None and not df.empty:
            df = calculate_technical_indicators(df)
            momentum = detect_momentum(df)
            _, vol_ratio = calculate_volume_profile(df)
            result["technical"] = {"momentum": momentum, "volume_ratio": round(vol_ratio, 2), "ma5": round(df['ma5'].iloc[-1], 2), "ma20": round(df['ma20'].iloc[-1], 2), "rsi": round(df['rsi'].iloc[-1], 1)}
        if self.iv_history:
            composite = composite_signal(result["iv_signal"].get("iv_rank", 50), result["iv_signal"].get("skew", 0), basis_signal, momentum)
            result["composite"] = composite
            result["signals"] = composite.get("signals", [])
        if df is not None and not df.empty:
            result["price"] = round(df['close'].iloc[-1], 2)
            result["change"] = round((df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1] * 100, 2)
        return result
    
    def print_report(self, result: dict):
        print("=" * 50)
        print(f"📊 {result['title']}")
        print("=" * 50)
        if "price" in result:
            print(f"价格: {result['price']} ({result['change']}%)")
        if result.get("iv_signal"):
            iv = result["iv_signal"]
            print(f"\n📈 波动率信号:")
            print(f"  IV Rank: {iv['iv_rank']}%")
            print(f"  IV Skew: {iv['skew']}")
            print(f"  市场情绪: {iv['sentiment']}")
        if result.get("composite"):
            comp = result["composite"]
            print(f"\n🎯 综合信号:")
            print(f"  建议: {comp['recommendation']}")
            print(f"  评分: {comp['score']:+d}")
            print(f"  置信度: {comp['confidence']}")
        if result.get("signals"):
            print(f"\n📋 信号列表:")
            for s in result["signals"]:
                print(f"  • {s}")
        print("=" * 50)


# ==================== 主程序 ====================

# 期货品种配置 - 支持多种合约
# 格式: "M2509" = 豆粕2509, "CU2509" = 铜2509, "AU2509" = 黄金2509
TARGET_SYMBOLS = ["M2509", "CU2509", "AU2509", "AG2509"]

# IV历史数据（需要从数据源获取或存储）
IV_HISTORY = {
    "M2509": [20, 22, 25, 28, 30, 32, 28, 25, 22, 24, 26, 28, 30, 32, 35],  # 豆粕
    "CU2509": [20, 22, 25, 28, 30, 32, 28, 25, 22, 24, 26, 28, 30, 32, 35],  # 铜
    "AU2509": [12, 14, 15, 16, 18, 17, 15, 14, 13, 14, 15, 16, 18, 17, 16],  # 黄金
    "AG2509": [25, 28, 30, 32, 35, 38, 35, 32, 28, 30, 32, 35, 38, 40, 38]   # 白银
}

# 期权IV数据（需要从数据源获取）
OPTIONS_IV = {
    "M2509": {"put_iv": 22.5, "call_iv": 20.3},   # 豆粕
    "CU2509": {"put_iv": 24.5, "call_iv": 22.3}, # 铜
    "AU2509": {"put_iv": 16.2, "call_iv": 15.8}, # 黄金
    "AG2509": {"put_iv": 35.0, "call_iv": 32.5}  # 白银
}
    "AU": {"put_iv": 16.2, "call_iv": 15.8},
    "AG": {"put_iv": 35.0, "call_iv": 32.5}
}


def main():
    print("=" * 60)
    print("🚀 期货期权综合分析")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    pusher = FeishuPusher()
    print("✅ 飞书推送已初始化")
    
    results = []
    for symbol in TARGET_SYMBOLS:
        print(f"\n📊 正在分析 {symbol}...")
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
        df = get_futures_daily(symbol, start_date, end_date)
        if df.empty:
            print(f"⚠️ {symbol} 无数据，跳过")
            continue
        df = calculate_technical_indicators(df)
        analyzer = FuturesOptionsAnalyzer(symbol=symbol, iv_history=IV_HISTORY.get(symbol, []), put_iv=OPTIONS_IV.get(symbol, {}).get("put_iv"), call_iv=OPTIONS_IV.get(symbol, {}).get("call_iv"))
        result = analyzer.analyze({"df": df, "basis": 0})
        analyzer.print_report(result)
        results.append(result)
    
    if results:
        print("\n📤 正在推送到飞书...")
        if pusher.send_analysis_report(results):
            print("✅ 推送成功！")
        else:
            print("⚠️ 推送失败")
    else:
        print("\n⚠️ 没有可用的分析结果")
    
    print("\n✅ 分析完成!")


if __name__ == "__main__":
    main()
