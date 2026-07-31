# ============================================================
# backend/calculators/lcr.py - LCR（流动性覆盖率）影响计算
# ============================================================

from typing import Dict, List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from .ratios import HQLA_DISCOUNT


def _calc_hedge_outflow(hedge_list: List[HedgeTrade]) -> float:
    """
    计算交易端对冲工具的未来30日现金流出增量 ΔOutflow（万元）

    依据《证券公司流动性覆盖率计算表》（附件4）注7：
      - 股指期货：按合约名义价值总额的 20% 计算
      - 卖出场内期权：按 Delta 金额的 15% × 20% 计算
      - 场外背对背收益互换：按名义本金 × 0.2% 计算
      - ETF/股票现货/私募基金/买入场内期权等：0

    注：期货、卖出期权按单品种（合约标的）单边最大名义价值填列；
        本函数按单条对冲工具名义价值保守加总。
    """
    cof = 0.0
    for h in hedge_list:
        if h.tool_type == "futures":
            cof += h.notional * 0.20
        elif h.tool_type == "onsite_option" and h.direction == "short":
            delta_amount = abs(h.option_delta or 0.5) * h.notional
            cof += delta_amount * 0.15 * 0.20
        elif h.tool_type == "otc_hedge":
            # 视同为权益互换处理（模型中 otc_hedge 主要用于背对背互换/期权平盘，
            # 此处保守按互换 0.2% 计提；后续可依据结构细化）
            cof += h.notional * 0.002
    return cof


def _calc_hedge_hqla(hedge_list: List[HedgeTrade]) -> float:
    """
    计算交易端对冲工具的 ΔHQLA（优质流动性资产变动量，万元）

    【规则】
      现金流出直接减少 HQLA，但买入的现货/ETF 根据标的类型有不同折算率：
        - 指数成分股/宽基ETF：HQLA 折算率 50%
          例：买入 100 万沪深300 ETF → 现金 -100 + 现货×50% = 净 ΔHQLA = -50
        - 一般股票/期货保证金/期权权利金/私募：HQLA 折算率 0%
          例：支付期货保证金 12 万 → 净 ΔHQLA = -12

      卖出（做空）方向则反向：获得现金 +HQLA，失去现券 -HQLA×折算率
    """
    hqla = 0.0

    for h in hedge_list:
        trade_cash = h.get_trade_cash_outflow()  # 正值=现金流出券商, 负值=流入
        hqla -= trade_cash  # 现金流出 → HQLA 减少；流入 → HQLA 增加

        # 只有 ETF / 股票现货才产生 HQLA 资产折算
        if h.tool_type in ("etf", "stock"):
            hqla_rate = HQLA_DISCOUNT.get(h.underlying_type or h.stock_type, 0.0)
            if h.direction == "long":
                hqla += h.notional * hqla_rate   # 买入现券 → 获得 HQLA 资产
            elif h.direction == "short":
                hqla -= h.notional * hqla_rate   # 卖出现券 → 失去 HQLA 资产

    return hqla


def _calc_option_lcr(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    场外期权（call_option / put_option）的 LCR 影响计算
    """
    # --- ΔHQLA ---
    # 客户端：卖出收权利金(+), 买入付权利金(-)
    hqla_change = otc.get_otc_cash_inflow()
    # 交易端
    hqla_change += _calc_hedge_hqla(hedge_list)

    # --- ΔOutflow（未来30日现金净流出增量）---
    cof_change = 0.0
    if otc.direction == "short":
        # 卖出期权的表外项目折算：S_short × 20%
        # S_short = max(5 × 压力测试损失, 名义本金 × 0.5%)
        loss = otc.stress_loss if otc.stress_loss is not None else 0.0
        s_short = max(5 * loss, otc.notional * 0.005)
        cof_change = s_short * 0.20

    # 交易端对冲工具自身的资金流出（股指期货/卖出场内期权/背对背互换）
    cof_change += _calc_hedge_outflow(hedge_list)

    return {"hqla_change": hqla_change, "net_cof_change": cof_change}


def _calc_swap_lcr(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    收益互换（equity_swap）的 LCR 影响计算
    """
    # --- ΔHQLA ---
    # 客户端：收取保证金 +M
    hqla_change = otc.get_otc_cash_inflow()
    # 交易端
    hqla_change += _calc_hedge_hqla(hedge_list)

    # --- ΔOutflow ---
    # 收益互换作为自营业务资金流出，按名义本金 × 0.2% 折算
    cof_change = otc.notional * 0.002

    # 交易端对冲工具自身的资金流出
    cof_change += _calc_hedge_outflow(hedge_list)

    return {"hqla_change": hqla_change, "net_cof_change": cof_change}


def _calc_income_cert_lcr(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    收益凭证（income_certificate）的 LCR 影响计算

    判断是否为浮动收益凭证（含内嵌衍生品）：otc.stress_loss 不为 None
    """
    V = otc.funds_raised if otc.funds_raised is not None else otc.notional
    is_floating = otc.stress_loss is not None

    # --- ΔHQLA ---
    # 募集资金 V 带来 100% HQLA（全部货币资金流入），再减去对冲占用现金 + 补偿折算
    hqla_change = V
    hqla_change += _calc_hedge_hqla(hedge_list)

    # --- ΔOutflow ---
    cof_change = 0.0

    # 债务本金部分：若 T ≤ 30 天，到期需偿还全部本金 → 100% 流出
    if otc.term_days <= 30:
        cof_change += V

    # 内嵌期权部分（仅浮动收益凭证）
    if is_floating:
        loss = otc.stress_loss if otc.stress_loss is not None else 0.0
        s_short = max(5 * loss, otc.notional * 0.005)
        cof_change += s_short * 0.20

    # 交易端对冲工具自身的资金流出
    cof_change += _calc_hedge_outflow(hedge_list)

    return {"hqla_change": hqla_change, "net_cof_change": cof_change}


def calc_lcr_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    计算对 LCR（流动性覆盖率）的影响

    【LCR = HQLA / 未来30日现金净流出 ≥ 100%】
      HQLA = High Quality Liquid Assets（优质流动性资产）
      ΔLCR = (HQLA_base + ΔHQLA) / (Outflow_base + ΔOutflow) - LCR_base

    三种产品分别有独立的计算逻辑：
      1. 场外期权（call_option / put_option）
      2. 收益互换（equity_swap）
      3. 收益凭证（income_certificate）

    Returns:
        {"hqla_change": ΔHQLA（万元）, "net_cof_change": Δ未来30日现金净流出（万元）}
    """
    ct = otc.contract_type

    if ct in ("call_option", "put_option"):
        return _calc_option_lcr(otc, hedge_list)
    elif ct == "equity_swap":
        return _calc_swap_lcr(otc, hedge_list)
    elif ct == "income_certificate":
        return _calc_income_cert_lcr(otc, hedge_list)
    else:
        return {"hqla_change": 0.0, "net_cof_change": 0.0}
