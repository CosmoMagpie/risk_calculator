# ============================================================
# backend/services/ifind_client.py - 同花顺 iFinD 数据接口
# ============================================================

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from iFinDPy import (
    THS_iFinDLogin,
    THS_iFinDLogout,
    THS_HQ,
    THS_DS,
    THS_RQ,
)


# =============== 登录状态管理 ===============

_LOGIN_STATUS = {
    "logged_in": False,
    "user_name": None,
    "password": None,
}


def _get_credentials() -> tuple:
    """
    读取 iFinD 登录凭据，优先级：环境变量 > 代码内空值

    Returns:
        (user_name, password)
    """
    user_name = os.environ.get("IFIND_USER_NAME", "")
    password = os.environ.get("IFIND_PASSWORD", "")
    return user_name, password


def ifind_login(force: bool = False) -> bool:
    """
    登录同花顺 iFinD 数据终端（带登录状态缓存）

    Args:
        force: 是否强制重新登录

    Returns:
        bool: 登录成功返回 True，失败或凭据为空返回 False
    """
    if _LOGIN_STATUS["logged_in"] and not force:
        return True

    user_name, password = _get_credentials()
    if not user_name or not password:
        print("[iFinD] 未配置登录凭据（IFIND_USER_NAME / IFIND_PASSWORD），跳过登录")
        return False

    try:
        thsLogin = THS_iFinDLogin(user_name, password)
        print(f"[iFinD] login result: {thsLogin}")
        if thsLogin in {0, -201}:
            _LOGIN_STATUS["logged_in"] = True
            _LOGIN_STATUS["user_name"] = user_name
            _LOGIN_STATUS["password"] = password
            print("[iFinD] 登录成功")
            return True
        else:
            print(f"[iFinD] 登录失败，错误码: {thsLogin}")
            return False
    except Exception as e:
        print(f"[iFinD] 登录异常: {e}")
        return False


def ifind_logout() -> None:
    """登出 iFinD 并清空缓存状态"""
    global _LOGIN_STATUS
    try:
        THS_iFinDLogout()
    except Exception as e:
        print(f"[iFinD] 登出异常: {e}")
    _LOGIN_STATUS = {"logged_in": False, "user_name": None, "password": None}


# =============== 基础数据接口 ===============

def get_underlying_price_series(
    underlying_code: str,
    price_type: str = "close",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, List[float]]:
    """
    获取产品底层过去一年的价格数据（通过同花顺 iFinD API）

    Args:
        underlying_code: 同花顺代码，如 'AAPL.O', '000300.SH'
        price_type: 价格类型，如 'close', 'open', 'high', 'low', 'pre_close'
        start_date: 开始日期 'YYYY-MM-DD'，默认一年前
        end_date: 结束日期 'YYYY-MM-DD'，默认今天

    Returns:
        Dict[str, List[float]]: {"代码": [价格列表]}，若获取失败返回空列表
    """
    if not ifind_login():
        return {underlying_code: []}

    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    try:
        result = THS_HQ(underlying_code, price_type, 'fill:Omit', start_date, end_date)
        if result is None:
            print("[iFinD] THS_HQ 返回 None")
            return {underlying_code: []}
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"[iFinD] THS_HQ 失败，错误码: {result.errorcode}, {result.errmsg}")
            return {underlying_code: []}

        data = pd.DataFrame(result.data)
        if data.empty:
            print("[iFinD] THS_HQ 返回空数据")
            return {underlying_code: []}

        return {underlying_code: data[price_type].tolist()}

    except Exception as e:
        print(f"[iFinD] 获取价格序列失败: {e}")
        return {underlying_code: []}


def calculate_correlation_between_price_series(
    otc_code: str,
    otc_prices: Dict[str, List[float]],
    hedge_code: str,
    hedge_prices: Dict[str, List[float]],
) -> float:
    """
    计算两个标的价格序列的皮尔逊相关系数

    Returns:
        float: 相关系数（-1 到 1），数据不足返回 np.nan
    """
    otc_series = pd.Series(otc_prices.get(otc_code, []))
    hedge_series = pd.Series(hedge_prices.get(hedge_code, []))
    if len(otc_series) < 2 or len(hedge_series) < 2:
        return np.nan

    min_len = min(len(otc_series), len(hedge_series))
    corr = otc_series.iloc[:min_len].corr(hedge_series.iloc[:min_len])
    return corr if corr is not None else np.nan


# =============== 现货价格与 Greeks 接口 ===============

def is_trading_time() -> bool:
    """
    判断当前是否处于 A 股交易时间（含集合竞价）
    """
    now = datetime.now()
    if now.weekday() >= 5:  # 周六、周日
        return False

    t = now.time()
    morning = datetime.strptime("09:30:00", "%H:%M:%S").time() <= t <= datetime.strptime("11:30:00", "%H:%M:%S").time()
    afternoon = datetime.strptime("13:00:00", "%H:%M:%S").time() <= t <= datetime.strptime("15:00:00", "%H:%M:%S").time()
    auction = datetime.strptime("09:15:00", "%H:%M:%S").time() <= t <= datetime.strptime("09:25:00", "%H:%M:%S").time()
    return morning or afternoon or auction


def get_realtime_price(ifind_code: str) -> Optional[float]:
    """
    使用 THS_RQ 获取标的实时最新价

    Returns:
        float: 最新价，失败返回 None
    """
    if not ifind_login():
        return None

    try:
        result = THS_RQ(ifind_code, 'latest')
        if result is None:
            return None
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"[iFinD] THS_RQ 失败 {ifind_code}: {result.errorcode}, {result.errmsg}")
            return None

        data = pd.DataFrame(result.data)
        if data.empty:
            return None

        price = data['latest'].iloc[0]
        if pd.isna(price):
            return None
        return float(price)

    except Exception as e:
        print(f"[iFinD] 获取实时价格失败 {ifind_code}: {e}")
        return None


def get_latest_close_price(
    ifind_code: str,
    spot_type: str,
    market: str = 'CN',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[float]:
    """
    获取标的最近交易日收盘价（非交易时间或实时接口失败时回落）

    Args:
        ifind_code: 同花顺代码
        spot_type: 'stock' | 'index' | 'fund' | 'future' | 'spot' | 'option'
        market: 'CN' | 'US' | 'HK' | 'EN' | 'Other'
        start_date: 查询起始日，默认最近 14 天
        end_date: 查询结束日，默认今天

    Returns:
        float: 最新有效收盘价，失败返回 None
    """
    if not ifind_login():
        return None

    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

    # 映射：现货类型 + 市场 -> iFinD 字段
    mapping = {
        'stockCN': 'ths_close_price_stock',
        'stockUS': 'ths_close_price_uss',
        'stockHK': 'ths_close_price_hks',
        'stockEN': 'ths_close_gbs',
        'stockOther': 'close_price',
        'index': 'ths_close_price_index',
        'fund': 'ths_close_price_fund',
        'future': 'ths_close_price_future',
        'spot': 'ths_close_price_spot',
        'option': 'ths_close_price_option',
    }

    if spot_type == 'stock' and market in ('CN', 'US', 'HK', 'EN'):
        type_market = f"stock{market}"
    elif spot_type == 'stock':
        type_market = 'stockOther'
    else:
        type_market = spot_type

    price_type = mapping.get(type_market)
    if price_type is None:
        print(f"[iFinD] 未找到 {spot_type}/{market} 对应的价格字段")
        return None

    try:
        result = THS_DS(
            ifind_code,
            price_type,
            '100',
            'Days:Tradedays,Fill:Blank',
            start_date,
            end_date,
        )
        if result is None:
            return None
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"[iFinD] THS_DS 失败 {ifind_code}: {result.errorcode}, {result.errmsg}")
            return None

        data = pd.DataFrame(result.data)
        if data.empty:
            return None

        col_names = data.columns.tolist()
        price_col = col_names[-1]
        prices = pd.to_numeric(data[price_col].tolist(), errors='coerce')
        for val in reversed(prices):
            if not np.isnan(val):
                return float(val)
        return None

    except Exception as e:
        print(f"[iFinD] 获取收盘价失败 {ifind_code}: {e}")
        return None


def get_underlying_spot_price(
    ifind_code: str,
    spot_type: str,
    market: str = 'CN',
) -> Optional[float]:
    """
    获取标的物现货价格：交易时间内优先实时价，非交易时间回落最近收盘价

    Args:
        ifind_code: 同花顺代码
        spot_type: 'stock' | 'index' | 'fund' | 'future' | 'spot' | 'option'
        market: 'CN' | 'US' | 'HK' | 'EN' | 'Other'

    Returns:
        float: 价格，失败返回 None
    """
    if is_trading_time():
        realtime = get_realtime_price(ifind_code)
        if realtime is not None:
            return realtime
    return get_latest_close_price(ifind_code, spot_type, market)


def get_onsite_option_greeks(
    option_code: Optional[str],
    greek_letter: str = 'delta',
) -> Optional[float]:
    """
    获取场内期权希腊字母值（通过同花顺 iFinD API）

    Args:
        option_code: 期权代码，为空时直接返回 None
        greek_letter: 'delta' | 'gamma' | 'vega' | 'theta' | 'rho'

    Returns:
        float: 期权当日希腊字母值，获取失败返回 None
    """
    if option_code is None or str(option_code).strip() == "":
        return None

    if not ifind_login():
        return None

    map_dict = {
        'delta': 'ths_delta_option',
        'gamma': 'ths_gamma_option',
        'vega': 'ths_vega_option',
        'theta': 'ths_theta_option',
        'rho': 'ths_rho_option',
    }
    greek_wanted = map_dict.get(greek_letter)
    if greek_wanted is None:
        print(f"[iFinD] 不支持的希腊字母: {greek_letter}")
        return None

    current_date = datetime.now().strftime('%Y-%m-%d')
    conservative_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

    try:
        result = THS_DS(
            option_code,
            greek_wanted,
            '100',
            'Days:Tradedays,Fill:Blank',
            conservative_date,
            current_date,
        )
        if result is None:
            return None
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"[iFinD] THS_DS Greeks 失败 {option_code}: {result.errorcode}, {result.errmsg}")
            return None

        data = pd.DataFrame(result.data)
        if data.empty:
            return None

        values = pd.to_numeric(data[greek_wanted].tolist(), errors='coerce')
        for val in reversed(values):
            if not np.isnan(val):
                return float(val)
        return None

    except Exception as e:
        print(f"[iFinD] 获取 Greeks 失败 {option_code}: {e}")
        return None
