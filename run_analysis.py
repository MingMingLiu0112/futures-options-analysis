#!/usr/bin/env python3
"""
期货期权分析 - 主入口
直接导入同目录下的模块
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 添加当前目录到 sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# 加载环境变量
load_dotenv()

# 直接导入模块（同目录）
import importlib.util

def import_module_from_file(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# 导入各个模块
analyzer = import_module_from_file("analyzer", os.path.join(_current_dir, "analyzer.py"))
signals_volatility = import_module_from_file("signals_volatility", os.path.join(_current_dir, "signals", "volatility.py"))
data_futures = import_module_from_file("futures_data", os.path.join(_current_dir, "data", "futures_data.py"))
utils_indicators = import_module_from_file("indicators", os.path.join(_current_dir, "utils", "indicators.py"))
push_feishu = import_module_from_file("feishu", os.path.join(_current_dir, "push", "feishu.py"))

FuturesOptionsAnalyzer = analyzer.FuturesOptionsAnalyzer
init_pusher = push_feishu.init_pusher
send_report = push_feishu.send_report
get_futures_daily = data_futures.get_futures_daily
calculate_technical_indicators = utils_indicators.calculate_technical_indicators

# 计算波动率信号的函数
calculate_iv_rank = signals_volatility.calculate_iv_rank
calculate_iv_skew = signals_volatility.calculate_iv_skew
calculate_iv_percentile = signals_volatility.calculate_iv_percentile
calculate_basis_iv_signal = signals_volatility.calculate_basis_iv_signal
composite_signal = signals_volatility.composite_signal


# ============== 配置区 ==============
TARGET_SYMBOLS = ["CU", "AU", "AG"]  # 铜、黄金、白银

IV_HISTORY = {
    "CU": [20, 22, 25, 28, 30, 32, 28, 25, 22, 24, 26, 28, 30, 32, 35],
    "AU": [12, 14, 15, 16, 18, 17, 15, 14, 13, 14, 15, 16, 18, 17, 16],
    "AG": [25, 28, 30, 32, 35, 38, 35, 32, 28, 30, 32, 35, 38, 40, 38]
}

OPTIONS_IV = {
    "CU": {"put_iv": 24.5, "call_iv": 22.3},
    "AU": {"put_iv": 16.2, "call_iv": 15.8},
    "AG": {"put_iv": 35.0, "call_iv": 32.5}
}


def get_futures_data(symbol: str, days: int = 60) -> dict:
    """获取期货数据"""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    
    df = get_futures_daily(symbol, start_date, end_date)
    
    if df.empty:
        print(f"⚠️ 无法获取 {symbol} 期货数据")
        return {"df": None, "basis": 0}
    
    if len(df) > 20:
        df = calculate_technical_indicators(df)
    
    return {"df": df, "basis": 0}


def analyze_symbol(symbol: str) -> dict:
    """分析单个品种"""
    print(f"\n📊 正在分析 {symbol}...")
    
    futures_data = get_futures_data(symbol)
    df = futures_data.get("df")
    
    if df is None or df.empty:
        print(f"⚠️ {symbol} 无数据，跳过")
        return None
    
    iv_history = IV_HISTORY.get(symbol, [])
    iv_data = OPTIONS_IV.get(symbol, {})
    
    analyzer = FuturesOptionsAnalyzer(
        symbol=symbol,
        iv_history=iv_history,
        put_iv=iv_data.get("put_iv"),
        call_iv=iv_data.get("call_iv")
    )
    
    result = analyzer.analyze(futures_data)
    analyzer.print_report(result)
    
    return result


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 期货期权综合分析")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    webhook_url = os.getenv("FEISHU_WEBHOOK")
    if webhook_url:
        init_pusher(webhook_url)
        print("✅ 飞书推送已初始化")
    else:
        print("⚠️ 未配置 FEISHU_WEBHOOK，跳过推送")
    
    results = []
    for symbol in TARGET_SYMBOLS:
        result = analyze_symbol(symbol)
        if result:
            results.append(result)
    
    if results:
        summary = create_summary(results)
        
        if webhook_url:
            print("\n📤 正在推送到飞书...")
            if send_report(summary):
                print("✅ 推送成功！")
            else:
                print("⚠️ 推送失败")
        
        save_results(results)
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
    
    signals_text = ""
    for r in results:
        comp = r.get("composite", {})
        action = comp.get("action", "watch")
        action_emoji = {"long": "🟢", "short": "🔴", "watch": "⚪"}.get(action, "⚪")
        signals_text += f"{action_emoji} **{r['symbol']}**: {comp.get('recommendation', 'N/A')}\n"
    
    summary["content"] = signals_text
    return summary


def save_results(results: list):
    """保存分析结果"""
    output_dir = os.path.join(_current_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    
    import json
    filename = os.path.join(output_dir, f"analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)
    
    print(f"💾 结果已保存: {filename}")


if __name__ == "__main__":
    main()
