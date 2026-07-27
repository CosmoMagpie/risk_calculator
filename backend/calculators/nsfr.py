# ============================================================
# backend/calculators/nsfr.py - NSFR（净稳定资金率）影响计算
# ============================================================

from typing import Dict, List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade


def calc_nsfr_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    计算对 NSFR（净稳定资金率）的影响

    【NSFR = 可用稳定资金(ASF) / 所需稳定资金(RSF) ≥ 100%】
      ASF = Available Stable Funding（负债端，期限越长越稳定）
      RSF = Required Stable Funding（资产端，流动性越差需要越多稳定资金）

    【监管规则要点】
      - 期限≥1年的负债可按较高比例计入ASF
      - 各类资产按流动性不同有不同RSF系数（如股票50%，私募20%）
    """
    asf_change = 0.0
    rsf_change = 0.0

    # --- 可用稳定资金（ASF）变动 ---
    # 收益凭证：期限>=1年 → 100%计入ASF（属于稳定的长期负债）
    if otc.contract_type == "income_note" and otc.term_days >= 365:
        asf_change += otc.funds_raised or otc.notional

    # 互换保证金：期限>=1年 → 按50%计入ASF
    if otc.contract_type == "swap" and otc.term_days >= 365:
        asf_change += otc.notional * (otc.margin_rate or 10) / 100 * 0.5

    # --- 所需稳定资金（RSF）变动 ---
    if otc.contract_type == "option":
        if otc.direction == "buy":
            # 买入期权：权利金部分需要稳定资金
            premium = otc.notional * (otc.premium_rate or 5) / 100
            rsf_change += premium
        else:
            # 卖出期权：名义本金的30%需要稳定资金
            rsf_change += otc.notional * 0.30

    elif otc.contract_type == "swap":
        # 互换：名义本金的1%
        rsf_change += otc.notional * 0.01

    # 对冲端 RSF 计提
    for hedge in hedge_list:
        if hedge.tool_type == "etf" or hedge.tool_type == "stock_basket":
            rsf_change += hedge.notional * 0.50  # ETF/股票：50%
        elif hedge.tool_type == "private_fund":
            rsf_change += (hedge.subscription_amount or 0) * 0.20  # 私募基金：20%
        elif hedge.tool_type == "otc_hedge":
            rsf_change += hedge.notional * 0.01  # 场外背对背：1%

    return {"asf_change": asf_change, "rsf_change": rsf_change}
