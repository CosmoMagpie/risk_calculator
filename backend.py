# ============================================================
# backend.py - 后端核心逻辑
# ============================================================
import numpy as np
import pandas as pd
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import math

from iFinDPy import *


# ===================== 默认参数配置 =====================
DEFAULT_CONFIG = {
    "client": {
        "swap_margin_rate": 0.10,           # 收益互换默认保证金比例 10%
        "option_premium_rate": 0.05,        # 场外期权默认权利金/名义本金比例 5%
        "atm_option_delta": 0.50,           # 平值期权默认Delta
        "equity_swap_delta": 1.0,           # 互换默认Delta 100%
        "income_certificate_delta": 0.0,     # 收益凭证默认Delta 0%
        "income_certificate_term": 1.0,            # 收益凭证默认期限（年）
        "income_certificate_rate": 0.04,           # 收益凭证默认票面利率 4%
    },
    "trade": {
        "futures_margin_rate": 0.12,        # 期货默认保证金比例 12%
        "future_delta": 1.0,               # 期货默认Delta值
        "private_fund_cash_rate": 1.0,      # 私募基金申购资金占用比例 100%
        "etf_cash_rate": 1.0,               # ETF现货资金消耗比例 100%
        "onsite_option_premium_rate": 0.02, # 场内期权默认权利金比例 2%
        "otc_option_premium_rate": 0.03,    # 场外期权默认权利金比例 3%
        "atm_option_delta": 0.5,            # 场内外期权默认Delta值
        "onsite_option_stress_loss": 0.0,   # 卖出压力测试最大损失（万元）
    },
    "firm": {
        "classification_factor": 1.0,
        "HQLA_base": 11_881_000_000,
        "LCR_COF_base": 7_977_000_000,
        "ASF_base": 30_532_000_000,
        "RSF_base": 21_644_000_000,
        "net_capital_base": 16_496_000_000,
        "total_risk_reserve_base": 740_000_000,
        "on_off_balance_total_asset_base": 300_000_000_000,
    }
}


# ===================== 模块A：场外衍生品合约（OtcContract） =====================
@dataclass
class OtcContract:
    """对应模块A：场外衍生品业务要素"""
    # 基础信息
    contract_type: str          # 场外期权 | 场外期权 | 收益互换 | 收益凭证
    direction: str              # "buy" | "sell" (期权) / "long" | "short" (互换)
    notional: float             # 名义本金/发行规模（万元）
    # 标的资产属性
    underlying_type: str        # 指数成分股 | 一般上市公司股票 | 流动受限股票 | 其他股票 | ETF | 股指期货
    underlying_name: Optional[str] = None  # 标的资产名称
    underlying_code: Optional[str] = None  # 标的资产代码
    
    
    # 期权专有属性
    option_type: Optional[str] = None        # 看涨期权 | 看跌期权
    premium_rate: Optional[float] = None        # 权利金比例（%）
    total_premium_amount: Optional[float] = None # 权利金总额（万元）
    single_premium_amount: Optional[float] = None # 单笔期权费（万元）
    contract_multiplier: Optional[float] = None # 合约乘数（元/点）
    contract_size: Optional[float] = None       # 合约份数（份）
    exercise_price: Optional[float] = None      # 行权价（元）
    option_delta: Optional[float] = None        # Delta值（%）
    stress_loss: Optional[float] = None         # 压力测试最大损失（万元），卖出场外期权

    # 收益互换专有属性
    margin_rate: Optional[float] = None         # 保证金比例（%
    margin_amount: Optional[float] = None       # 保证金（万元）
    equity_swap_delta: Optional[float] = None          # Delta值（%）

    # 收益凭证专有属性
    funds_raised: Optional[float] = None        # 募集资金总额（万元），收益凭证用
    income_certificate_delta: Optional[float] = None      # OC Delta值（%），收益凭证用
    
    # 预期创收与期限
    expected_yield: float = 0.08                # 预期年化收益率
    expiry_date: Optional[str] = None           # 合约到期日（YYYY-MM-DD）
    begin_date: Optional[str] = None            # 合约起始日（YYYY-MM-DD）
    term_days: int = 90                         # 合约期限（天）
    
    def get_otc_contract_type(self) -> str:
        """获取合约类型"""
        return self.contract_type
    
    def get_otc_contract_direction(self) -> str:
        """获取交易方向"""
        return self.direction
    
    def get_otc_contract_notional(self) -> float:
        """获取名义本金"""
        return self.notional
    
    def get_otc_underlying_type(self) -> str:
        """获取标的资产类型"""
        return self.underlying_type
    
    def get_otc_underlying_name(self) -> Optional[str]:
        """获取标的资产名称"""
        return self.underlying_name
    
    def get_otc_underlying_code(self) -> Optional[str]:
        """获取标的资产代码"""
        return self.underlying_code
    
    def get_option_type(self) -> Optional[str]:
        """获取期权类型"""
        return self.option_type
    
    def get_premium_rate(self) -> Optional[float]:
        """获取权利金比例"""
        return self.premium_rate
    
    def get_total_premium_amount(self) -> Optional[float]:
        """获取权利金总额"""
        return self.total_premium_amount
    
    def get_single_premium_amount(self) -> Optional[float]:
        """获取单笔期权费"""
        return self.single_premium_amount
    
    def get_contract_size(self) -> Optional[float]:
        """获取合约份数"""
        return self.contract_size
    
    def get_contract_multiplier(self) -> Optional[float]:
        """获取合约乘数"""
        return self.contract_multiplier
    
    def get_exercise_price(self) -> Optional[float]:
        """获取行权价"""
        return self.exercise_price
    
    def get_option_delta(self) -> Optional[float]:
        """获取期权Delta值"""
        return self.option_delta
    
    def get_stress_loss(self) -> Optional[float]:
        """获取压力测试最大损失"""
        return self.stress_loss
    
    def get_margin_rate(self) -> Optional[float]:
        """获取互换保证金比例"""
        return self.margin_rate
    
    def get_margin_amount(self) -> Optional[float]:
        """获取互换保证金"""
        return self.margin_amount
    
    def get_equity_swap_delta(self) -> Optional[float]:
        """获取收益互换Delta值"""
        return self.equity_swap_delta
    
    def get_funds_raised(self) -> Optional[float]:
        """获取募集资金总额"""
        return self.funds_raised
    
    def get_income_certificate_delta(self) -> Optional[float]:
        """获取OC Delta值"""
        return self.income_certificate_delta
    
    def get_income_certificate_rate(self) -> Optional[float]:
        """获取收益凭证票面利率（%）"""
        return self.income_certificate_rate
    
    def get_expected_yield(self) -> float:
        """获取预期年化收益率"""
        return self.expected_yield
    
    def get_expiry_date(self) -> Optional[str]:
        """获取合约到期日"""
        return self.expiry_date
    
    def get_begin_date(self) -> Optional[str]:
        """获取合约起始日"""
        return self.begin_date
    
    def get_term_days(self) -> int:
        """获取合约期限（天）"""
        return self.term_days

    def get_otc_contract_cash_inflow(self) -> float:
        """计算场外合约首日现金净流入（万元，正值=流入）"""
        if (self.contract_type == "call_option" or self.contract_type == "put_option"):
            if self.total_premium_amount is not None:
                premium = self.total_premium_amount
            elif self.single_premium_amount is not None and self.contract_size is not None:
                premium = self.single_premium_amount * self.contract_size
            elif self.premium_rate is not None:
                premium = self.notional * self.premium_rate / 100
            else:
                premium = self.notional * DEFAULT_CONFIG["client"]["option_premium_rate"]
            return premium if self.direction == "short" else -premium
        
        elif self.contract_type == "equity_swap":
            if self.margin_rate is not None:
                return self.notional * self.margin_rate / 100 if self.direction == "short" else -self.notional* self.margin_rate / 100
            elif self.margin_amount is not None:
                return self.margin_amount if self.direction == "short" else -self.margin_amount
            return self.notional * DEFAULT_CONFIG["client"]["swap_margin_rate"] if self.direction == "short" else -self.notional * DEFAULT_CONFIG["client"]["swap_margin_rate"]
        
        elif self.contract_type == "income_certificate":
            return self.funds_raised if self.funds_raised is not None else self.notional
        else:
            print("Invalid contract type, please check the contract type.")
            return 0.0
    
    def get_expected_income(self) -> float:
        """预期年化创收（万元）"""
        return self.notional * self.expected_yield
    
    def is_swap_margin_100_and_stock_as_underlying(self) -> bool:
        '''判断收益互换保证金比例是否为100%且标的资产为境内个股'''
        if self.contract_type != "equity_swap":
            return False
        if "stock" not in self.underlying_type:
            return False
        if self.margin_rate is not None:
            return abs(self.margin_rate - 100.0) < 0.001
        if self.margin_amount is not None:
            ratio = self.margin_amount / self.notional
            return abs(ratio - 1.0) < 0.001
        return abs(DEFAULT_CONFIG["client"]["swap_margin_rate"] - 100.0) < 0.001
    
    def get_otc_delta_amount(self) -> float:
        """获取场外合约Delta金额（万元）"""
        is_long = 1 if self.direction == "long" else -1
        if "option" in self.contract_type:
            is_call = 1 if self.option_type == "call_option" else -1
            if self.option_delta is not None:
                return self.option_delta * self.notional
            return DEFAULT_CONFIG["client"]["atm_option_delta"] * self.notional * is_call * is_long
        elif "swap" in self.contract_type:
            if self.equity_swap_delta is not None:
                return self.equity_swap_delta * self.notional
            return DEFAULT_CONFIG["client"]["equity_swap_delta"] * self.notional * is_long
        elif "income_certificate" in self.contract_type:
            if self.income_certificate_delta is not None:
                return self.income_certificate_delta * self.notional
            return DEFAULT_CONFIG["client"]["income_certificate_delta"] * self.notional * is_long
        return 0.0


# ===================== 模块B：交易端对冲工具 =====================
@dataclass
class HedgeTrade:
    """对应模块B：对冲工具"""
    tool_type: str              # ETF | 股票 | 股指期货 | 场内期权 | 场外背对背期权 | 私募基金
    direction: str              # "long" | "short"
    notional: float             # 名义价值/对冲总金额（万元）
    tool_code: Optional[str] = None  # 对冲工具iFinD代码
    # 标的资产属性
    underlying_type: Optional[str] = None  # 衍生品的底层资产类型，若为股票或ETF，直接为tool_type
    underlying_name: Optional[str] = None  # 对冲工具底层资产名称
    underlying_code: Optional[str] = None  # 对冲工具底层资产代码

    # ETF现货
    cash_spent: Optional[float] = None
    
    # 股票现货
    stock_type: Optional[str] = None  # 股票类型: 指数成分股 | 一般上市公司股票 | 流动受限股票 | 其他股票
    
    # 期货
    futures_margin: Optional[float] = None  # 股指期货保证金（万元）
    futures_margin_rate: Optional[float] = None  # 股指期货保证金比例（%）
    future_type: Optional[str] = None  # 期货类型
    future_delta: Optional[float] = None  # 期货Delta值（%）
    
    # 场内期权
    option_premium: Optional[float] = None   # 场内期权权利金（万元）
    option_type: Optional[str] = None  # 期权类型: 看涨期权 | 看跌期权
    option_strike_price: Optional[float] = None  # 期权执行价（元）
    option_start_date: Optional[str] = None    # 期权起始日（YYYY-MM-DD）
    option_expiry_date: Optional[str] = None    # 期权到期日（YYYY-MM-DD）
    option_delta: Optional[float] = None        # Delta值（%）
    
    # 场外背对背对冲
    otc_payment: Optional[float] = None         # 向平盘方支付的预付金/保证金（万元）
    pass_through_fee: Optional[float] = None    # 平盘成本（年化%）
    
    # 私募基金
    subscription_amount: Optional[float] = None
    
    def get_trade_cash_outflow(self) -> float:
        """计算交易端首日现金净流出（万元，正值=流出）"""
        if self.tool_type == "etf":
            if self.cash_spent is not None:
                return self.cash_spent if self.direction == "long" else -self.cash_spent
            else:
                return self.notional if self.direction == "long" else -self.notional
        
        elif self.tool_type == "stock":
            return self.notional if self.direction == "long" else -self.notional
        
        elif self.tool_type == "futures":
            if self.futures_margin is not None:
                return self.futures_margin
            rate = self.futures_margin_rate if self.futures_margin_rate is not None else DEFAULT_CONFIG["trade"]["futures_margin_rate"]
            return self.notional * rate
        
        elif self.tool_type == "onsite_option":
            if self.option_premium is not None:
                return self.option_premium if self.direction == "long" else -self.option_premium
            premium = self.notional * DEFAULT_CONFIG["trade"]["onsite_option_premium_rate"]
            return premium if self.direction == "long" else -premium
        
        elif self.tool_type == "otc_hedge":
            # 场外背对背：支付的预付金 + 平盘成本（年化，按期限折算）
            total = self.otc_payment if self.otc_payment is not None else 0.0
            if self.pass_through_fee is not None:
                # 平盘成本 = 名义本金 × 平盘成本率 × (期限/365)
                total += self.notional * self.pass_through_fee / 100 * (90 / 365)  # 默认90天
            return total
        
        elif self.tool_type == "private_fund":
            return self.subscription_amount if self.subscription_amount is not None else 0.0
        
        return 0.0
    
    def get_tool_type(self) -> str:
        """获取对冲工具类型"""
        return self.tool_type
    
    def get_tool_notional(self) -> float:
        """获取对冲工具名义价值（万元）"""
        return self.notional
    
    def get_tool_direction(self) -> str:
        """获取对冲工具方向"""
        return self.direction

    def get_tool_code(self) -> str:
        return self.tool_code
    
    def get_tool_stock_type(self) -> Optional[str]:
        """获取对冲工具股票类型"""
        return self.stock_type if self.stock_type is not None else None
    
    def get_tool_underlying_name(self) -> str:
        """获取对冲工具底层资产名称"""
        return self.underlying_name
    
    def get_tool_underlying_code(self) -> str:
        """获取对冲工具底层资产代码"""
        return self.underlying_code
    
    def get_hedge_delta_amount(self) -> Optional[float]:
        """获取对冲工具的Delta金额"""
        is_long = 1 if self.direction == "long" else -1
        if self.tool_type == "onsite_option":
            is_call = 1 if self.option_type == "call_option" else -1
            if self.option_delta is not None:
                return self.option_delta * self.notional
            return DEFAULT_CONFIG["trade"]["onsite_option_delta"] * self.notional * is_call * is_long
        elif "futures" in self.tool_type:
            if self.future_delta is not None:
                return self.future_delta * self.notional
            return DEFAULT_CONFIG["trade"]["future_delta"] * self.notional * is_long
        elif self.tool_type == "etf" or self.tool_type == "stock":
            return self.notional if self.direction == "long" else -self.notional
        return None



# ===================== 核心计算函数 =====================


# =============== 判断是否有效对冲函数组 ==============
def ifind_login():
    '''登录iFinD函数'''
    # 输入用户的帐号和密码
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
    获取产品底层过去一年的价格数据
    Args:
        underlying_code: 同花顺代码，如 'AAPL.O', '000300.SH'
        start_date: 开始日期 'YYYY-MM-DD'，默认一年前
        end_date: 结束日期 'YYYY-MM-DD'，默认今天
        price_type: 价格类型，如 'close', 'open', 'high', 'low', 'pre_close'
    Returns:
        Dict[str, List[float]]: {"代码": [价格列表]}
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
        # 调用 THS_HQ 获取数据
        result = THS_HQ(underlying_code, price_type, 'fill:omit', start_date, end_date)
        if result is None:
            print("THS_DS 返回 None")
            return {underlying_code: []}
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"获取数据失败，错误码: {result.errorcode}, 错误信息: {result.errmsg}")
            return {underlying_code: []}
        data = pd.DataFrame(result.data)
        THS_iFinDLogout()
        if data.empty:
            print("获取数据为空")
            return {underlying_code: []}
        return {underlying_code: data[price_type].tolist()}
    
    except Exception as e:
        print(f"获取底层价格数据失败: {e}")
        return {underlying_code: []}
    
def calculate_correlation_between_price_series(otc_code: str, otc_prices: Dict[str, List[float]],
    hedge_code: str, hedge_prices: Dict[str, List[float]]) -> float:
    """计算两个标的价格序列的相关系数
    args:
        otc_code: 场外合约代码
        otc_prices: 场外合约价格字典
        hedge_code: 对冲工具代码
        hedge_prices: 对冲工具价格字典
    returns:
        float: 相关系数
    """
    # 提取价格序列
    otc_series = pd.Series(otc_prices.get(otc_code, []))
    hedge_series = pd.Series(hedge_prices.get(hedge_code, []))
    if len(otc_series) < 2 or len(hedge_series) < 2:
        return np.nan
    
    # 对齐长度
    min_len = min(len(otc_series), len(hedge_series))
    otc_aligned = otc_series.iloc[:min_len]
    hedge_aligned = hedge_series.iloc[:min_len]
    corr = otc_aligned.corr(hedge_aligned)
    return corr if corr is not None else np.nan

def get_onsite_option_greeks(option_code: str, greek_letter: str = 'delta') -> Optional[float]:
    """获取期权greeks值
    args:
        option_code: 期权代码
        greek_letter: greek字母，如 'delta', 'gamma', 'vega', 'theta', 'rho'
    returns:
        float: 期权当日greek字母值，若当天交易未结束，返回前一交易日greek
    """
    if not ifind_login():
        print("登录失败")
        return None
    # 5大常用希腊字母映射字典，不够再加
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
        THS_iFinDLogout()
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

def is_effective_hedge(otc: OtcContract, hedge_list: List[HedgeTrade], price_type: str = "close") -> List[bool, Optional[str]]:
    """
    判断是否构成有效对冲
    args:
        otc: 场外合约对象
        hedge_list: 对冲工具列表
        price_type: 标的价格类型，如 'close', 'open', 'high', 'low', 'pre_close'
    returns:
        bool: 是否构成有效对冲
    
    条件1：标的物相同 OR 过去一年价格相关性 ≥ 95%
    条件2：多头Delta绝对值与空头Delta绝对值比例在 80%-125% 之间
    """
    # ========== 条件1.1：判断标的物是否相同 ==========
    otc_underlying_code = otc.get_otc_underlying_code()
    if otc_underlying_code is None:
        return [False, "未填写场外合约标的代码，默认不满足有效对冲条件"]
    hedge_tool_underlying_codes = [h.get_tool_underlying_code() for h in hedge_list if h.get_tool_underlying_code() is not None]
    if not hedge_tool_underlying_codes:
        return [False, "未填写对冲工具标的代码，默认不满足有效对冲条件"]
    
    # 检查是否所有对冲工具的标的代码都与场外合约相同
    underlying_is_same = any(otc_underlying_code == h_code for h_code in hedge_tool_underlying_codes)
    
    # ========== 条件1.2：判断标的物过去一年价格相关性 ≥ 95% ==========
    correlation_met = True
    if not underlying_is_same:
        otc_price_data = get_underlying_price_series(otc_underlying_code, price_type) # 产品底层过去一年价格
        if not otc_price_data.get(otc_underlying_code, []):
            return [False, f"获取{otc.get_otc_contract_type()}产品标的：{otc.get_otc_underlying_code()}价格数据失败"]
        for hedge_tool_underlying_code in hedge_tool_underlying_codes:
            hedge_price_data = get_underlying_price_series(hedge_tool_underlying_code, price_type) # 获取对冲工具底层过去一年的价格
            if not hedge_price_data.get(hedge_tool_underlying_code, []):
                return [False, f"获取对冲工具标的: {hedge_tool_underlying_code}价格数据失败"]
            # 计算相关系数
            corr = calculate_correlation_between_price_series(otc_underlying_code, otc_price_data, hedge_tool_underlying_code, hedge_price_data)
            if np.isnan(corr) or corr < 0.95:
                correlation_met = False
                break
        condition1 = underlying_is_same or correlation_met
        if not condition1:
            return [False, "标的代码不匹配或标的物过去一年价格相关性未达到95%"]

    # ========== 条件2：计算Delta值比例 ==========
    # 标的代码与Delta现金金额总列表
    all_positions = []
    otc_delta_amount = otc.get_otc_delta_amount()
    otc_direction = otc.get_otc_contract_direction()
    if otc_delta_amount is not None:
        all_positions.append((otc_direction, otc_delta_amount))
    else:
        return [False, "未填写对冲工具Delta金额，默认不满足有效对冲条件"]
    for hedge in hedge_list:
        hedge_direction = hedge.get_tool_direction()
        if hedge.get_tool_type() == "onsite_option":
            hedge_delta = get_onsite_option_greeks(hedge.get_tool_code(), "delta")
        else:
            hedge_delta = hedge.get_hedge_delta_amount()
        if hedge_delta is not None:
            all_positions.append((hedge_direction, hedge_delta))
        else:
            return [False, "未填写对冲工具Delta金额，或未成功获取相应期权delta值，请检查，否则默认不满足有效对冲条件"]
    if not all_positions:
        return False
    
    # 计算多头Delta总和（取绝对值）和空头Delta总和（取绝对值）
    long_delta = sum(abs(delta) for dir_, delta in all_positions if dir_ == "long")
    short_delta = sum(abs(delta) for dir_, delta in all_positions if dir_ == "short")
    if long_delta == 0 or short_delta == 0:
        return [False, "多头Delta绝对值或空头Delta绝对值为0，默认不满足有效对冲条件"]
    ratio = min(long_delta, short_delta) / max(long_delta, short_delta)
    if ratio < 0.80:
        return [False, "多头Delta绝对值与空头Delta绝对值比例不在80%-125%之间"]
    
    return True


def calc_market_risk_reserve(otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool) -> float:
    """计算市场风险资本准备（万元）"""
    # 风险系数
    RATES = {
        "index_component": 0.08,      # 指数成分股 8%
        "general_stock": 0.25,        # 一般上市股票 25%
        "restricted_stock": 0.50,     # 流通受限股票 50%
        "other_stock": 0.80,          # 其他股票 80%
        "stock_index_future": 0.30,   # 股指期货 30%
        "equity_swap": 0.30,          # 权益互换 30%
        "equity_short_option": 0.30,  # 权益类卖出期权 30%
        "equtity_long_option": 1.00,  # 权益类买入期权 100%
        "monetary_fund": 0.05,        # 货币基金 5%
        "interest_rate_bond_index_fund": 0.06, # 利率债指数基金 6%
        "other_non_equity_fund": 0.10,  # 其他非权益类基金
        "treasury_future_and_interest_rate_swap": 0.20, # 国债期货和利率互换 20%
        "single_product": 0.50,        # 单一产品 50%
        "bulk_commodity": 0.08,       # 大宗商品 8%
        "bulk_commodity_derivatives": 0.20,     # 大宗商品衍生品 20%
        "non_equity_short_option": 0.20,  # 非权益类卖出期权 20%
        "non_equity_long_option": 1.00,  # 非权益类买入期权 100%
    }
    
    reserve = 0.0

    # 场外合约风险敞口
    if otc.contract_type == "option":
        if otc.direction == "buy":
            premium = otc.notional * (otc.premium_rate or DEFAULT_CONFIG["client"]["option_premium_rate"]) / 100
            reserve += premium * RATES["buy_option"]
        else:  # 卖出
            if otc.stress_loss is not None:
                # 卖出场外期权
                virtual = max(otc.stress_loss * 5, otc.notional * 0.005)
                reserve += virtual * RATES["futures_swap"]
            elif otc.delta_amount is not None:
                # 卖出场内期权
                reserve += otc.delta_amount * 0.15 * RATES["futures_swap"]
            else:
                # 默认按名义本金估算
                reserve += otc.notional * 0.30 * RATES["futures_swap"]
    
    elif otc.contract_type == "swap":
        exposure = otc.notional * 0.10
        reserve += exposure * RATES["futures_swap"]
        if otc.margin_rate is not None and otc.margin_rate < 100:
            reserve *= 2  # 非全额保证金加倍
    
    elif otc.contract_type == "income_note":
        if otc.expected_yield > 0.05:
            reserve += otc.notional * 0.05 * RATES["futures_swap"]
    
    # 有效对冲减免
    if is_hedge_effective and hedge_list:
        reserve *= 0.05
    
    return reserve


def calc_credit_risk_reserve(otc: OtcContract) -> float:
    """计算信用风险资本准备（万元）"""
    if otc.contract_type == "swap" and otc.margin_rate is not None and otc.margin_rate < 100:
        if otc.underlying_type == "general_stock":
            return otc.notional * 0.05
    return 0.0


def calc_total_risk_reserve(otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool) -> float:
    """计算各项风险资本准备合计（万元）"""
    total = (
        calc_market_risk_reserve(otc, hedge_list, is_hedge_effective)
        + calc_credit_risk_reserve(otc)
        # + calc_operational_risk_reserve()  # 简化，暂为0
        # + calc_specific_risk_reserve()     # 简化，暂为0
    )
    total *= DEFAULT_CONFIG["firm"]["classification_factor"]
    return total


def calc_lcr_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """计算LCR影响（万元）"""
    hqla_change = 0.0
    cof_change = 0.0
    
    # 场外合约现金变动
    otc_cash = otc.get_otc_cash_inflow()
    hqla_change += otc_cash
    
    # 对冲端现金变动
    for hedge in hedge_list:
        trade_cash = hedge.get_trade_cash_outflow()
        hqla_change -= trade_cash
    
    # 30日内到期现金流（简化）
    if otc.term_days <= 30:
        if otc.contract_type == "income_note":
            cof_change += otc.funds_raised or otc.notional
        elif otc.contract_type == "swap":
            cof_change += otc.notional * (otc.margin_rate or 10) / 100
    
    return {
        "hqla_change": hqla_change,
        "net_cof_change": cof_change,  # 简化，未处理CIF抵扣
    }


def calc_nsfr_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """计算NSFR影响（万元）"""
    asf_change = 0.0
    rsf_change = 0.0
    
    # 收益凭证：期限>=1年，100%计入ASF
    if otc.contract_type == "income_note" and otc.term_days >= 365:
        asf_change += otc.funds_raised or otc.notional
    
    # 互换保证金：期限>=1年，按50%计入
    if otc.contract_type == "swap" and otc.term_days >= 365:
        asf_change += otc.notional * (otc.margin_rate or 10) / 100 * 0.5
    
    # 场外合约所需稳定资金
    if otc.contract_type == "option":
        if otc.direction == "buy":
            premium = otc.notional * (otc.premium_rate or 5) / 100
            rsf_change += premium
        else:
            rsf_change += otc.notional * 0.30
    
    elif otc.contract_type == "swap":
        rsf_change += otc.notional * 0.01
    
    # 对冲端所需稳定资金
    for hedge in hedge_list:
        if hedge.tool_type == "etf" or hedge.tool_type == "stock_basket":
            rsf_change += hedge.notional * 0.50
        elif hedge.tool_type == "private_fund":
            rsf_change += (hedge.subscription_amount or 0) * 0.20
        elif hedge.tool_type == "otc_hedge":
            rsf_change += hedge.notional * 0.01
    
    return {"asf_change": asf_change, "rsf_change": rsf_change}


def analyze_contract(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, Any]:
    """主分析函数"""
    # 现金流
    otc_cash = otc.get_otc_cash_inflow()
    total_trade_cash = sum(h.get_trade_cash_outflow() for h in hedge_list)
    net_day1_cash = otc_cash - total_trade_cash
    expected_income = otc.get_expected_income()
    
    # 对冲有效性
    is_effective = is_effective_hedge(otc, hedge_list)
    
    # 风险资本准备
    new_risk_reserve = calc_total_risk_reserve(otc, hedge_list, is_effective[0])
    
    # LCR影响
    lcr = calc_lcr_impact(otc, hedge_list)
    
    # NSFR影响
    nsfr = calc_nsfr_impact(otc, hedge_list)
    
    # 表内外资产总额变动
    new_assets = otc.notional * 0.10 + sum(h.notional * 0.10 for h in hedge_list)
    
    # 核心指标变动
    hqla_new = DEFAULT_CONFIG["firm"]["HQLA_base"] / 10000 + lcr["hqla_change"]
    cof_new = DEFAULT_CONFIG["firm"]["LCR_COF_base"] / 10000 + lcr["net_cof_change"]
    lcr_new = hqla_new / cof_new if cof_new > 0 else 999
    lcr_old = (DEFAULT_CONFIG["firm"]["HQLA_base"] / 10000) / (DEFAULT_CONFIG["firm"]["LCR_COF_base"] / 10000)
    
    asf_new = DEFAULT_CONFIG["firm"]["ASF_base"] / 10000 + nsfr["asf_change"]
    rsf_new = DEFAULT_CONFIG["firm"]["RSF_base"] / 10000 + nsfr["rsf_change"]
    nsfr_new = asf_new / rsf_new if rsf_new > 0 else 999
    nsfr_old = (DEFAULT_CONFIG["firm"]["ASF_base"] / 10000) / (DEFAULT_CONFIG["firm"]["RSF_base"] / 10000)
    
    risk_reserve_new = DEFAULT_CONFIG["firm"]["total_risk_reserve_base"] / 10000 + new_risk_reserve
    risk_old = DEFAULT_CONFIG["firm"]["net_capital_base"] / 10000 / (DEFAULT_CONFIG["firm"]["total_risk_reserve_base"] / 10000)
    risk_new = DEFAULT_CONFIG["firm"]["net_capital_base"] / 10000 / risk_reserve_new if risk_reserve_new > 0 else 999
    
    return {
        "net_day1_cash": net_day1_cash,
        "expected_income": expected_income,
        "new_risk_reserve": new_risk_reserve,
        "new_assets": new_assets,
        "lcr_net_cof_change": lcr["net_cof_change"],
        "lcr_old": lcr_old,
        "lcr_new": lcr_new,
        "lcr_change": lcr_new - lcr_old,
        "lcr_status": "safe" if lcr_new >= 1.20 else "warning" if lcr_new >= 1.00 else "danger",
        "nsfr_old": nsfr_old,
        "nsfr_new": nsfr_new,
        "nsfr_change": nsfr_new - nsfr_old,
        "nsfr_status": "safe" if nsfr_new >= 1.20 else "warning" if nsfr_new >= 1.00 else "danger",
        "risk_coverage_old": risk_old,
        "risk_coverage_new": risk_new,
        "risk_coverage_change": risk_new - risk_old,
        "risk_coverage_status": "safe" if risk_new >= 1.20 else "warning" if risk_new >= 1.00 else "danger",
        "ro_capital": expected_income / new_risk_reserve if new_risk_reserve > 0 else 999,
        "ro_assets": expected_income / new_assets if new_assets > 0 else 999,
        "ro_lcr": expected_income / abs(lcr["net_cof_change"]) if lcr["net_cof_change"] != 0 else 999,
        "is_effective_hedge": is_effective,
    }


# ===================== 测试用例 =====================
if __name__ == "__main__":
    otc = OtcContract(
        contract_type="put_option",
        direction="short",
        notional=100000,
        underlying_type="Index",
        underlying_name="中证1000",
        underlying_code="000852"
    )
    hedge_list = [
        HedgeTrade(
            tool_type="onsite_option",
            direction="long",
            notional=50000,
            underlying_type="Index",
            underlying_name="中证1000",
            underlying_code="000852",
            option_delta=0.95
        )
    ]
    is_effective = is_effective_hedge(otc, hedge_list)
    print(is_effective)

    d = get_underlying_price_series('000852.SH', 'close')
    print(d)