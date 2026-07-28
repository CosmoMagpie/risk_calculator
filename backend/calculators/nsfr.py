# ============================================================
# backend/calculators/nsfr.py - NSFR（净稳定资金率）影响计算
# ============================================================

from typing import Dict, List

from ..config import DEFAULT_CONFIG
from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from .ratios import RSF_RATES


def _calc_hedge_rsf(hedge_list: List[HedgeTrade]) -> float:
    """
    计算交易端对冲工具的 ΔRSF（所需稳定资金变动量，万元）

    【规则 —— 按工具类型与标的属性分别计提】
      现货端：
        - 指数成分股（沪深300/中证500等）：市值 × 30%
        - 宽基ETF：市值 × 10%
        - 一般上市公司股票 / 非宽基ETF：市值 × 50%
        - 流动受限 / 其他股票：市值 × 100%
      衍生品端：
        - 场内股指期货：名义价值 × 12%
        - 场内卖出期权：Delta金额 × 15% × 12%（买入期权不计RSF）
        - 场外背对背（视为互换）：名义本金 × 1%
        - 私募基金：申购金额 × 20%
    """
    rsf = 0.0

    for h in hedge_list:
        # --- ETF 现货 ---
        if h.tool_type == "etf":
            ut = h.underlying_type
            if ut == "index_component":
                rsf += h.notional * RSF_RATES["index_component_etf"]     # 宽基ETF: 10%
            else:
                rsf += h.notional * RSF_RATES["general_stock"]           # 非宽基ETF: 50%

        # --- 一揽子股票 ---
        elif h.tool_type == "stock":
            st = h.stock_type or "general_stock"
            rsf += h.notional * RSF_RATES.get(st, RSF_RATES["general_stock"])

        # --- 场内期货（名义价值 × 12%）---
        elif h.tool_type == "futures":
            rsf += h.notional * RSF_RATES["stock_index_future"]

        # --- 场内期权（仅卖出期权计入RSF）---
        elif h.tool_type == "onsite_option":
            if h.direction == "short":
                # Delta金额 = Delta系数 × 名义价值
                delta_amount = (h.option_delta or 0.5) * h.notional
                rsf += delta_amount * RSF_RATES["onsite_short_option"]   # Delta × 15% × 12%

        # --- 场外背对背对冲（按互换 1% 计提）---
        elif h.tool_type == "otc_hedge":
            rsf += h.notional * RSF_RATES["equity_swap"]

        # --- 私募基金 ---
        elif h.tool_type == "private_fund":
            amount = h.subscription_amount if h.subscription_amount is not None else 0.0
            rsf += amount * 0.20

    return rsf


def _calc_option_nsfr(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    场外期权（call_option / put_option）的 NSFR 影响计算
    """
    # --- ΔASF（可用稳定资金增量）---
    asf_change = 0.0
    if otc.direction == "short":
        # 卖出期权收到的权利金，按合约期限折算为可用稳定资金
        # T ≥ 1年 → 100%；6月 ≤ T < 1年 → 依公司评级折算（0%~20%）；T < 6月 → 0%
        premium = abs(otc.get_otc_cash_inflow())
        days = otc.term_days
        if days >= 365:
            asf_change = premium * 1.00
        elif days >= 180:
            asf_change = premium * DEFAULT_CONFIG["firm"]["asf_rating_factor"]
    # 买入期权：无 ASF（支付权利金属于资金使用，非资金来源）

    # --- ΔRSF（所需稳定资金增量）---
    rsf_change = 0.0

    # 客户端
    if otc.direction == "short":
        loss = otc.stress_loss if otc.stress_loss is not None else 0.0
        s_short = max(5 * loss, otc.notional * 0.005)
        rsf_change += s_short * RSF_RATES["otc_short_option"]   # S_short × 12%
    # 买入期权：ΔRSF_client = 0

    # 交易端
    rsf_change += _calc_hedge_rsf(hedge_list)

    return {"asf_change": asf_change, "rsf_change": rsf_change}


def _calc_swap_nsfr(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    收益互换（equity_swap）的 NSFR 影响计算
    """
    # --- ΔASF ---
    # 互换保证金：若无确定期限或归入交易性负债，折算为 0%
    asf_change = 0.0

    # --- ΔRSF ---
    # 客户端：名义本金 × 1%
    rsf_change = otc.notional * RSF_RATES["equity_swap"]

    # 交易端
    rsf_change += _calc_hedge_rsf(hedge_list)

    return {"asf_change": asf_change, "rsf_change": rsf_change}


def _calc_income_cert_nsfr(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    收益凭证（income_certificate）的 NSFR 影响计算

    判断是否为浮动收益凭证（含内嵌衍生品）：otc.stress_loss 不为 None
    """
    V = otc.funds_raised if otc.funds_raised is not None else otc.notional
    is_floating = otc.stress_loss is not None
    days = otc.term_days

    # --- ΔASF（按发行期限 T 提供稳定资金）---
    # T ≥ 1年 → 100%；6月 ≤ T < 1年 → 依公司评级折算（0%~20%）；T < 6月 → 0%
    if days >= 365:
        asf_change = V * 1.00
    elif days >= 180:
        asf_change = V * DEFAULT_CONFIG["firm"]["asf_rating_factor"]
    else:
        asf_change = 0.0

    # --- ΔRSF ---
    rsf_change = 0.0

    # 内嵌期权部分（仅浮动收益凭证）：S_short × 12%
    if is_floating:
        loss = otc.stress_loss if otc.stress_loss is not None else 0.0
        s_short = max(5 * loss, otc.notional * 0.005)
        rsf_change += s_short * RSF_RATES["otc_short_option"]

    # 交易端
    rsf_change += _calc_hedge_rsf(hedge_list)

    return {"asf_change": asf_change, "rsf_change": rsf_change}


def calc_nsfr_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    计算对 NSFR（净稳定资金率）的影响

    【NSFR = ASF / RSF ≥ 100%】
      ASF = Available Stable Funding（可用稳定资金，负债端）
      RSF = Required Stable Funding（所需稳定资金，资产端）
      ΔNSFR = (ASF_base + ΔASF) / (RSF_base + ΔRSF) - NSFR_base

    三种产品分别有独立的计算逻辑：
      1. 场外期权（call_option / put_option）
         - ASF：卖出期权权利金按期限折算（≥1年100%，6月~1年0%，<6月0%）
         - RSF：卖出期权 S_short × 12% + 对冲端RSF
      2. 收益互换（equity_swap）
         - ASF：保证金归入交易性负债，折算 0%
         - RSF：名义本金 × 1% + 对冲端RSF
      3. 收益凭证（income_certificate）
         - ASF：募集资金 V 按期限折算
         - RSF：内嵌期权 S_short × 12%（仅浮动型）+ 对冲端RSF

    Returns:
        {"asf_change": ΔASF（万元）, "rsf_change": ΔRSF（万元）}
    """
    ct = otc.contract_type

    if ct in ("call_option", "put_option"):
        return _calc_option_nsfr(otc, hedge_list)
    elif ct == "equity_swap":
        return _calc_swap_nsfr(otc, hedge_list)
    elif ct == "income_certificate":
        return _calc_income_cert_nsfr(otc, hedge_list)
    else:
        return {"asf_change": 0.0, "rsf_change": 0.0}
