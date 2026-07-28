# ============================================================
# backend/calculators/net_capital.py - 净资本变动计算
# ============================================================

from typing import List

from ..config import DEFAULT_CONFIG
from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade


def calc_nc_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> float:
    """
    计算保证金占用对净资本的变动影响（万元，负值=减少净资本）

    【监管背景】
      净资本 = 核心净资本 - 保证金占用（期货/卖出期权缴纳的保证金会扣减净资本）
      本函数汇总：①交易端对冲工具的保证金扣减 + ②客户端卖出期权的保证金扣减

    【计算逻辑】
      交易端：
        - 场内卖出期权：按 option_margin（或 option_margin_rate × notional）扣减
        - 期货（不分多空）：按 futures_margin（或 futures_margin_rate × notional）扣减
        - 其他工具（ETF/现货/场外背对背/私募）：不扣减净资本
      客户端：
        - 卖出场外期权：按 option_margin_amount（或 option_margin_rate × notional）扣减
        - 买入期权/互换/凭证：不扣减净资本

    Args:
        otc: 场外合约
        hedge_list: 对冲工具列表

    Returns:
        float: 净资本变动（万元，≤0）
    """
    nc_impact = 0.0

    # === 交易端：对冲工具保证金扣减 ===
    for h in hedge_list:
        # 场内卖出期权 — 保证金扣减净资本
        if h.tool_type == "onsite_option" and h.direction == "short":
            if h.option_margin is not None:
                nc_impact -= h.option_margin
            elif h.option_margin_rate is not None:
                nc_impact -= h.option_margin_rate * h.notional
            else:
                nc_impact -= DEFAULT_CONFIG["trade"]["onsite_option_margin_rate"] * h.notional

        # 期货 — 保证金扣减净资本（不分多空方向）
        elif h.tool_type == "futures":
            if h.futures_margin is not None:
                nc_impact -= h.futures_margin
            elif h.futures_margin_rate is not None:
                nc_impact -= h.futures_margin_rate * h.notional
            else:
                nc_impact -= DEFAULT_CONFIG["trade"]["futures_margin_rate"] * h.notional

    # === 客户端：卖出场外期权保证金扣减 ===
    if otc.contract_type in ("call_option", "put_option") and otc.direction == "short":
        if otc.option_margin_amount is not None:
            nc_impact -= otc.option_margin_amount
        elif otc.option_margin_rate is not None:
            nc_impact -= otc.option_margin_rate * otc.notional
        else:
            nc_impact -= DEFAULT_CONFIG["client"]["option_margin_rate"] * otc.notional

    return nc_impact
