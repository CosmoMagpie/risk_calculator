# ============================================================
# backend/calculators/risk_reserve.py - 风险资本准备计算
# ============================================================

from typing import List

from ..services.ifind_client import get_underlying_spot_price, get_onsite_option_greeks
from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from ..config import DEFAULT_CONFIG
from .ratios import RATES

def otc_option_short_investment_size(option_type: str, 
                          underlying_code: str, 
                          spot_type: str,  
                          notional: float, 
                          contract_multiplier: int, 
                          contract_size: int, 
                          exercise_price: float, 
                          market: str = 'CN') -> float:
    '''计算卖出场外期权的投资规模
    【计算方法】：5倍压力损失与名义本金的0.5%孰高法，其中压力情形为标的现货价格上下浮动20%

    args:
        option_type(str): 期权类型（如 'call', 'put'）
        underlying_code (str): 标的代码
        spot_type (str): 现货类型（如 'index', 'stock', 'future'）
        market (str): 市场（如 'CN', 'US'）
        notional (float): 名义本金
        contract_multiplier (int): 合约乘数
        contract_size (int): 合约规模
        excercise_price (float): 行权价格

    returns:
        float: 投资规模
    '''
    spot_price = get_underlying_spot_price(underlying_code, spot_type, market)
    if spot_price is None:
        return 0.0
    pressure_lower_bond = spot_price * (1 - 0.20)
    pressure_upper_bond = spot_price * (1 + 0.20)
    # 计算单位压力损失
    if option_type == "call":
        unit_pressure_loss = pressure_upper_bond - exercise_price if pressure_upper_bond > exercise_price else 0.0
    else:
        unit_pressure_loss = exercise_price - pressure_lower_bond if exercise_price > pressure_lower_bond else 0.0
    # 计算压力损失: 单位压力损失 × 合约乘数 × 合约规模
    pressure_loss = unit_pressure_loss * contract_multiplier * contract_size
    investment_size = max(notional * 0.5, 5 * pressure_loss)
    return investment_size


def _calc_hedge_trade_market_risk_reserve(hedge_list: List[HedgeTrade], is_effective_hedge: bool) -> float:
    '''计算对冲工具的市场风险资本准备（万元）
    
    args:
        hedge_list (List[HedgeTrade]): 对冲工具列表
        is_effective_hedge (bool): 是否满足对冲条件

    returns:
        float: 市场风险资本准备（万元）
    '''
    # 必要信息
    hedgetool_basic_parameters = [(h.get_tool_type(),  #0
                                   h.get_tool_notional(),  #1
                                   h.get_tool_direction(), #2
                                   h.get_tool_code(),  #3
                                   h.get_total_premium_amount(), #4
                                   h.get_single_premium_amount(), #5
                                   h.get_option_type(), #6
                                   h.get_tool_underlying_code(), #7
                                   h.get_tool_underlying_type(), #8
                                   h.get_option_contract_multiplier(), #9
                                   h.get_option_contract_size(), #10
                                   h.get_option_exercise_price(), #11
                                   h.get_tool_underlying_market(), #12
                                   ) for h in hedge_list]
    hedge_reserve = 0.0
    for h in hedgetool_basic_parameters:
        # 是否为权益类指示器
        is_equity = False if h[0] in ['bulk_commodity', 'bulk_commodity_futures', 'single_product', 'non_equity_securities'] else True

        # 对于非期权对冲工具，直接用名义金额*相应系数
        if "option" not in h[0]:
            if is_effective_hedge and is_equity:
                hedge_reserve += RATES[h[0]] * h[1] * RATES['effective_hedge']['equity_securities_and_derivatives']  # 权益类减免系数为5%
            elif is_effective_hedge and not is_equity:
                hedge_reserve += RATES[h[0]] * h[1] * RATES['effective_hedge']['non_equity_securities_and_derivatives'] # 非权益类减免系数为1%
            hedge_reserve += RATES[h[0]] * h[1]

        # 对于期权对冲工具，情况极为复杂！
        else:
            # 买入时场内场外投资金额计算规则一致，且权益与非权益处理一致
            if h[2] == "long":
                if h[4] is not None: # 总权利金非空
                    reserve_change = RATES['equity_long_option'] * h[4]
                else:  # 总权利金为空，用单权利金*合约数量
                    reserve_change = RATES['equity_long_option'] * h[5] * h[10]
                if is_effective_hedge:
                    hedge_reserve += reserve_change * RATES['effective_hedge']['equity_securities_and_derivatives'] if is_equity else reserve_change * RATES['effective_hedge']['non_equity_securities_and_derivatives']
                else:
                    hedge_reserve += reserve_change

            # 卖出时，先分场内外的投资规模，再分权益与非权益的系数差异
            else:
                if h[0] == "onsite_option":
                    # 对于场内卖出期权，按照期权代码查找delta值，乘以名义本金，再乘15%
                    invest_size = 0.15 * get_onsite_option_greeks(h[3], 'delta') * h[1]
                else:
                    # 对于场外卖出期权，直接调投资规模函数
                    invest_size = otc_option_short_investment_size(h[6], h[7], h[7], h[8], h[9], h[10], h[11], h[12])
                if is_equity:
                    if is_effective_hedge:  # 权益类卖出期权减免系数为30%，若为有效对冲再乘0.05减免
                        hedge_reserve += RATES['equity_short_option'] * RATES['effective_hedge']['equity_securities_and_derivatives'] * invest_size
                    else:
                        hedge_reserve += RATES['equity_short_option'] * invest_size
                else:
                    if is_effective_hedge:  # 非权益类卖出期权减免系数为20%，若为有效对冲再乘0.01减免
                        hedge_reserve += RATES['non_equity_short_option'] * RATES['effective_hedge']['non_equity_securities_and_derivatives'] * invest_size
                    else:
                        hedge_reserve += RATES['non_equity_short_option'] * invest_size  
    return hedge_reserve


def _calc_otc_option_market_risk_reserve(otc: OtcContract, is_effective_hedge: bool) -> float:
    """
    计算场外期权（仅限场外合约端）的市场风险资本准备（万元）

    args:
        otc (OtcContract): 场外合约对象
        is_effective_hedge (bool): 是否满足对冲条件

    returns:
        float: 市场风险资本准备（万元）
    """
    # 基本信息
    direction = otc.get_otc_contract_direction()
    option_type = otc.get_option_type()
    underlying_code = otc.get_otc_underlying_code()
    underlying_type = otc.get_otc_underlying_type()
    if otc.get_otc_underlying_market() is None:
        underlying_market = 'CN'
    else:
        underlying_market = otc.get_otc_underlying_market()
    option_notional = otc.get_otc_contract_notional()
    option_multiplier = otc.get_contract_multiplier()
    option_size = otc.get_contract_size()
    option_exercise_price = otc.get_exercise_price()
    option_premium = otc.get_total_premium_amount() if otc.get_total_premium_amount() is not None else otc.get_single_premium_amount() * otc.get_contract_size()

    otc_reserve = 0.0
    is_equity = False if otc.get_otc_underlying_type() in ['bulk_commodity', 'bulk_commodity_futures', 'single_product', 'non_equity_securities'] else True
    if direction == "short":
        # 卖出场外期权，用压力测试下最大损失金额5倍与名义本金的0.5%孰高法计算投资规模
        investment_size = otc_option_short_investment_size(option_type, 
                                                           underlying_code, 
                                                           underlying_type,  
                                                           option_notional, 
                                                           option_multiplier, 
                                                           option_size, 
                                                           option_exercise_price, 
                                                           underlying_market)
        if is_equity:
            otc_reserve += RATES['equity_short_option'] * investment_size  # 权益类卖出期权减免系数为30%
            if is_effective_hedge:
                otc_reserve *= RATES['effective_hedge']['equity_securities_and_derivatives']  # 若满足对冲条件再进行0.05减免
        else:
            otc_reserve += RATES['non_equity_short_option'] * investment_size  # 非权益类卖出期权减免系数为20%
            if is_effective_hedge:
                otc_reserve *= RATES['effective_hedge']['non_equity_securities_and_derivatives']  # 若满足对冲条件再进行0.01减免
    else:
        # 买入场外期权投资规模按权利金总额计算
        otc_reserve += RATES['equity_long_option'] * option_premium  # 不论底层属于权益类还是非权益类，系数均取100%
        if is_effective_hedge:  # 满足对冲条件时同卖出期权情况
            otc_reserve *= RATES['effective_hedge']['equity_securities_and_derivatives'] if is_equity else RATES['effective_hedge']['non_equity_securities_and_derivatives']
    return otc_reserve


def _calc_otc_equity_swap_market_risk_reserve(otc: OtcContract, is_effective_hedge: bool) -> List[float, bool]:
    """
    计算场外收益互换（仅限场外合约端）的市场风险资本准备（万元）

    args:
            otc (OtcContract): 场外合约对象
            is_effective_hedge (bool): 是否满足对冲条件
    
    returns:
        float: 市场风险准备（万元）
        bool: 是否满足惩罚条件【A: 非全额保证金; B: 标的为境内个股】
    """
    notional = otc.get_otc_contract_notional()
    underlying_type = otc.get_otc_underlying_type()
    margin_amount = otc.get_equity_swap_margin_amount()
    margin_rate = otc.get_equity_swap_margin_rate()
    condition = False
    if underlying_type in ['index_component', 'general_stock', 'restricted_stock', 'other_stock']:
        if margin_amount is not None:
            condition = margin_amount < notional
        elif margin_rate is not None:
            condition = margin_rate < 1.0
    reserve = notional * RATES['equity_swap'] * 2 if condition else notional * RATES['equity_swap']
    if is_effective_hedge:
        reserve *= 0.05
    return [reserve, condition]


def _calc_otc_income_certificate_market_risk_reserve(otc: OtcContract, is_effective_hedge: bool) -> float:
    """
    计算场外收入凭证（仅限场外合约端）的市场风险资本准备（万元）
    
    """
    reserve = 0.0
    # 若为浮动收益，风险资本准备同场外期权，直接调用
    if otc.get_is_float_income():
        reserve += _calc_otc_option_market_risk_reserve(otc, is_effective_hedge)
    return reserve


def calc_market_risk_reserve(otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool) -> float:
    """
    计算市场风险资本准备（万元）
    """

    hedge_reserve = _calc_hedge_trade_market_risk_reserve(hedge_list, is_hedge_effective) if hedge_list else 0.0

    otc_reserve = 0.0
    if "option" in otc.get_otc_contract_type():
        otc_reserve += _calc_otc_option_market_risk_reserve(otc, hedge_list, is_hedge_effective)
    elif "swap" in otc.get_otc_contract_type():
        otc_reserve += _calc_otc_equity_swap_market_risk_reserve(otc, hedge_list, is_hedge_effective)[0]
        condition = _calc_otc_equity_swap_market_risk_reserve(otc, hedge_list, is_hedge_effective)[1]
        if condition: # 满足惩罚条件，收益互换的对冲端风险资本准备加倍，场外合约自身已经在函数中加倍，不必考虑
            hedge_reserve *= 2
    elif "income_certificate" in otc.get_otc_contract_type():
        otc_reserve += _calc_otc_income_certificate_market_risk_reserve(otc, hedge_list, is_hedge_effective)

    market_reserve = otc_reserve + hedge_reserve
    return market_reserve


def calc_credit_risk_reserve(otc: OtcContract) -> float:
    """
    计算信用风险资本准备（万元）

    【监管背景】对于非全额保证金的收益互换，客户可能违约不补保证金，
               因此需要计提信用风险资本准备。

    当前仅对非全额保证金互换计提5%
    """
    if "swap" in otc.get_otc_contract_type():
        if otc.get_equity_swap_margin_amount() is not None:
            if otc.get_equity_swap_margin_amount() < otc.get_otc_contract_notional():
                return otc.get_otc_contract_notional() * 0.05
        elif otc.get_equity_swap_margin_rate() is not None:
            if otc.get_equity_swap_margin_rate() < 1.0:
                return otc.get_otc_contract_notional() * 0.05
    return 0.0


def calc_total_risk_reserve(otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool) -> float:
    """
    计算各项风险资本准备合计（万元）

    【组成】市场风险 + 信用风险 + 操作风险（待实现）+ 特定风险（待实现）
    【分类评价系数】证监会根据券商评级调整最终风险准备，评级越高系数越低
      AAA=0.4, AA=0.6, A=0.8, BBB=0.9, BB=1.0, B=1.0, C=1.0, D=2.0
    """
    total = (
        calc_market_risk_reserve(otc, hedge_list, is_hedge_effective)
        + calc_credit_risk_reserve(otc)
        # + calc_operational_risk_reserve()  # 操作风险资本准备（未实现，如有需要再补充）
        # + calc_specific_risk_reserve()     # 特定风险资本准备（未实现，如有需要再补充）
    )
    total *= DEFAULT_CONFIG["firm"]["classification_factor"]  # 乘以证监会分类评价系数
    return total
