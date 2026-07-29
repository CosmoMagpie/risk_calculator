# ============================================================
# backend/services/ifind_client.py - 同花顺 iFinD 数据接口
# ============================================================

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from iFinDPy import *


# =============== iFinD 数据接口函数 ===============

def ifind_login():
    """
    登录同花顺 iFinD 数据终端

    【用途】在使用 THS_HQ、THS_DS 等接口获取实时数据前，必须先调用此函数完成身份认证
    Returns:
        bool: 登录成功返回 True，失败返回 False
    """
    thsLogin = THS_iFinDLogin('glzq703','96998XuY')
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
        greek_value_list = pd.to_numeric(data[greek_wanted].tolist(), errors='coerce')
        # 从后往前取第一个有效值，避免当日未收盘导致最新值为空
        for val in reversed(greek_value_list):
            if not np.isnan(val):
                return float(val)
        print("Greeks 数据均为空")
        return None

    except Exception as e:
        print(f"获取期权greeks值失败: {e}")
        return None
