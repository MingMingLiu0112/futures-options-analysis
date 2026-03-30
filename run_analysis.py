#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
期货技术分析 - 纯技术面 + 真实行情
东财API获取期货数据，本地计算技术指标，飞书推送
"""

import os
import sys
import json
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ============================================================
# 数据获取 - 东方财富API
# ============================================================

def http_get(url: str, headers: Dict = None) -> Optional[str]:
    """发起HTTP GET请求，优先curl"""
    try:
        cmd = ["curl", "-s", "--max-time", "15", url]
        if headers:
            for k, v in headers.items():
                cmd += ["-H", f"{k}: {v}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  HTTP请求失败: {e}")
    return None


def get_futures_list() -> List[Dict]:
    """获取东财期货主力合约列表"""
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
        "&fs=m:112+t:3"  # 商品期货主力
        "&fields=f12,f14,f3,f2,f4,f5,f6,f7,f15,f16,f17,f18"
    )
    text = http_get(url)
    if not text:
        return []
    try:
        d = json.loads(text)
        return d.get("data", {}).get("diff", [])
    except Exception as e:
        print(f"解析期货列表失败: {e}")
        return []


def get_futures_kline(secid: str, count: int = 60) -> pd.DataFrame:
    """
    获取期货日K线数据
    secid格式: 112.M26N (东财期货代码)
    """
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=count + 30)).strftime("%Y%m%d")
    
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56"
        f"&klt=101&fqt=1"  # 日K线
        f"&beg={start_date}&end={end_date}"
        f"&lmt={count}"
    )
    
    text = http_get(url)
    if not text:
        return pd.DataFrame()
    
    try:
        d = json.loads(text)
        klines = d.get("data", {}).get("klines", [])
        if not klines:
            return pd.DataFrame()
        
        records = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 6:
                records.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                })
        
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").tail(count).reset_index(drop=True)
        return df
    except Exception as e:
        print(f"解析K线失败: {e}")
        return pd.DataFrame()


# ============================================================
# 技术指标计算
# ============================================================

def calc_ma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()


def calc_ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = calc_ema(series, fast)
    ema_slow = calc_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def calc_rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(n).mean()
    avg_loss = loss.rolling(n).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_bollinger(series: pd.Series, n: int = 20, k: float = 2):
    mid = series.rolling(n).mean()
    std = series.rolling(n).std()
    upper = mid + k * std
    lower = mid - k * std
    return upper, mid, lower


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def analyze_technicals(df: pd.DataFrame) -> Dict:
    """计算完整技术分析"""
    if df.empty or len(df) < 10:
        return {}
    
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    
    # 均线
    ma5 = calc_ma(close, 5).iloc[-1]
    ma10 = calc_ma(close, 10).iloc[-1]
    ma20 = calc_ma(close, 20).iloc[-1]
    ma60 = calc_ma(close, min(60, len(df))).iloc[-1]
    
    # 均线方向
    ma5_prev = calc_ma(close, 5).iloc[-2]
    ma10_prev = calc_ma(close, 10).iloc[-2]
    ma20_prev = calc_ma(close, 20).iloc[-2]
    
    # MACD
    macd, signal, hist = calc_macd(close)
    macd_val = macd.iloc[-1]
    macd_signal = signal.iloc[-1]
    macd_hist = hist.iloc[-1]
    macd_hist_prev = hist.iloc[-2]
    
    # RSI
    rsi = calc_rsi(close).iloc[-1]
    
    # 布林带
    bb_upper, bb_mid, bb_lower = calc_bollinger(close)
    bb_upper_val = bb_upper.iloc[-1]
    bb_mid_val = bb_mid.iloc[-1]
    bb_lower_val = bb_lower.iloc[-1]
    
    # ATR
    atr = calc_atr(high, low, close).iloc[-1]
    
    # 成交量分析
    vol_ma5 = vol.rolling(5).mean().iloc[-1]
    vol_ratio = vol.iloc[-1] / vol_ma5 if vol_ma5 > 0 else 1.0
    
    # 涨跌
    close_cur = close.iloc[-1]
    close_prev = close.iloc[-2] if len(close) > 1 else close_cur
    change_pct = (close_cur - close_prev) / close_prev * 100
    
    # 关键价位
    high_20 = high.tail(20).max()
    low_20 = low.tail(20).min()
    high_60 = high.tail(60).max() if len(df) >= 60 else high_20
    low_60 = low.tail(60).min() if len(df) >= 60 else low_20
    
    return {
        "price": round(close_cur, 2),
        "change": round(change_pct, 2),
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2) if not pd.isna(ma60) else None,
        "ma5_dir": "up" if ma5 > ma5_prev else "down",
        "ma10_dir": "up" if ma10 > ma10_prev else "down",
        "ma20_dir": "up" if ma20 > ma20_prev else "down",
        "macd": round(macd_val, 2),
        "macd_signal": round(macd_signal, 2),
        "macd_hist": round(macd_hist, 2),
        "macd_cross": "金叉" if macd_hist > 0 and macd_hist_prev < 0 else ("死叉" if macd_hist < 0 and macd_hist_prev > 0 else "无"),
        "rsi": round(rsi, 1),
        "bb_upper": round(bb_upper_val, 2),
        "bb_mid": round(bb_mid_val, 2),
        "bb_lower": round(bb_lower_val, 2),
        "atr": round(atr, 2),
        "vol_ratio": round(vol_ratio, 2),
        "high_20": round(high_20, 2),
        "low_20": round(low_20, 2),
        "high_60": round(high_60, 2),
        "low_60": round(low_60, 2),
    }


def generate_signal(tech: Dict) -> Dict:
    """基于技术指标生成交易信号"""
    if not tech:
        return {"action": "数据不足", "confidence": "低", "signals": []}
    
    score = 0
    signals = []
    
    # MA趋势
    ma_score = 0
    if tech["ma5"] > tech["ma20"]: ma_score += 2
    else: ma_score -= 2
    if tech["ma10"] > tech["ma20"]: ma_score += 1
    else: ma_score -= 1
    if tech["ma5"] > tech["ma5_dir"].replace("up","1").replace("down","0"): 
        pass  # already counted
    
    # MA多头排列
    if tech["ma5"] > tech["ma10"] > tech["ma20"]:
        score += 2
        signals.append("✅ MA多头排列（5>10>20）")
    elif tech["ma5"] < tech["ma10"] < tech["ma20"]:
        score -= 2
        signals.append("🔻 MA空头排列（5<10<20）")
    
    # 均线支撑/压力
    if tech["price"] > tech["ma5"]:
        score += 1
        signals.append("✅ 价格站上MA5")
    else:
        score -= 1
        signals.append("⚠️ 价格跌破MA5")
    
    if tech["price"] > tech["ma20"]:
        score += 1
        signals.append("✅ 价格站上MA20")
    else:
        score -= 1
        signals.append("⚠️ 价格跌破MA20")
    
    # MACD
    if tech["macd_cross"] == "金叉":
        score += 2
        signals.append("✅ MACD金叉")
    elif tech["macd_cross"] == "死叉":
        score -= 2
        signals.append("🔻 MACD死叉")
    
    if tech["macd_hist"] > 0:
        score += 1
        signals.append("✅ MACD柱正值")
    else:
        score -= 1
        signals.append("⚠️ MACD柱负值")
    
    # RSI
    rsi = tech["rsi"]
    if rsi > 75:
        score -= 1
        signals.append(f"⚠️ RSI超买({rsi})")
    elif rsi < 25:
        score += 1
        signals.append(f"✅ RSI超卖({rsi})")
    elif rsi > 65:
        signals.append(f"📊 RSI偏强({rsi})")
    elif rsi < 35:
        signals.append(f"📊 RSI偏弱({rsi})")
    else:
        signals.append(f"📊 RSI中性({rsi})")
    
    # 布林带位置
    if tech["price"] <= tech["bb_lower"] * 1.01:
        score += 1
        signals.append("✅ 触及布林下轨支撑")
    elif tech["price"] >= tech["bb_upper"] * 0.99:
        score -= 1
        signals.append("⚠️ 触及布林上轨压力")
    
    # 成交量
    if tech["vol_ratio"] > 1.5:
        signals.append(f"📊 成交量放大({tech['vol_ratio']}x)")
        if tech["change"] > 0: score += 1
        else: score -= 1
    elif tech["vol_ratio"] < 0.5:
        signals.append(f"📊 成交量萎缩({tech['vol_ratio']}x)")
    
    # 综合判断
    if score >= 3:
        action, action_emoji = "做多", "🟢"
    elif score <= -3:
        action, action_emoji = "做空", "🔴"
    else:
        action, action_emoji = "观望", "⚪"
    
    confidence = "高" if abs(score) >= 4 else ("中" if abs(score) >= 2 else "低")
    
    return {
        "score": score,
        "action": action,
        "action_emoji": action_emoji,
        "confidence": confidence,
        "signals": signals,
    }


# ============================================================
# 期货品种配置
# ============================================================

# 常用期货品种（中文名 -> 东财代码）
# 市场代码: 112=商品期货, 113=金融期货, 114=原油
FUTURES_MAP = {
    "豆粕": "M",
    "玉米": "C",
    "铁矿石": "I",
    "螺纹钢": "RB",
    "热轧卷板": "HC",
    "不锈钢": "SS",
    "黄金": "AU",
    "白银": "AG",
    "铜": "CU",
    "铝": "AL",
    "锌": "ZN",
    "镍": "NI",
    "锡": "SN",
    "橡胶": "RU",
    "原油": "SC",
    "沥青": "BU",
    "甲醇": "MA",
    "PTA": "TA",
    "乙二醇": "EG",
    "PVC": "V",
    "塑料": "L",
    "聚丙烯": "PP",
    "白糖": "SR",
    "棉花": "CF",
    "菜粕": "RM",
    "菜油": "OI",
    "棕榈油": "P",
    "豆油": "Y",
    "焦煤": "JM",
    "焦炭": "J",
    "动力煤": "ZC",
    "液化气": "PG",
}

# 重点关注的品种
TARGET_SYMBOLS = ["M", "I", "RB", "AU", "CU", "NI", "RU", "JM", "J", "P"]


# ============================================================
# 飞书推送
# ============================================================

FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")


def get_futures_secid(symbol: str, futures_list: List[Dict]) -> Optional[str]:
    """根据品种代码找东财secid"""
    symbol = symbol.upper()
    for item in futures_list:
        code = item.get("f12", "")
        name = item.get("f14", "")
        # 匹配主力合约（名字包含品种代码）
        if symbol in code.upper():
            return f"112.{code}"
    return None


def build_feishu_card(results: List[Dict]) -> Dict:
    """构建飞书卡片"""
    long_cnt = sum(1 for r in results if r.get("signal", {}).get("action") == "做多")
    short_cnt = sum(1 for r in results if r.get("signal", {}).get("action") == "做空")
    watch_cnt = len(results) - long_cnt - short_cnt
    
    if long_cnt > short_cnt:
        summary_emoji = "🟢"
    elif short_cnt > long_cnt:
        summary_emoji = "🔴"
    else:
        summary_emoji = "⚪"
    
    summary = f"{summary_emoji} 做多{long_cnt} | 做空{short_cnt} | 观望{watch_cnt}"
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"⏰ **{now_str}** · {summary}"
            }
        }
    ]
    
    for r in results:
        tech = r.get("tech", {})
        sig = r.get("signal", {})
        if not tech:
            continue
        
        action = sig.get("action", "观望")
        emoji = sig.get("action_emoji", "⚪")
        arrow = "📈" if tech.get("change", 0) >= 0 else "📉"
        
        # MA排列
        if tech["ma5"] > tech["ma10"] > tech["ma20"]:
            ma_text = "多头↑"
        elif tech["ma5"] < tech["ma10"] < tech["ma20"]:
            ma_text = "空头↓"
        else:
            ma_text = "纠缠"
        
        # RSI状态
        rsi = tech["rsi"]
        if rsi >= 70:
            rsi_text = f"⚠️超买{rsi}"
        elif rsi <= 30:
            rsi_text = f"⚠️超卖{rsi}"
        else:
            rsi_text = f"正常{rsi}"
        
        # MACD状态
        macd_text = sig.get("macd_cross", "无")
        
        # 成交量
        vr = tech["vol_ratio"]
        vol_text = "放量" if vr > 1.2 else ("缩量" if vr < 0.8 else "正常")
        
        # 信号列表
        sig_list = sig.get("signals", [])
        sig_md = "\n".join([f"• {s}" for s in sig_list[:5]]) if sig_list else "• 暂无明显信号"
        
        content = (
            f"{emoji} **{r['name']}** {arrow} {tech['change']:+.2f}%\n\n"
            f"💰 **收盘 {tech['price']}** | {ma_text}\n\n"
            f"📊 **技术指标**\n"
            f"• MA5: {tech['ma5']} / MA20: {tech['ma20']}\n"
            f"• RSI: {rsi_text} | MACD: {macd_text}\n"
            f"• 布林带: {tech['bb_lower']}~{tech['bb_upper']}\n"
            f"• ATR: {tech['atr']} | 成交量: {vol_text}({vr}x)\n\n"
            f"🎯 **操作**: **{action}**（置信度:{sig.get('confidence','N/A')}）\n\n"
            f"📋 **信号明细**\n{sig_md}"
        )
        
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content}})
    
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "⚠️ 仅供参考，不构成投资建议"}]
    })
    
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "📊 期货技术分析日度信号"},
                "template": "purple"
            },
            "elements": elements
        }
    }


def push_feishu(card: Dict) -> bool:
    """推送飞书"""
    if not FEISHU_WEBHOOK:
        print("⚠️ 未配置 FEISHU_WEBHOOK")
        return False
    try:
        import requests
        resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
        result = resp.json()
        ok = result.get("code") == 0 or result.get("StatusCode") == 0
        if ok:
            print("✅ 飞书推送成功")
        else:
            print(f"⚠️ 推送失败: {result}")
        return ok
    except Exception as e:
        print(f"⚠️ 推送异常: {e}")
        return False


# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 60)
    print("📊 期货技术分析")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 获取期货列表
    print("\n📡 正在获取期货列表...")
    futures_list = get_futures_list()
    if not futures_list:
        print("⚠️ 获取期货列表失败，尝试备用方法...")
    else:
        print(f"✅ 获取到 {len(futures_list)} 个期货合约")
    
    # 2. 遍历目标品种
    results = []
    for sym in TARGET_SYMBOLS:
        cn_name = [k for k, v in FUTURES_MAP.items() if v == sym]
        name = cn_name[0] if cn_name else sym
        print(f"\n📊 正在分析 {name}({sym})...")
        
        # 查找合约代码
        secid = None
        for item in futures_list:
            code = item.get("f12", "")
            if sym.upper() in code.upper():
                secid = f"112.{code}"
                print(f"  找到合约: {code} | {item.get('f14','')} | 涨跌:{item.get('f3','N/A')}%")
                break
        
        if not secid:
            print(f"  ⚠️ 未找到 {sym} 主力合约，跳过")
            continue
        
        # 获取K线
        df = get_futures_kline(secid, count=60)
        if df.empty:
            print(f"  ⚠️ 获取K线数据失败，跳过")
            continue
        print(f"  获得K线 {len(df)} 条，最新: {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
        
        # 技术分析
        tech = analyze_technicals(df)
        sig = generate_signal(tech)
        
        print(f"  信号: {sig['action']} | MA5={tech['ma5']} | RSI={tech['rsi']} | MACD={sig.get('macd_cross','无')}")
        
        results.append({
            "symbol": sym,
            "name": name,
            "secid": secid,
            "tech": tech,
            "signal": sig,
        })
    
    # 3. 输出结果
    if results:
        print("\n" + "=" * 60)
        print("📊 分析结果汇总")
        print("=" * 60)
        for r in results:
            sig = r["signal"]
            tech = r["tech"]
            print(f"\n{r['name']}: {sig['action_emoji']} {sig['action']} | 价格:{tech['price']} | 涨跌:{tech['change']:+.2f}%")
            print(f"  MA5:{tech['ma5']} MA20:{tech['ma20']} RSI:{tech['rsi']} MACD:{sig.get('macd_cross')}")
        
        # 4. 飞书推送
        print("\n📤 正在推送到飞书...")
        card = build_feishu_card(results)
        push_feishu(card)
    else:
        print("\n⚠️ 没有可用的分析结果")
    
    print("\n✅ 分析完成!")


if __name__ == "__main__":
    main()
