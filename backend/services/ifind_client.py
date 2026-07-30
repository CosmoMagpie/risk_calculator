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


def set_ifind_credentials(user_name: str, password: str) -> None:
    """设置 iFinD 登录凭据（保存到环境变量与缓存状态）"""
    os.environ["IFIND_USER_NAME"] = user_name
    os.environ["IFIND_PASSWORD"] = password
    _LOGIN_STATUS["user_name"] = user_name
    _LOGIN_STATUS["password"] = password
    print(f"[iFinD] 凭据已更新: {user_name}")


def clear_ifind_credentials() -> None:
    """清除 iFinD 登录凭据"""
    os.environ.pop("IFIND_USER_NAME", None)
    os.environ.pop("IFIND_PASSWORD", None)
    _LOGIN_STATUS["logged_in"] = False
    _LOGIN_STATUS["user_name"] = None
    _LOGIN_STATUS["password"] = None
    print("[iFinD] 凭据已清除")


def get_ifind_login_status() -> dict:
    """获取当前 iFinD 登录状态"""
    return dict(_LOGIN_STATUS)


# =============== A股代码后缀归一化（便于 iFinD 识别）==============

_A_SHARE_SUFFIXES = (".SH", ".SZ", ".BJ")


def normalize_a_share_code(code: str) -> str:
    """
    将 A 股代码统一补充为 iFinD 可识别的后缀格式。

    规则（仅针对 A 股 6 位数字代码，不区分境内/境外市场）：
      - 已带 .SH/.SZ/.BJ 后缀：直接返回
      - 6 位数字：
          0/3/68/69 开头 → 补充 .SZ
          6/9 开头      → 补充 .SH
          其他          → 保持原样
      - 非 6 位数字或已带其他后缀：保持原样

    Args:
        code: 标的代码，如 '000300', '000300.SH', 'AAPL.O'

    Returns:
        归一化后的代码
    """
    if not code or not isinstance(code, str):
        return code
    code = code.strip().upper()
    if not code:
        return code
    if code.endswith(_A_SHARE_SUFFIXES):
        return code
    if len(code) == 6 and code.isdigit():
        if code.startswith(("0", "3", "68", "69")):
            return code + ".SZ"
        if code.startswith(("6", "9")):
            return code + ".SH"
    return code


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
    underlying_code = normalize_a_share_code(underlying_code)
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
    spot_price: Optional[float] = None,
    strike_price: Optional[float] = None,
    risk_free_rate: float = 0.02,
    days_to_expiry: Optional[int] = None,
    option_type: str = 'call',
):
    """
    获取场内期权希腊字母值

    优先通过 iFinD API 获取；若 API 不可用，回退到本地 Black-Scholes 模型估算。

    Args:
        option_code: 期权代码（iFinD 格式，如 '10011855' 或 '10011855.SH'），为空时仅尝试本地计算
        greek_letter: 'delta' | 'gamma' | 'vega' | 'theta' | 'rho'
        spot_price: 标的现价（本地模型必需）
        strike_price: 行权价（本地模型必需）
        risk_free_rate: 无风险利率，默认 2%
        days_to_expiry: 距到期天数（本地模型必需）
        option_type: 'call' | 'put'，默认 'call'

    Returns:
        (Optional[float], Optional[str]): (希腊字母值, 错误信息)。
            成功时 error_msg 为 None；失败时 value 为 None，error_msg 含失败原因。
    """
    # ---- 优先尝试 iFinD API ----
    if option_code and str(option_code).strip() != "" and ifind_login():
        map_dict = {
            'delta': 'ths_delta_option',
            'gamma': 'ths_gamma_option',
            'vega': 'ths_vega_option',
            'theta': 'ths_theta_option',
            'rho': 'ths_rho_option',
        }
        greek_wanted = map_dict.get(greek_letter)
        if greek_wanted is None:
            msg = f"不支持的希腊字母: {greek_letter}"
            print(f"[iFinD] {msg}")
            return None, msg
        else:
            # 尝试多种代码格式：原代码 → 原代码.SH → (已带后缀则不再追加)
            code = str(option_code).strip()
            code_variants = [code]
            if not code.endswith('.SH') and not code.endswith('.SZ'):
                code_variants.append(code + '.SH')

            current_date = datetime.now().strftime('%Y-%m-%d')
            conservative_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

            iFind_errors = []  # 收集各变体尝试的错误信息

            for variant in code_variants:
                try:
                    result = THS_DS(
                        variant,
                        greek_wanted,
                        '100',
                        'Days:Tradedays,Fill:Blank',
                        conservative_date,
                        current_date,
                    )
                    if result is None:
                        iFind_errors.append(f"代码 {variant}: THS_DS 返回 None")
                        continue
                    if hasattr(result, 'errorcode') and result.errorcode != 0:
                        err_code = result.errorcode
                        err_msg = getattr(result, 'errmsg', '未知错误')
                        iFind_errors.append(f"代码 {variant}: 错误码={err_code}, 信息={err_msg}")
                        continue

                    data = pd.DataFrame(result.data)
                    if data.empty or greek_wanted not in data.columns:
                        iFind_errors.append(f"代码 {variant}: 返回数据为空或无 {greek_wanted} 列")
                        continue

                    values = pd.to_numeric(data[greek_wanted].tolist(), errors='coerce')
                    for val in reversed(values):
                        if not np.isnan(val):
                            if variant != code:
                                print(f"[iFinD] Greeks 通过 {variant} 获取成功 "
                                      f"(原始代码 {code} 无有效值)")
                            return float(val), None

                except Exception as e:
                    iFind_errors.append(f"代码 {variant}: 异常={e}")
                    continue

            # 所有尝试均失败，汇总错误信息
            error_detail = "; ".join(iFind_errors) if iFind_errors else "所有代码格式均无有效数据"
            msg = (f"期权代码 {option_code} 的 {greek_letter} 获取失败: {error_detail}。"
                   f"请确认: 1) 代码是否正确 2) iFinD 终端是否正常 3) 该期权合约数据是否可用")
            print(f"[iFinD] {msg}")
            return None, msg

    elif option_code and str(option_code).strip() != "" and not ifind_login():
        return None, "iFinD 未登录，请先在侧边栏登录 iFinD 终端"

    # ---- 回退：本地 Black-Scholes 模型 ----
    if spot_price and strike_price and days_to_expiry and spot_price > 0 and strike_price > 0:
        bs_val = _calc_bs_greek(
            spot_price, strike_price, risk_free_rate,
            days_to_expiry, greek_letter, option_type,
        )
        if bs_val is not None:
            return bs_val, None  # BS 本地计算成功，无错误

    return None, "未提供期权代码，且缺少本地 BS 模型所需参数（标的价格、行权价、到期天数）"


def _calc_bs_greek(
    S: float, K: float, r: float, T_days: int,
    greek: str, option_type: str = 'call',
) -> Optional[float]:
    """
    使用 Black-Scholes 模型计算希腊字母（辅助函数）

    Args:
        S: 标的现价
        K: 行权价
        r: 无风险利率（年化）
        T_days: 距到期天数
        greek: 'delta' | 'gamma' | 'vega' | 'theta' | 'rho'
        option_type: 'call' | 'put'

    Returns:
        float: 希腊字母值
    """
    from scipy.stats import norm

    T = T_days / 365.0
    if T <= 0:
        return None

    # 估算波动率（简单假设 20% 年化）
    sigma = 0.20

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    sign = 1 if option_type == 'call' else -1

    if greek == 'delta':
        # call: N(d1);  put: N(d1) - 1
        return float(norm.cdf(d1) if option_type == 'call' else norm.cdf(d1) - 1)
    elif greek == 'gamma':
        return float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
    elif greek == 'vega':
        # vega 通常按 1% 波动率变化报价，即导数 / 100
        return float(S * norm.pdf(d1) * np.sqrt(T) / 100)
    elif greek == 'theta':
        # theta 按每天衰减（年化 derivative / 365）
        theta_call = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
                      - r * K * np.exp(-r * T) * norm.cdf(d2))
        theta_put = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
                     + r * K * np.exp(-r * T) * norm.cdf(-d2))
        return float((theta_call if option_type == 'call' else theta_put) / 365)
    elif greek == 'rho':
        # rho 按 1% 利率变化报价
        return float(K * T * np.exp(-r * T) * norm.cdf(sign * d2) * sign / 100)
    else:
        return None
