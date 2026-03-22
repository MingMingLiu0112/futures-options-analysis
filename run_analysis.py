#!/usr/bin/env python3
"""
期货期权分析 - 主入口
支持多品种分析，输出到飞书

注意: 需要设置 PYTHONPATH 或从项目根目录运行
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 确保当前目录在 sys.path 中
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# 加载环境变量
load_dotenv()

# 导入模块
from . import FuturesOptionsAnalyzer
from .push.feishu import init_pusher, send_report
from .data.futures_data import get_futures_daily
from .utils.indicators import calculate_technical_indicators


# ============== 配置区 ==============
# 要分析的期货品种
TARGET_SYMBOLS = ["CU", "AU", "AG"]  # 铜、黄金、白银

# IV历史数据（需要从数据源获取或存储）
# 这里用模拟数据演示
IV_HISTORY = {
    "CU": [20, 22, 25, 28, 30, 32, 28, 25, 22, 24, 26, 28, 30, 32, 35],
    "AU": [12, 14, 15, 16, 18, 17, 15, 14, 13, 14, 15, 16, 18, 17, 16],
    "AG": [25, 28, 30, 32, 35, 38, 35, 32, 28, 30, 32, 35, 38, 40, 38]
}

# 期权IV数据（需要从数据源获取）
# 格式: {品种: {put_iv: xx, call_iv: xx}}
OPTIONS_IV = {
    "CU": {"put_iv": 24.5, "call_iv": 22.3},
    "AU": {"put_iv": 16.2, "call_iv": 15.8},
    "AG": {"put_iv": 35.0, "call_iv": 32.5}
}


def get_futures_data(symbol: str, days: int = 60) -> dict:
    """
    获取期货数据
    
    Returns:
        dict with keys: df, basis
    """
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    
    # 获取日线数据
    df = get_futures_daily(symbol, start_date, end_date)
    
    if df.empty:
        print(f"⚠️ 无法获取 {symbol} 期货数据")
        return {"df": None, "basis": 0}
    
    # 计算技术指标
    if len(df) > 20:
        df = calculate_technical_indicators(df)
    
    # 模拟基差数据（实际应从数据源获取）
    # basis > 0 表示贴水，basis < 0 表示升水
    basis = 0  # 默认
    
    return {
        "df": df,
        "basis": basis
    }


def analyze_symbol(symbol: str) -> dict:
    """分析单个品种"""
    print(f"\n📊 正在分析 {symbol}...")
    
    # 获取数据
    futures_data = get_futures_data(symbol)
    df = futures_data.get("df")
    
    if df is None or df.empty:
        print(f"⚠️ {symbol} 无数据，跳过")
        return None
    
    # 获取IV数据
    iv_history = IV_HISTORY.get(symbol, [])
    iv_data = OPTIONS_IV.get(symbol, {})
    
    # 创建分析器
    analyzer = FuturesOptionsAnalyzer(
        symbol=symbol,
        iv_history=iv_history,
        put_iv=iv_data.get("put_iv"),
        call_iv=iv_data.get("call_iv")
    )
    
    # 执行分析
    result = analyzer.analyze(futures_data)
    
    # 打印结果
    analyzer.print_report(result)
    
    return result


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 期货期权综合分析")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 初始化飞书推送
    webhook_url = os.getenv("FEISHU_WEBHOOK")
    if webhook_url:
        init_pusher(webhook_url)
        print("✅ 飞书推送已初始化")
    else:
        print("⚠️ 未配置 FEISHU_WEBHOOK，跳过推送")
    
    # 分析所有品种
    results = []
    for symbol in TARGET_SYMBOLS:
        result = analyze_symbol(symbol)
        if result:
            results.append(result)
    
    # 汇总报告
    if results:
        summary = create_summary(results)
        
        # 推送到飞书
        if webhook_url:
            print("\n📤 正在推送到飞书...")
            if send_report(summary):
                print("✅ 推送成功！")
            else:
                print("⚠️ 推送失败，请检查 webhook 配置")
        
        # 保存结果
        save_results(results, summary)
    else:
        print("\n⚠️ 没有可用的分析结果")
    
    print("\n✅ 分析完成!")


def create_summary(results: list) -> dict:
    """创建汇总报告"""
    summary = {
        "title": "期货期权日度分析汇总",
        "template": "purple",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    # 汇总各品种信号
    signals_text = ""
    for r in results:
        comp = r.get("composite", {})
        action = comp.get("action", "watch")
        action_emoji = {
            "long": "🟢",
            "short": "🔴",
            "watch": "⚪"
        }.get(action, "⚪")
        
        signals_text += f"{action_emoji} **{r['symbol']}**: {comp.get('recommendation', 'N/A')}\n"
    
    summary["content"] = signals_text
    
    return summary


def save_results(results: list, summary: dict):
    """保存分析结果"""
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存JSON
    import json
    filename = os.path.join(output_dir, f"analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": results}, f, ensure_ascii=False, indent=2)
    
    print(f"💾 结果已保存: {filename}")


if __name__ == "__main__":
    main()
