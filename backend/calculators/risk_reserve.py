# ============================================================
# backend/calculators/risk_reserve.py - 风险资本准备计算
# ============================================================

from typing import List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from ..config import DEFAULT_CONFIG
from .ratios import RATES


# ============================================================
# 辅助函数
# ============================================================

def _get_option_premium(otc: OtcContract) -> float:
    """获取场外期权的权利金绝对值 P（万元）"""
    return abs(otc.get_otc_cash_inflow())


def _get_short_investment_scale(notional: float, stress_loss: float = 0.0) -> float:
    """
    卖出期权投资规模 S_short = max(5 × L_stress, N × 0.5%)
    适用：场外卖出期权 / 浮动收益凭证内嵌期权
    """
    return max(5 * stress_loss, notional * 0.005)


def _get_client_investment_scale(otc: OtcContract) -> float:
    """
    获取场外合约客户端的投资规模 |S_client|
      买入期权: S = P（权利金）
      卖出期权: S = S_short
      收益互换: S = N × 10%
      收益凭证(浮): S = S_short; (固): S = 0
    """
    ct = otc.contract_type

    if ct in ("call_option", "put_option"):
        if otc.direction == "buy":
            return _get_option_premium(otc)
        else:
            loss = otc.stress_loss or 0.0
            return _get_short_investment_scale(otc.notional, loss)

    elif ct == "equity_swap":
        return otc.notional * 0.10

    elif ct == "income_certificate":
        if otc.stress_loss is not None:
            return _get_short_investment_scale(otc.notional, otc.stress_loss)
        return 0.0

    return 0.0


def _get_hedge_investment_scale(hedge: HedgeTrade) -> float:
    """
    获取单个对冲工具的投资规模 |S_hedge|
      现货/ETF: 市值 = notional
      期货: 名义价值 × 15%
      场外背对背: N × 10%（按互换处理）
      场内期权: 权利金（默认名义价值 × 2%）
      私募基金: 申购金额
    """
    if hedge.tool_type in ("etf", "stock"):
        return hedge.notional
    elif hedge.tool_type == "futures":
        return hedge.notional * 0.15
    elif hedge.tool_type == "otc_hedge":
        return hedge.notional * 0.10
    elif hedge.tool_type == "onsite_option":
        if hedge.option_premium is not None:
            return hedge.option_premium
        return hedge.notional * DEFAULT_CONFIG["trade"]["onsite_option_premium_rate"]
    elif hedge.tool_type == "private_fund":
        return hedge.subscription_amount or 0.0
    return 0.0


def _is_non_full_margin_swap(otc: OtcContract) -> bool:
    """条件A：收益互换是否为非全额保证金（M < N）"""
    if otc.contract_type != "equity_swap":
        return False
    if otc.margin_amount is not None:
        return otc.margin_amount < otc.notional
    if otc.margin_rate is not None:
        return otc.margin_rate < 100.0
    return True  # 默认10%保证金，必然非全额


def _is_individual_stock(otc: OtcContract) -> bool:
    """条件B：标的是否为境内个股（非指数成分股）"""
    return otc.underlying_type not in ("index_component",)


# ============================================================
# 各产品市场风险资本准备
# ============================================================

def _calc_option_market_risk(
    otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool
) -> float:
    """
    场外期权的市场风险资本准备（万元，不含 k_class）
    """
    s_client = _get_client_investment_scale(otc)
    s_hedge_total = sum(_get_hedge_investment_scale(h) for h in hedge_list)

    if is_hedge_effective and hedge_list:
        # 达成有效对冲：(|S_client| + |S_hedge|) × 5%
        return (s_client + s_hedge_total) * 0.05

    # 单边未对冲
    if otc.direction == "buy":
        return s_client * RATES["equtity_long_option"]   # 买入期权 100%
    else:
        return s_client * RATES["equity_short_option"]   # 卖出期权 30%


def _calc_swap_market_risk(
    otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool
) -> float:
    """
    收益互换的市场风险资本准备（万元，不含 k_class）

    惩罚条件：同时满足 条件A(非全额保证金) + 条件B(个股标的) → 加倍
    """
    s_client = _get_client_investment_scale(otc)  # N × 10%
    s_hedge_total = sum(_get_hedge_investment_scale(h) for h in hedge_list)
    is_penalty = _is_non_full_margin_swap(otc) and _is_individual_stock(otc)

    if is_hedge_effective and hedge_list:
        reserve = (s_client + s_hedge_total) * 0.05
    else:
        reserve = s_client * RATES["equity_swap"]   # N × 10% × 30% = N × 3%

    if is_penalty:
        reserve *= 2.0

    return reserve


def _calc_income_cert_market_risk(
    otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool
) -> float:
    """
    收益凭证的市场风险资本准备（万元，不含 k_class）
    仅浮动收益凭证（含内嵌衍生品）才计提
    """
    if otc.stress_loss is None:
        return 0.0  # 固定收益凭证：无市场风险资本准备

    s_client = _get_client_investment_scale(otc)  # S_short
    s_hedge_total = sum(_get_hedge_investment_scale(h) for h in hedge_list)

    if is_hedge_effective and hedge_list:
        return (s_client + s_hedge_total) * 0.05

    return s_client * RATES["equity_short_option"]  # S_short × 30%


# ============================================================
# 信用风险资本准备（仅收益互换）
# ============================================================

def _calc_credit_risk(otc: OtcContract) -> float:
    """
    信用风险资本准备（万元，不含 k_class）

    仅对非全额保证金的收益互换计提：N × 5%
    对冲不减免信用风险
    """
    if otc.contract_type != "equity_swap":
        return 0.0
    if not _is_non_full_margin_swap(otc):
        return 0.0
    return otc.notional * 0.05


# ============================================================
# 合计入口
# ============================================================

def calc_total_risk_reserve(
    otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool
) -> float:
    """
    计算各项风险资本准备合计（万元，含 k_class 分类评价系数）

    【组成】市场风险 + 信用风险（操作风险/特定风险待实现）

    三种产品的计提规则：
      1. 场外期权
         - 买入: P × 100% × k_class
         - 卖出: S_short × 30% × k_class
         - 对冲: (|S_client| + |S_hedge|) × 5% × k_class
      2. 收益互换
         - 市场风险: N×3%×k_class（惩罚情况×2）
         - 信用风险: N×5%×k_class（非全额保证金，对冲不减免）
         - 对冲: (|S_swap|+|S_hedge|)×5%×k_class（惩罚仍×2）
      3. 收益凭证
         - 固定型: 0
         - 浮动型: S_short×30%×k_class / 对冲: (|S_short|+|S_hedge|)×5%×k_class

    【分类评价系数 k_class】
      AAA=0.4, AA=0.6, A=0.8, BBB=0.9, BB=1.0, B=1.0, C=1.0, D=2.0
    """
    ct = otc.contract_type
    k_class = DEFAULT_CONFIG["firm"]["classification_factor"]

    if ct in ("call_option", "put_option"):
        market_risk = _calc_option_market_risk(otc, hedge_list, is_hedge_effective)
        credit_risk = 0.0

    elif ct == "equity_swap":
        market_risk = _calc_swap_market_risk(otc, hedge_list, is_hedge_effective)
        credit_risk = _calc_credit_risk(otc)

    elif ct == "income_certificate":
        market_risk = _calc_income_cert_market_risk(otc, hedge_list, is_hedge_effective)
        credit_risk = 0.0

    else:
        return 0.0

    total = (market_risk + credit_risk) * k_class
    return total
