# ============================================================
# backend/calculators/lcr.py - LCR（流动性覆盖率）影响计算
# ============================================================

from typing import Dict, List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade


def calc_lcr_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    计算对 LCR（流动性覆盖率）的影响

    【LCR = HQLA / 未来30日现金净流出 ≥ 100%】
      HQLA = High Quality Liquid Assets（优质流动性资产）
      COF  = Cash Outflow（现金净流出）

    【本函数的简化处理】
      1. 场外合约现金流入直接增加HQLA
      2. 对冲端现金流出直接减少HQLA
      3. 仅30日内到期的合约才计入COF（压力情景下的现金流出）
      4. 未完整处理CIF(Cash Inflow)抵扣（因监管对CIF抵扣有上限限制）
    """
    hqla_change = 0.0  # HQLA变动量
    cof_change = 0.0   # 未来30日现金净流出变动量

    # 场外合约现金变动 → HQLA
    otc_cash = otc.get_otc_cash_inflow()
    hqla_change += otc_cash

    # 对冲端现金变动 → HQLA（注意负号：流出减少HQLA，流入增加HQLA）
    for hedge in hedge_list:
        trade_cash = hedge.get_trade_cash_outflow()
        hqla_change -= trade_cash  # 对冲端流出=券商花钱=HQLA减少

    # 30日内到期现金流 → 计入COF
    if otc.term_days <= 30:
        if otc.contract_type == "income_note":
            # 收益凭证30日内到期：需偿还募集资金
            cof_change += otc.funds_raised or otc.notional  # X or Y：取第一个非None/非零值
        elif otc.contract_type == "swap":
            # 互换30日内到期：需返还客户保证金
            cof_change += otc.notional * (otc.margin_rate or 10) / 100

    return {
        "hqla_change": hqla_change,
        "net_cof_change": cof_change,  # 简化，未处理CIF抵扣
    }
