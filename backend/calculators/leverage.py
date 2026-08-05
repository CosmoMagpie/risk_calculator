# ============================================================
# backend/calculators/leverage.py - 资本杠杆率（分类调整后表内外资产总额）边际影响
# ============================================================

from typing import List

from ..config import DEFAULT_CONFIG
from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade


def _get_short_scale(notional: float, stress_loss: float = 0.0) -> float:
    return max(5 * stress_loss, notional * 0.005)


def _is_domestic_individual_stock(
    underlying_type: str | None,
    underlying_instrument: str | None,
    underlying_market: str | None,
) -> bool:
    market = (underlying_market or "CN").upper()
    if market not in ("CN", "CHINA", "A_SHARE"):
        return False
    if underlying_instrument is not None:
        return underlying_instrument == "stock"
    return underlying_type not in ("index_component", "broad_based_etf", "index")


def _is_swap_penalty(otc: OtcContract) -> bool:
    if otc.contract_type != "equity_swap":
        return False
    if otc.margin_amount is not None:
        non_full = otc.margin_amount < otc.notional
    elif otc.margin_rate is not None:
        non_full = otc.margin_rate < 100.0
    else:
        non_full = True
    return non_full and _is_domestic_individual_stock(
        otc.underlying_type, otc.underlying_instrument, otc.underlying_market
    )


def _calc_client_on_balance(otc: OtcContract) -> float:
    """新增交易对总资产的影响；支付现金购买资产不减少总资产。"""
    if otc.contract_type in ("call_option", "put_option"):
        return max(0.0, otc.get_otc_cash_inflow())
    if otc.contract_type == "equity_swap":
        return max(0.0, otc.get_otc_cash_inflow())
    if otc.contract_type == "income_certificate":
        return otc.funds_raised if otc.funds_raised is not None else otc.notional
    return 0.0


def _calc_hedge_on_balance(hedge_list: List[HedgeTrade]) -> float:
    # 现金支出通常只是现金转为金融资产/保证金；现金收入同时形成相应负债或空头头寸，
    # 会增加表内总资产。
    return sum(max(0.0, -hedge.get_trade_cash_outflow()) for hedge in hedge_list)


def _calc_client_off_balance(otc: OtcContract) -> float:
    if otc.contract_type in ("call_option", "put_option"):
        if otc.direction == "short":
            return _get_short_scale(otc.notional, otc.stress_loss or 0.0)
        return 0.0
    if otc.contract_type == "equity_swap":
        return otc.notional * (0.20 if _is_swap_penalty(otc) else 0.10)
    if otc.contract_type == "income_certificate" and otc.has_embedded_option:
        notional = otc.embedded_option_notional or otc.notional
        return _get_short_scale(notional, otc.stress_loss or 0.0)
    return 0.0


def _calc_hedge_off_balance(hedge_list: List[HedgeTrade]) -> float:
    total = 0.0
    for hedge in hedge_list:
        if hedge.tool_type == "futures":
            total += hedge.notional * 0.15
        elif hedge.tool_type == "onsite_option" and hedge.direction == "short":
            total += abs(hedge.option_delta or 0.5) * hedge.notional * 0.15
        elif hedge.tool_type == "otc_hedge":
            if hedge.otc_hedge_contract_type == "option" and hedge.direction == "short":
                total += _get_short_scale(
                    hedge.notional, hedge.otc_stress_loss or 0.0
                )
            elif hedge.otc_hedge_contract_type == "equity_swap":
                penalty = (
                    (hedge.otc_payment or 0.0) < hedge.notional
                    and _is_domestic_individual_stock(
                        hedge.underlying_type, None, hedge.underlying_market
                    )
                )
                total += hedge.notional * (0.20 if penalty else 0.10)
    return total


def calc_leverage_impact(
    otc: OtcContract,
    hedge_list: List[HedgeTrade],
    net_day1_cash: float | None = None,
) -> float:
    """返回分类调整后的表内外资产总额增量（万元）。

    ``net_day1_cash``仅为兼容旧调用保留，监管表的表内资产总额不能用净现金流代替。
    """
    unadjusted = (
        _calc_client_on_balance(otc)
        + _calc_hedge_on_balance(hedge_list)
        + _calc_client_off_balance(otc)
        + _calc_hedge_off_balance(hedge_list)
    )
    return unadjusted * DEFAULT_CONFIG["firm"].get("asset_adjustment_factor", 1.0)
