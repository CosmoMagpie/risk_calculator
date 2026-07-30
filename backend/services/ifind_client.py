# ============================================================
# backend/services/ifind_client.py - 同花顺 iFinD 数据接口
# ============================================================

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ========== iFinD 导入（带容错处理）==========
# 若 iFinDPy 未安装，系统仍可运行，但 iFinD 相关功能会返回空数据
try:
    from iFinDPy import (
        THS_iFinDLogin,
        THS_iFinDLogout,
        THS_HQ,
        THS_DS,
        THS_RQ,
    )
    _IFIND_AVAILABLE = True
except ImportError:
    _IFIND_AVAILABLE = False
    print("[iFinD] 警告：iFinDPy 未安装，将跳过实时行情和历史数据获取。请运行 'pip install iFinDPy' 安装。")


# =============== 登录状态管理 ===============
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

'''_LOGIN_STATUS = {
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
    user_name = os.environ.get("IFIND_USER_NAME", "glzq703")
    password = os.environ.get("IFIND_PASSWORD", "96998XuY")
    return user_name, password


def ifind_login(force: bool = False) -> bool:
    """
    登录同花顺 iFinD 数据终端（带登录状态缓存）

    Args:
        force: 是否强制重新登录

    Returns:
        bool: 登录成功返回 True，失败或凭据为空返回 False
    """
    if not _IFIND_AVAILABLE:
        print("[iFinD] iFinDPy 未安装，无法登录")
        return False

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
            print(f"[iFinD] 登录失败，错误码: {thsLogin}。请检查账号密码是否正确，或联系IT部门确认iFinD服务状态")
            return False
    except Exception as e:
        print(f"[iFinD] 登录异常: {e}")
        return False


def ifind_logout() -> None:
    """登出 iFinD 并清空缓存状态"""
    global _LOGIN_STATUS
    if not _IFIND_AVAILABLE:
        _LOGIN_STATUS = {"logged_in": False, "user_name": None, "password": None}
        return
    try:
        THS_iFinDLogout()
    except Exception as e:
        print(f"[iFinD] 登出异常: {e}")
    _LOGIN_STATUS = {"logged_in": False, "user_name": None, "password": None}
'''

# =============== 基础数据接口 ===============

def get_underlying_price_series(underlying_code: str, price_type: str = "close", start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, List[float]]:
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
    if not _IFIND_AVAILABLE:
        print(f"[iFinD] iFinDPy 未安装，无法获取 {underlying_code} 的历史价格数据")
        return {underlying_code: []}

    login_ok = ifind_login()
    if not login_ok:
        print(f"[iFinD] 登录失败，无法获取 {underlying_code} 的价格数据")
        return {underlying_code: []}

    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    try:
        result = THS_HQ(underlying_code, price_type, 'fill:Omit', start_date, end_date)
        if result is None:
            print(f"[iFinD] THS_HQ 返回 None，代码: {underlying_code}，请检查代码格式是否正确")
            return {underlying_code: []}
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"[iFinD] THS_HQ 失败，代码: {underlying_code}，错误码: {result.errorcode}, 错误信息: {getattr(result, 'errmsg', '未知错误')}")
            return {underlying_code: []}

        data = pd.DataFrame(result.data)
        if data.empty:
            print(f"[iFinD] THS_HQ 返回空数据，代码: {underlying_code}")
            return {underlying_code: []}

        return {underlying_code: data[price_type].tolist()}

    except Exception as e:
        print(f"[iFinD] 获取价格序列异常，代码: {underlying_code}，异常: {type(e).__name__}: {e}")
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


def map_underlying_type_to_spot_type(underlying_type: str) -> str:
    """
    将细化标的类型映射为 get_latest_close_price 需要的 spot_type
    
    Args:
        underlying_type: 细化类型，如 'index_component', 'index_fund', 'stock_index_future' 等
        is_equity: 是否为权益类
        
    Returns:
        str: spot_type，可选值：'stock', 'index', 'fund', 'future', 'spot', 'option'
    """
    # ===== 直接映射：根据 underlying_type 前缀或关键词 =====
    
    # 1. 股票类
    if underlying_type in ["index_component", "general_stock", "restricted_stock", "other_stock"]:
        return "stock"
    
    # 2. 指数类（股指期货的标的是指数，但期货本身是 future）
    if underlying_type in ["stock_index_future", "treasury_future"]:
        return "future"
    
    # 3. 大宗商品期货
    if underlying_type == "bulk_commodity_future":
        return "future"
    
    # 4. 大宗商品现货
    if underlying_type == "bulk_commodity":
        return "spot"
    
    # 5. 基金类
    if underlying_type in ["etf", "other_index_fund", "other_equity_fund", "monetary_fund", 
                           "interest_rate_bond_index_fund", "other_non_equity_fund"]:
        return "fund"
    
    # 6. 互换类（价格来源是指数或股票，需要看挂钩标的）
    if underlying_type in ["equity_swap", "interest_rate_swap"]:
        # 互换本身不直接有价格，需要看其挂钩标的类型
        # 这里返回 "index" 作为默认，实际使用时可能需要传入额外的挂钩信息
        return "index"
    
    # 7. 期权类（标的本身是期权，但价格来源是其底层资产）
    if underlying_type in ["equity_short_option", "equity_long_option", 
                           "non_equity_short_option", "non_equity_long_option"]:
        # 期权的价格来源是其挂钩的标的，这里返回 "option" 代表期权自身价格
        # 如果是为了获取标的资产价格，应该使用 underlying_code 对应的标的类型
        return "option"
    
    # 8. 产品类
    if underlying_type in ["single_product", "collection_and_trust"]:
        return "fund"  # 私募基金/信托等视为基金类
    
    # 默认返回 index（最保守的猜测）
    print(f"[警告] 未识别的 underlying_type: {underlying_type}，默认使用 'index'")
    return "index"


def get_spot_type_from_underlying(underlying_type: str, is_equity: bool = True) -> str:
    """
    获取用于价格查询的 spot_type（增强版，带前缀匹配）
    """
    # 定义映射表：关键词 -> spot_type
    KEYWORD_MAP = {
        "stock": "stock",
        "fund": "fund",
        "future": "future",
        "option": "option",
        "swap": "index",      # 互换默认用指数价格
        "commodity": "spot",  # 大宗商品现货
        "index": "index",     # 指数
        "treasury": "future", # 国债期货
        "single_product": "fund",
        "collection_and_trust": "fund",
    }
    
    # 1. 精确匹配
    exact_map = {
        "index_component": "stock",
        "general_stock": "stock",
        "restricted_stock": "stock",
        "other_stock": "stock",
        "etf": "fund",
        "other_index_fund": "fund",
        "other_equity_fund": "fund",
        "monetary_fund": "fund",
        "interest_rate_bond_index_fund": "fund",
        "other_non_equity_fund": "fund",
        "stock_index_future": "future",
        "treasury_future": "future",
        "bulk_commodity_future": "future",
        "bulk_commodity": "spot",
        "equity_swap": "index",
        "interest_rate_swap": "index",
        "equity_short_option": "option",
        "equity_long_option": "option",
        "non_equity_short_option": "option",
        "non_equity_long_option": "option",
        "single_product": "fund",
        "collection_and_trust": "fund",
    }
    
    result = exact_map.get(underlying_type, None)
    if result is not None:
        return result
    
    # 2. 关键词匹配
    for keyword, spot_type in KEYWORD_MAP.items():
        if keyword in underlying_type:
            return spot_type
    
    # 3. 默认
    print(f"[警告] 未识别的 underlying_type: {underlying_type}，默认使用 'index'")
    return "index"


def get_underlying_spot_price(ifind_code: str, underlying_type: str, market: str = 'CN') -> Optional[float]:
    """
    获取标的物实时现货价格或收盘价（通过细化类型自动映射）
    
    Args:
        ifind_code: 同花顺代码，如 'AAPL.O', '000300.SH'
        underlying_type: 细化类型，如 'index_component', 'index_fund', 'stock_index_future' 等
                         来源于 UNDERLYING_TYPE_MAP
        market: 市场类型，如 'CN', 'US', 'HK', 'JP', 'EN' 等
    
    Returns:
        float: 标的物现货价格
    """
    if not ifind_login():
        print("登录失败")
        return None
    
    # ===== 转换 underlying_type -> spot_type =====
    spot_type = get_spot_type_from_underlying(underlying_type)
    print(f"[转换] underlying_type='{underlying_type}' -> spot_type='{spot_type}'")
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    conservative_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    
    # ====== 判断是否在交易时间内 ======
    if is_trading_time():
        print(f"当前处于交易时间，使用 THS_RQ 获取实时价格")
        realtime_price = get_realtime_price(ifind_code)
        if realtime_price is not None:
            return realtime_price
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


def otc_option_delta_calculator(underlying_code: str, underlying_type: str, underlying_market: str, K: float, T: float, option_type: str) -> float:
    """
    计算场外期权的delta值（通过场外期权的delta公式）

    Args:
        underlying_code: 标的物代码
        underlying_type: 标的物类型
        underlying_market: 标的物市场
        K: 看涨期权的执行价格
        T: 期权到期时间（年）
        option_type: 期权类型，如 'call' 或 'put'
    Returns:
        float: 标的物的delta值
    """
    # 获取标的物的实时现货价格
    spot_price = get_underlying_spot_price(underlying_code, underlying_type, underlying_market)
    if spot_price is None:
        print(f"获取标的物实时现货价格失败，标的物代码: {underlying_code}")
        return None

    pass
