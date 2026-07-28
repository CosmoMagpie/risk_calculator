# ============================================================
# backend/calculators/net_capital.py - 净资本变动计算
# ============================================================

from typing import Dict, List
from ..config import DEFAULT_CONFIG
from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade

def calc_nc_impact(otc: OtcContract, hedge_list: List[HedgeTrade]):
    '''计算净资本变动'''
    nc_impact = 0.0
    if hedge_list:
        for h in hedge_list:
            # 场内卖出期权保证金
            if h.get_tool_type() == 'onsite_option' and h.get_tool_direction() == 'short':
                if h.get_option_margin():
                    nc_impact -= h.get_option_margin() 
                elif h.get_option_margin_rate():
                    nc_impact -= h.get_option_margin_rate() * h.get_tool_notional()
                else:
                    nc_impact -= DEFAULT_CONFIG['trade']['onsite_option_margin_rate'] * h.get_tool_notional()
            # 期货保证金
            elif h.get_tool_type() == 'futures':
                if h.get_futures_margin(): 
                    nc_impact -= h.get_futures_margin() 
                elif h.get_futures_margin_rate(): 
                    nc_impact -= h.get_futures_margin_rate() * h.get_tool_notional()
                else:
                    nc_impact -= DEFAULT_CONFIG['trade']['futures_margin_rate'] * h.get_tool_notional()
            else:
                continue
    # 场外卖出期权保证金
    if otc.get_otc_contract_type() == 'option' and otc.get_otc_contract_direction() == 'short':
        if otc.get_option_margin_amount():
            nc_impact -= otc.get_option_margin_amount()
        elif otc.get_option_margin_rate():
            nc_impact -= otc.get_option_margin_rate() * otc.get_otc_contract_notional()
        else:
            nc_impact -= DEFAULT_CONFIG['client']['option_margin_rate'] * otc.get_otc_contract_notional()
    return nc_impact
