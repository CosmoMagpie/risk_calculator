# ============================================================
# backend/calculators/lcr.py - LCR（流动性覆盖率）边际影响
# ============================================================
# 监管口径来自附件4。风险资本准备/表内外资产的"投资规模"不能替代本表的
# 合约期末名义价值；卖出场内期权的 Delta 金额×15% 为最终填列金额，不再乘20%。

from typing import Dict, List

from ..config import DEFAULT_CONFIG
from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from .ratios import HQLA_DISCOUNT, LCR_OUTFLOW_RATES


def _calc_hedge_outflow(hedge_list: List[HedgeTrade]) -> float:
    """交易端对冲工具新增未来30日毛现金流出（万元）。"""
    total = 0.0
    for hedge in hedge_list:
        if hedge.tool_type == "futures":
            total += hedge.notional * LCR_OUTFLOW_RATES["stock_index_future"]
        elif hedge.tool_type == "onsite_option" and hedge.direction == "short":
            delta_amount = abs(hedge.option_delta or 0.5) * hedge.notional
            total += delta_amount * LCR_OUTFLOW_RATES["onsite_short_option"]
        elif hedge.tool_type == "otc_hedge":
            if hedge.otc_hedge_contract_type == "equity_swap":
                total += hedge.notional * LCR_OUTFLOW_RATES["equity_swap"]
            elif hedge.otc_hedge_contract_type == "option" and hedge.direction == "short":
                total += hedge.notional * LCR_OUTFLOW_RATES["otc_short_option"]
    return total


def _calc_hedge_hqla(
    client_contract_type: str, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    """拆分现金/非权益HQLA变化与受15%上限约束的权益HQLA原始变化。"""
    non_equity_change = 0.0
    equity_raw_change = 0.0

    for hedge in hedge_list:
        trade_cash = hedge.get_trade_cash_outflow()
        non_equity_change -= trade_cash

        if hedge.tool_type not in ("etf", "stock"):
            continue

        # 附件4注3：已用于对冲权益互换合约的证券不计入HQLA。
        if client_contract_type == "equity_swap":
            continue

        if hedge.tool_type == "etf":
            rate = 0.50 if hedge.is_broad_based_etf else 0.0
        else:
            asset_type = hedge.underlying_type or hedge.stock_type
            rate = HQLA_DISCOUNT.get(asset_type, 0.0)

        sign = 1.0 if hedge.direction == "long" else -1.0
        equity_raw_change += sign * hedge.notional * rate

    return {
        "non_equity_change": non_equity_change,
        "equity_raw_change": equity_raw_change,
    }


def _apply_equity_hqla_cap(
    non_equity_change: float, equity_raw_change: float
) -> float:
    """执行指数成份股/宽基ETF折算额不超过HQLA总额15%的上限。"""
    firm = DEFAULT_CONFIG["firm"]
    total_base = firm["HQLA_base"] / 10000
    raw_base = max(0.0, firm.get("HQLA_equity_raw_base", 0.0) / 10000)

    counted_base = min(raw_base, total_base * 0.15)
    other_base = total_base - counted_base
    other_new = other_base + non_equity_change
    raw_new = max(0.0, raw_base + equity_raw_change)

    # counted <= 15%*(other+counted)，等价于 counted <= 15%/85%*other。
    cap_amount = max(0.0, other_new) * 0.15 / 0.85
    counted_new = min(raw_new, cap_amount)
    return other_new + counted_new - total_base


def _net_outflow(outflow: float, inflow: float) -> float:
    return outflow - min(inflow, 0.75 * outflow)


def _calc_net_cof_change(
    gross_outflow_change: float, gross_inflow_change: float = 0.0
) -> float:
    firm = DEFAULT_CONFIG["firm"]
    outflow_base = firm.get("LCR_outflow_base", firm["LCR_COF_base"]) / 10000
    inflow_base = firm.get("LCR_inflow_base", 0.0) / 10000
    old = _net_outflow(outflow_base, inflow_base)
    new = _net_outflow(
        outflow_base + gross_outflow_change,
        inflow_base + gross_inflow_change,
    )
    return new - old


def _finish_result(
    client_hqla_cash: float,
    client_outflow: float,
    contract_type: str,
    hedge_list: List[HedgeTrade],
) -> Dict[str, float]:
    hedge_hqla = _calc_hedge_hqla(contract_type, hedge_list)
    non_equity_change = client_hqla_cash + hedge_hqla["non_equity_change"]
    equity_raw_change = hedge_hqla["equity_raw_change"]
    gross_outflow_change = client_outflow + _calc_hedge_outflow(hedge_list)
    hqla_change = _apply_equity_hqla_cap(non_equity_change, equity_raw_change)
    net_cof_change = _calc_net_cof_change(gross_outflow_change)
    return {
        "hqla_change": hqla_change,
        "hqla_non_equity_change": non_equity_change,
        "hqla_equity_raw_change": equity_raw_change,
        "gross_outflow_change": gross_outflow_change,
        "gross_inflow_change": 0.0,
        "net_cof_change": net_cof_change,
    }


def _calc_option_lcr(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    outflow = (
        otc.notional * LCR_OUTFLOW_RATES["otc_short_option"]
        if otc.direction == "short"
        else 0.0
    )
    return _finish_result(
        otc.get_otc_cash_inflow(), outflow, otc.contract_type, hedge_list
    )


def _calc_swap_lcr(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    return _finish_result(
        otc.get_otc_cash_inflow(),
        otc.notional * LCR_OUTFLOW_RATES["equity_swap"],
        otc.contract_type,
        hedge_list,
    )


def _calc_income_cert_lcr(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    funds = otc.funds_raised if otc.funds_raised is not None else otc.notional
    outflow = funds if otc.term_days <= 30 else 0.0
    if otc.has_embedded_option:
        outflow += (otc.embedded_option_notional or otc.notional) * LCR_OUTFLOW_RATES[
            "otc_short_option"
        ]
    return _finish_result(funds, outflow, otc.contract_type, hedge_list)


def calc_lcr_impact(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, float]:
    """返回HQLA、毛流出及执行75%流入上限后的净流出边际变化。"""
    if otc.contract_type in ("call_option", "put_option"):
        return _calc_option_lcr(otc, hedge_list)
    if otc.contract_type == "equity_swap":
        return _calc_swap_lcr(otc, hedge_list)
    if otc.contract_type == "income_certificate":
        return _calc_income_cert_lcr(otc, hedge_list)
    return _finish_result(0.0, 0.0, otc.contract_type, hedge_list)
