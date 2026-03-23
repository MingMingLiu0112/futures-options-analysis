"""
测试 akshare 获取期货数据的真实情况
"""
import sys
import traceback
import warnings
warnings.filterwarnings('ignore')

print("Python version:", sys.version)
print("=" * 60)

# 测试不同的 akshare 函数
test_contracts = {
    'M': '豆粕',
    'SS': '不锈钢',
    'C': '玉米',
    'OI': '菜籽油',
    'JM': '焦煤',
}

def test_function(name, func, **kwargs):
    print(f"\n{'='*60}")
    print(f"测试函数: {name}")
    print(f"kwargs: {kwargs}")
    try:
        import pandas as pd
        result = func(**kwargs)
        if result is None:
            print(f"  [❌] 返回 None")
            return False
        if isinstance(result, pd.DataFrame):
            print(f"  [✅] DataFrame, shape: {result.shape}")
            print(f"  列名: {list(result.columns)}")
            print(f"  前3行:\n{result.head(3)}")
        else:
            print(f"  [⚠️] 返回类型: {type(result)}")
            print(f"  内容: {str(result)[:200]}")
        return True
    except Exception as e:
        print(f"  [❌] 错误: {e}")
        traceback.print_exc()
        return False

# ---------- 测试开始 ----------

print("\n\n########## 测试1: ak.futures_zh_daily_sina ##########")
try:
    import akshare as ak
    print(f"akshare 版本: {ak.__version__}")
except Exception as e:
    print(f"导入失败: {e}")
    sys.exit(1)

# futures_zh_daily_sina - 接收 symbol 参数，格式如 "M0" 表示豆粕连续合约
for symbol, name in test_contracts.items():
    print(f"\n--- {symbol} ({name}) ---")
    test_function(
        f"futures_zh_daily_sina({symbol}0)",
        ak.futures_zh_daily_sina,
        symbol=f"{symbol}0"
    )

print("\n\n########## 测试2: ak.futures_zh_daily_sina (期货主力合约) ##########")
# 试试期货品种主力合约
for symbol, name in test_contracts.items():
    print(f"\n--- {symbol} ({name}) ---")
    # 主力合约格式
    test_function(
        f"futures_zh_daily_sina({symbol}88)",
        ak.futures_zh_daily_sina,
        symbol=f"{symbol}88"
    )

print("\n\n########## 测试3: ak.futures 期货主力连续数据 ##########")
try:
    result = test_function("futures (获取期货列表)", ak.futures)
except Exception as e:
    print(f"futures 函数测试失败: {e}")

print("\n\n########## 测试4: ak.futures_comm_realtime 品种实时行情 ##########")
for symbol, name in test_contracts.items():
    print(f"\n--- {symbol} ({name}) ---")
    test_function(
        f"futures_comm_realtime({symbol})",
        ak.futures_comm_realtime,
        symbol=symbol
    )

print("\n\n########## 测试5: ak.futures_zh_min_sina 日线数据 ##########")
for symbol, name in test_contracts.items():
    print(f"\n--- {symbol} ({name}) ---")
    test_function(
        f"futures_zh_min_sina({symbol}0, 'daily')",
        ak.futures_zh_min_sina,
        symbol=f"{symbol}0",
        period="daily",
        adjust="qfq"
    )

print("\n\n########## 测试6: ak.futures_zh_daily_sina 特定合约代码 ##########")
# 尝试具体的期货合约代码
specific_contracts = ['M2405', 'SS2405', 'C2405', 'OI2405', 'JM2405']
for contract in specific_contracts:
    symbol = contract[0]
    name = test_contracts.get(symbol, symbol)
    print(f"\n--- {contract} ({name}) ---")
    test_function(
        f"futures_zh_daily_sina({contract})",
        ak.futures_zh_daily_sina,
        symbol=contract
    )

print("\n\n########## 测试7: ak.get_futures_zh_daily ##########")
try:
    # 尝试日线数据接口
    test_function("futures_zh_daily (列表)", ak.futures_zh_daily)
except Exception as e:
    print(f"futures_zh_daily 失败: {e}")

print("\n\n########## 测试8: ak.futures_zh_a_hist 分品种历史数据 ##########")
for symbol, name in test_contracts.items():
    print(f"\n--- {symbol} ({name}) ---")
    try:
        result = ak.futures_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date="20240101",
            end_date="20240323",
            adjust="qfq"
        )
        if result is None:
            print(f"  [❌] 返回 None")
        else:
            import pandas as pd
            if isinstance(result, pd.DataFrame):
                print(f"  [✅] DataFrame, shape: {result.shape}")
                print(f"  列名: {list(result.columns)}")
                print(f"  前3行:\n{result.head(3)}")
            else:
                print(f"  [⚠️] 返回类型: {type(result)}")
                print(f"  内容: {str(result)[:300]}")
    except Exception as e:
        print(f"  [❌] 错误: {e}")

print("\n\n########## 测试完成 ##########")
