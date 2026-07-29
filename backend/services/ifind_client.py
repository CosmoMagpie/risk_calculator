# ============================================================
# backend/services/ifind_client.py - 同花顺 iFinD 数据接口
# ============================================================

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from iFinDPy import *

LOGIN_INFO = {'user_name': 'glzq703', 'password': '96998XuY'}

# =============== iFinD 数据接口函数 ===============

def ifind_login(user_name: str = LOGIN_INFO['user_name'], password: str = LOGIN_INFO['password']):
    """
    登录同花顺 iFinD 数据终端

    【用途】在使用 THS_HQ、THS_DS 等接口获取实时数据前，必须先调用此函数完成身份认证
    Returns:
        bool: 登录成功返回 True，失败返回 False
    """
    thsLogin = THS_iFinDLogin(user_name, password)
    print(thsLogin)
    if thsLogin in {0, -201}:
        print('登录成功')
        return True
    else:
        print('登录失败')
        return False


def get_underlying_price_series(underlying_code: str,
                         price_type: str = "close",
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> Dict[str, List[float]]:
    """
    获取产品底层过去一年的价格数据（通过同花顺 iFinD API）

    Args:
        underlying_code: 同花顺代码，如 'AAPL.O', '000300.SH'
        start_date: 开始日期 'YYYY-MM-DD'，默认一年前
        end_date: 结束日期 'YYYY-MM-DD'，默认今天
        price_type: 价格类型，如 'close', 'open', 'high', 'low', 'pre_close'
    Returns:
        Dict[str, List[float]]: {"代码": [价格列表]}，若获取失败返回空列表
    """
    if not ifind_login():
        print("登录失败")
        return {underlying_code: []}
    # 获取当前日期与提前一年起始日期
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    try:
        # 调用 THS_HQ 获取行情数据
        result = THS_HQ(underlying_code, price_type, 'fill:Omit', start_date, end_date)
        if result is None:
            print("THS_DS 返回 None")
            return {underlying_code: []}
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"获取数据失败，错误码: {result.errorcode}, 错误信息: {result.errmsg}")
            return {underlying_code: []}
        data = pd.DataFrame(result.data)
        if data.empty:
            print("获取数据为空")
            return {underlying_code: []}
        return {underlying_code: data[price_type].tolist()}

    except Exception as e:
        print(f"获取底层价格数据失败: {e}")
        return {underlying_code: []}


def calculate_correlation_between_price_series(otc_code: str, otc_prices: Dict[str, List[float]],
    hedge_code: str, hedge_prices: Dict[str, List[float]]) -> float:
    """
    计算两个标的价格序列的皮尔逊相关系数（Pearson correlation）

    【用途】当客户端标的与对冲工具标的代码不同时（如用中证500期货对冲沪深300期权），
           通过历史价格相关性判断是否可视为"同一标的"

    Args:
        otc_code: 场外合约代码
        otc_prices: 场外合约价格字典
        hedge_code: 对冲工具代码
        hedge_prices: 对冲工具价格字典
    Returns:
        float: 相关系数（-1到1），数据不足返回 np.nan
    """
    # 提取价格序列
    otc_series = pd.Series(otc_prices.get(otc_code, []))
    hedge_series = pd.Series(hedge_prices.get(hedge_code, []))
    if len(otc_series) < 2 or len(hedge_series) < 2:
        return np.nan  # 数据不足2个点，无法计算相关，返回 NaN（Not a Number）

    # 对齐长度：取两者较短的
    min_len = min(len(otc_series), len(hedge_series))
    otc_aligned = otc_series.iloc[:min_len]
    hedge_aligned = hedge_series.iloc[:min_len]
    corr = otc_aligned.corr(hedge_aligned)
    return corr if corr is not None else np.nan


# ==== 获取标的价格函数组，服务于计算压力测试最大损失 ====
def is_trading_time() -> bool:
    """
    判断当前是否处于 A 股交易时间
    Returns:
        bool: True 表示在交易时间内，False 表示不在
    """
    now = datetime.now()
    if now.weekday() >= 5:  # 5=周六, 6=周日
        return False
    current_time = now.time()
    # 上午
    morning_start = datetime.strptime("09:30:00", "%H:%M:%S").time()
    morning_end = datetime.strptime("11:30:00", "%H:%M:%S").time()
    # 下午
    afternoon_start = datetime.strptime("13:00:00", "%H:%M:%S").time()
    afternoon_end = datetime.strptime("15:00:00", "%H:%M:%S").time()
    # 集合竞价时段也视为可获取实时数据（9:15-9:25）
    auction_start = datetime.strptime("09:15:00", "%H:%M:%S").time()
    auction_end = datetime.strptime("09:25:00", "%H:%M:%S").time()
    
    if (morning_start <= current_time <= morning_end or
        afternoon_start <= current_time <= afternoon_end or
        auction_start <= current_time <= auction_end):
        return True
    return False


def get_underlying_spot_price(ifind_code: str, spot_type: str, market: str) -> Optional[float]:
    """
    获取标的物实时现货价格或收盘价
    
    Args:
        ifind_code: 同花顺代码，如 'AAPL.O', '000300.SH'
        spot_type: 现货类型，如 'stock', 'index', 'fund' , 'future' , 'spot'(用于商品)等大类
        market: 市场类型，如 'CN', 'US', 'HK' ,'JP' , 'EN' 等
    
    Returns:
        float: 标的物现货价格
               - 交易时间内：返回实时价格
               - 非交易时间：返回最近收盘价
    """
    if not ifind_login():
        print("登录失败")
        return None
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    conservative_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    # ====== 判断是否在交易时间内 ======
    if is_trading_time():
        print(f"当前处于交易时间，使用 THS_RQ 获取实时价格")
        realtime_price = get_realtime_price(ifind_code)
        if realtime_price is not None:
            return realtime_price
        # 实时价格无权限或获取失败，退而求其次使用历史数据获取最新收盘价
        print("正在获取最近交易日收盘价...")
        return get_latest_close_price(ifind_code, spot_type, conservative_date, current_date, market)
    else:
        print(f"当前非交易时间，正在使用历史数据获取最新收盘价...")
        return get_latest_close_price(ifind_code, spot_type, conservative_date, current_date, market)


def get_realtime_price(ifind_code: str) -> Optional[float]:
    """
    使用 THS_RQ 获取实时价格
    
    Args:
        ifind_code: 同花顺代码
        spot_type: 现货类型
        market: 市场类型
    
    Returns:
        float: 实时价格，失败返回 None
    """
    try:
        result = THS_RQ(ifind_code, 'latest')
        if result is None:
            print("THS_RQ 返回 None")
            return None
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            if result.errorcode == -4230 or result.errorcode == -4225:
                print(f"无当前标的：{ifind_code} 实时行情权限（错误码：{result.errorcode}），将显示最近交易日收盘价")
            elif result.errorcode == -4001:
                print(f"当前标的：{ifind_code} 无实时行情数据（错误码：{result.errorcode}），将显示最近交易日收盘价")
            else:
                print(f"THS_RQ 获取数据失败，错误码: {result.errorcode}, 错误信息: {result.errmsg}")
            return None
        data = pd.DataFrame(result.data)
        
        # 检查数据是否为空
        if data.empty:
            print("THS_RQ 获取数据为空")
            return None
        
        # 提取价格
        price = data['latest'].iloc[0]
        if pd.isna(price):
            print(f"实时价格为 NaN")
            return None
        return float(price)
    
    except Exception as e:
        print(f"获取实时价格失败: {e}")
        return None


def get_latest_close_price(ifind_code: str, spot_type: str, start_date: str, end_date: str, market: str = 'CN') -> Optional[float]:
    """
    获取最新的收盘价（非交易时间使用）
    
    Args:
        ifind_code: 同花顺代码
        spot_type: 现货类型
        market: 市场类型
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        float: 最新有效价格，失败返回 None
    """

    # 映射字典：现货类型 + 市场组合 -> iFinD 函数价格类型字段
    mapping_dict = {
        'stockCN': 'ths_close_price_stock', # A股股票
        'stockUS': 'ths_close_price_uss', # 美股股票
        'stockHK': 'ths_close_price_hks', # 港股股票
        'stockEN': 'ths_close_gbs', # 英国股票
        'stockOther': 'close_price', # 其他股票
        'index': 'ths_close_price_index', # 指数
        'fund': 'ths_close_price_fund', # 基金
        'future': 'ths_close_price_future', # 期货
        'spot': 'ths_close_price_spot', # 现货
        'option': 'ths_close_price_option' # 期权，以防止用期权作标的的奇葩东西
    }
    # 建立现货类型 + 市场组合二元组，用于匹配iFinD函数价格类型字段 
    type_market = spot_type + ""  # 非股票

    if spot_type == 'stock':  # 股票需要区分市场
        if market == 'CN' or market == 'US' or market == 'HK' or market == 'EN':
            type_market = spot_type + market
        else:
            type_market = spot_type + 'Other'
    price_type = mapping_dict.get(type_market, None)

    try:
        result = THS_DS(ifind_code, price_type, '100', 'Days:Tradedays,Fill:Blank', start_date, end_date)
        if result is None:
            print("THS_DS 返回 None")
            return None
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"THS_DS 获取数据失败，错误码: {result.errorcode}, 错误信息: {result.errmsg}")
            return None
        data = pd.DataFrame(result.data)
        if data.empty:
            print("THS_DS 获取数据为空")
            return None
        
        col_names = data.columns.tolist()
        price_col = col_names[-1]
        prices = data[price_col].tolist()
        if not prices:
            print("无有效价格数据")
            return None
        if np.isnan(prices[-1]):
            return prices[-2]
        else:
            return prices[-1]

    except Exception as e:
        print(f"获取历史价格失败: {e}")
        return None


# ====== 期权信息获取函数 ======
def get_onsite_option_greeks(option_code: str, greek_letter: str = 'delta') -> Optional[float]:
    """
    获取场内期权希腊字母值（通过同花顺 iFinD API）

    Args:
        option_code: 期权代码
        greek_letter: 希腊字母，如 'delta', 'gamma', 'vega', 'theta', 'rho'
    Returns:
        float: 期权当日希腊字母值，若当天交易未结束，返回前一交易日值；获取失败返回 None
    """
    if not ifind_login():
        print("登录失败")
        return None
    # 5大常用希腊字母映射字典
    map_dict = {'delta': 'ths_delta_option','gamma': 'ths_gamma_option','vega': 'ths_vega_option','theta': 'ths_theta_option','rho': 'ths_rho_option'}
    greek_wanted = map_dict.get(greek_letter, None)
    # 当前日期和上一交易日的保守自然日（-14天）
    current_date = datetime.now().strftime('%Y-%m-%d')
    conservative_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    if greek_wanted is None:
        print(f"未找到{greek_letter}对应的greeks值")
        return None

    try:
        greeklist = THS_DS(option_code, greek_wanted,'100','Days:Tradedays,Fill:Blank', conservative_date, current_date)
        if greeklist is None:
            print("THS_DS 返回 None")
            return None
        if hasattr(greeklist, 'errorcode') and greeklist.errorcode != 0:
            print(f"获取数据失败，错误码: {greeklist.errorcode}, 错误信息: {greeklist.errmsg}")
            return None
        data = pd.DataFrame(greeklist.data)
        if data.empty:
            print("获取数据为空")
            return None
        greek_value_list = data[greek_wanted].tolist()
        if np.isnan(greek_value_list[-1]):
            greek_value = greek_value_list[-2]
        else:
            greek_value = greek_value_list[-1]
        return greek_value

    except Exception as e:
        print(f"获取期权greeks值失败: {e}")
        return None


# =============== 以下为测试代码 ===============


ifind_login()
result1 = THS_DS('AEX.GI', 'ths_close_price_index', '100', 'Days:Tradedays,Fill:Blank','2026-07-14','2026-07-28')
result2 = THS_DS('510130.SH', 'ths_close_price_fund', '100', 'Days:Tradedays,Fill:Blank','2026-07-14','2026-07-28')
result3 = THS_DS('SC2703.INE', 'ths_close_price_future', '100', 'Days:Tradedays,Fill:Blank','2026-07-14','2026-07-28')
result4 = THS_DS('NVDA.O', 'ths_close_price_uss', '100', 'Days:Tradedays,Fill:Blank','2026-07-14','2026-07-28')
print(result1)
print(result2)
print(result3)
print(result4)

a = get_underlying_spot_price('000001.CCI', 'index', 'CN')
print(f"现货价格: {a}")

b = get_onsite_option_greeks('90007054.SZ', 'delta')
print(f" delta值: {b}")

c = THS_DS('000001.CCI', 'ths_close_price_index', '100', 'Days:Tradedays,Fill:Blank','2026-07-14','2026-07-29')
print(c)

d = THS_HQ('10010973.SH', 'close', 'fill:Omit', '2025-07-29', '2026-07-29')
print(d)
