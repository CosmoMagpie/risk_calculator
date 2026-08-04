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
      本函数汇总交易所期货（期权）合约已占用的交易保证金扣减。

    【计算逻辑】
      交易端：
        - 场内卖出期权：按 option_margin（或 option_margin_rate × notional）扣减
        - 期货（不分多空）：按 futures_margin（或 futures_margin_rate × notional）扣减
        - 其他工具（ETF/现货/场外背对背/私募）：不扣减净资本
      客户端场外期权保证金不属于附件1注1定义的期货（期权）交易保证金，
      不能在缺少会计科目映射时直接按100%扣减；如属于其他履约保证金，应另按行次5口径处理。

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

    return nc_impact
