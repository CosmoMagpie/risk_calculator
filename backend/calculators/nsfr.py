# ============================================================
# backend/calculators/nsfr.py - NSFR（净稳定资金率）边际影响（依据附件5）
# ============================================================

from typing import Dict, List

from ..config import DEFAULT_CONFIG
from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from .ratios import RSF_RATES


def _eligible_liability_asf(amount: float, term_days: int) -> float:
    """仅对具有相应剩余期限且债权人无权提前要求偿还的借款/负债计入ASF。"""
    if term_days >= 365:
        return amount
    if term_days >= 180:
        return amount * DEFAULT_CONFIG["firm"]["asf_rating_factor"]
    return 0.0


def _other_asset_rsf(amount: float, maturity_days: int | None) -> float:
    """私募基金/SPV按“其他所有资产”剩余期限计提；无法确定期限归入1年以上。"""
    if maturity_days is None or maturity_days > 365:
        return amount
    if maturity_days > 180:
        return amount * 0.75
    return amount * 0.50


def _calc_hedge_rsf(hedge_list: List[HedgeTrade]) -> float:
    total = 0.0
    for hedge in hedge_list:
        if hedge.tool_type == "etf":
            rate = (
                RSF_RATES["broad_based_equity_etf"]
                if hedge.is_broad_based_etf
                else RSF_RATES["other_equity_fund"]
            )
            total += hedge.notional * rate
        elif hedge.tool_type == "stock":
            asset_type = hedge.stock_type or hedge.underlying_type or "general_stock"
            key = "index_component_stock" if asset_type == "index_component" else asset_type
            total += hedge.notional * RSF_RATES.get(key, 1.0)
        elif hedge.tool_type == "futures":
            total += hedge.notional * RSF_RATES["stock_index_future"]
        elif hedge.tool_type == "onsite_option" and hedge.direction == "short":
            delta_amount = abs(hedge.option_delta or 0.5) * hedge.notional
            total += delta_amount * RSF_RATES["onsite_short_option"]
        elif hedge.tool_type == "otc_hedge":
            if hedge.otc_hedge_contract_type == "equity_swap":
                total += hedge.notional * RSF_RATES["equity_swap"]
            elif hedge.otc_hedge_contract_type == "option" and hedge.direction == "short":
                total += hedge.notional * RSF_RATES["otc_short_option"]
        elif hedge.tool_type == "private_fund":
            amount = hedge.subscription_amount or hedge.notional
            total += _other_asset_rsf(amount, hedge.asset_maturity_days)
    return total


def _calc_option_nsfr(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    # 权利金收入不是附件5所列的有期限借款或负债，不因期权期限直接计入ASF。
    rsf = (
        otc.notional * RSF_RATES["otc_short_option"]
        if otc.direction == "short"
        else 0.0
    )
    return {"asf_change": 0.0, "rsf_change": rsf + _calc_hedge_rsf(hedge_list)}


def _calc_swap_nsfr(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    asf = 0.0
    if otc.margin_liability_term_days is not None:
        asf = _eligible_liability_asf(
            max(0.0, otc.get_otc_cash_inflow()), otc.margin_liability_term_days
        )
    rsf = otc.notional * RSF_RATES["equity_swap"]
    return {"asf_change": asf, "rsf_change": rsf + _calc_hedge_rsf(hedge_list)}


def _calc_income_cert_nsfr(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    funds = otc.funds_raised if otc.funds_raised is not None else otc.notional
    asf = _eligible_liability_asf(funds, otc.term_days)
    rsf = 0.0
    if otc.has_embedded_option:
        rsf += (otc.embedded_option_notional or otc.notional) * RSF_RATES[
            "otc_short_option"
        ]
    return {"asf_change": asf, "rsf_change": rsf + _calc_hedge_rsf(hedge_list)}


def calc_nsfr_impact(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    if otc.contract_type in ("call_option", "put_option"):
        return _calc_option_nsfr(otc, hedge_list)
    if otc.contract_type == "equity_swap":
        return _calc_swap_nsfr(otc, hedge_list)
    if otc.contract_type == "income_certificate":
        return _calc_income_cert_nsfr(otc, hedge_list)
    return {"asf_change": 0.0, "rsf_change": _calc_hedge_rsf(hedge_list)}
