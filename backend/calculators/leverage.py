# ============================================================
# backend/calculators/leverage.py - 资本杠杆率变动量计算
# ============================================================

from typing import List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade


# ============================================================
# 辅助函数
# ============================================================

def _get_short_scale(notional: float, stress_loss: float = 0.0) -> float:
    """卖出期权投资规模 S_short = max(5 × L_stress, N × 0.5%)"""
    return max(5 * stress_loss, notional * 0.005)


def _is_swap_penalty(otc: OtcContract) -> bool:
    """收益互换惩罚条件：非全额保证金 + 个股标的"""
    if otc.contract_type != "equity_swap":
        return False
    # 条件A：非全额保证金
    if otc.margin_amount is not None:
        non_full = otc.margin_amount < otc.notional
    elif otc.margin_rate is not None:
        non_full = otc.margin_rate < 100.0
    else:
        non_full = True  # 默认10%，必然非全额
    # 条件B：个股标的
    is_stock = otc.underlying_type not in ("index_component",)
    return non_full and is_stock


# ============================================================
# 表外项目余额计算
# ============================================================

def _calc_client_off_balance(otc: OtcContract) -> float:
    """
    计算客户端 Δ表外项目余额（万元）

    场外期权：买入=0，卖出=S_short
    收益互换：一般=N×10%，惩罚情况=N×20%
    收益凭证：固定=0，浮动=S_short
    """
    ct = otc.contract_type

    if ct in ("call_option", "put_option"):
        if otc.direction == "short":
            loss = otc.stress_loss or 0.0
            return _get_short_scale(otc.notional, loss)
        return 0.0

    elif ct == "equity_swap":
        base = otc.notional * 0.10
        if _is_swap_penalty(otc):
            base *= 2.0
        return base

    elif ct == "income_certificate":
        if otc.stress_loss is not None:
            return _get_short_scale(otc.notional, otc.stress_loss)
        return 0.0

    return 0.0


def _calc_hedge_off_balance(hedge_list: List[HedgeTrade], ct: str, is_swap_pen: bool) -> float:
    """
    计算交易端 Δ表外项目余额（万元）

    现货/ETF/私募：0
    场内股指期货：名义价值 × 15%
    场内卖出期权：Delta金额 × 15%
    场外背对背（期权类）：N × 0.5%（无 stress_loss 时取地板值）
    场外背对背（互换类）：N × 10%（惩罚 ×2）
    """
    total = 0.0

    for h in hedge_list:
        if h.tool_type in ("etf", "stock", "private_fund"):
            continue  # = 0

        elif h.tool_type == "futures":
            total += h.notional * 0.15

        elif h.tool_type == "onsite_option":
            if h.direction == "short":
                delta_amount = (h.option_delta or 0.5) * h.notional
                total += delta_amount * 0.15

        elif h.tool_type == "otc_hedge":
            if ct in ("call_option", "put_option", "income_certificate"):
                # 期权类平盘：无 stress_loss 数据，取监管地板值 N × 0.5%
                total += h.notional * 0.005
            elif ct == "equity_swap":
                base = h.notional * 0.10
                if is_swap_pen:
                    base *= 2.0
                total += base

    return total


# ============================================================
# 主导出函数
# ============================================================

def calc_leverage_impact(
    otc: OtcContract, hedge_list: List[HedgeTrade], net_day1_cash: float = 0.0
) -> float:
    """
    计算业务对资本杠杆率分母（表内外资产总额）的增量影响（万元）

    【公式】
      Δ表内外资产总额 = Δ表内资产余额 + Δ表外项目余额
      Δ表内资产余额 = 首日净现金流入额
      Δ表外项目余额 = Δ表外_client + Δ表外_hedge

      资本杠杆率 = 核心净资本 / 表内外资产总额 ≥ 8%

    三种产品分别有独立的表外计算逻辑：
      1. 场外期权：买入=0，卖出=S_short；对冲端期货×15%/场内卖期权×15%
      2. 收益互换：N×10%（惩罚×2）；对冲端同比例
      3. 收益凭证：固定=0，浮动=S_short；对冲端同上

    Args:
        otc: 场外合约
        hedge_list: 对冲工具列表
        net_day1_cash: 首日净现金流（万元），用于 Δ表内余额

    Returns:
        float: Δ表内外资产总额（万元）
    """
    ct = otc.contract_type
    is_pen = _is_swap_penalty(otc) if ct == "equity_swap" else False

    on_balance = net_day1_cash                           # Δ表内 = 首日净现金流入
    off_client = _calc_client_off_balance(otc)           # Δ表外_client
    off_hedge = _calc_hedge_off_balance(hedge_list, ct, is_pen)  # Δ表外_hedge

    return on_balance + off_client + off_hedge
