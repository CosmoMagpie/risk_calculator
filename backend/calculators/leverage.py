# ============================================================
# backend/calculators/leverage.py - 资本杠杆率变动量计算
# ============================================================

from typing import List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from ..services.ifind_client import get_underlying_spot_price, get_onsite_option_greeks

# ============================================================
# 辅助函数
# ============================================================
def _get_short_scale(option_type: str, 
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
    if "call" in option_type:
        unit_pressure_loss = pressure_upper_bond - exercise_price if pressure_upper_bond > exercise_price else 0.0
    else:
        unit_pressure_loss = exercise_price - pressure_lower_bond if exercise_price > pressure_lower_bond else 0.0
    # 计算压力损失: 单位压力损失 × 合约乘数 × 合约规模
    pressure_loss = unit_pressure_loss * contract_multiplier * contract_size
    investment_size = max(notional * 0.005, 5 * pressure_loss)
    return investment_size


def _is_swap_penalty(otc: OtcContract) -> bool:
    """收益互换惩罚条件：非全额保证金 + 个股标的"""
    if otc.contract_type != "equity_swap":
        return False
    # 条件A：非全额保证金
    if otc.equity_swap_margin_amount is not None:
        non_full = otc.equity_swap_margin_amount < otc.notional
    elif otc.equity_swap_margin_rate is not None:
        non_full = otc.equity_swap_margin_rate < 100.0
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

    场外期权：买入=0，卖出=压力损失与名义本金0.5%孰高法
    收益互换：一般=N×10%，惩罚情况=N×20%
    收益凭证：固定=0，浮动=压力损失与名义本金0.5%孰高法
    """
    ct = otc.get_otc_contract_type()
    
    # ===== 期权 =====
    if "option" in ct:
        # 买入期权：不产生表外项目
        if otc.get_otc_contract_direction() == "long":
            return 0.0
        
        # 卖出期权：需要计算投资规模
        # 检查必要的参数是否存在
        option_type = otc.get_option_type()
        underlying_code = otc.get_otc_underlying_code()
        spot_type = otc.get_otc_underlying_type()
        notional = otc.get_otc_contract_notional()
        contract_multiplier = otc.get_contract_multiplier()
        contract_size = otc.get_contract_size()
        exercise_price = otc.get_exercise_price()
        
        # 参数校验：如果关键参数缺失，返回 0 或打印警告
        if not all([
            underlying_code,
            spot_type,
            notional,
            contract_multiplier,
            contract_size,
            exercise_price,
            option_type
        ]):
            print(f"[警告] 卖出期权缺少必要参数，无法计算表外项目。缺失项: "
                  f"underlying_code={underlying_code}, spot_type={spot_type}, "
                  f"notional={notional}, contract_multiplier={contract_multiplier}, "
                  f"contract_size={contract_size}, exercise_price={exercise_price}, "
                  f"option_type={option_type}")
            return 0.0
        
        return _get_short_scale(
            option_type=option_type,
            underlying_code=underlying_code,
            spot_type=spot_type,
            notional=notional,
            contract_multiplier=contract_multiplier,
            contract_size=contract_size,
            exercise_price=exercise_price,
        )
    
    # ===== 收益互换 =====
    elif ct == "equity_swap":
        base = otc.get_otc_contract_notional() * 0.10
        if _is_swap_penalty(otc):
            base *= 2.0
        return base
    
    # ===== 收益凭证 =====
    elif ct == "income_certificate":
        # 固定型收益凭证：无表外项目
        if not otc.get_is_float_income():
            return 0.0
        
        # 浮动型收益凭证：需要计算投资规模
        option_type = otc.get_option_type()
        underlying_code = otc.get_otc_underlying_code()
        spot_type = otc.get_otc_underlying_type()
        notional = otc.get_otc_contract_notional()
        contract_multiplier = otc.get_contract_multiplier()
        contract_size = otc.get_contract_size()
        exercise_price = otc.get_exercise_price()
        
        # 参数校验
        if not all([
            underlying_code,
            spot_type,
            notional,
            contract_multiplier,
            contract_size,
            exercise_price
        ]):
            print(f"[警告] 浮动收益凭证缺少必要参数，无法计算表外项目")
            return 0.0
        
        return _get_short_scale(
            option_type=option_type,
            underlying_code=underlying_code,
            spot_type=spot_type,
            notional=notional,
            contract_multiplier=contract_multiplier,
            contract_size=contract_size,
            exercise_price=exercise_price,
        )
    
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
        if h.tool_type in ("index_fund", "other_equity_fund", "monetary_fund", "interest_rate_bond_index_fund", "other_non_equity_fund", 
                           "index_component", "general_stock", "restricted_stock", "other_stock", 
                           "single_product(private fund)", "collection_and_trust", "bulk_commodity"):
            continue  # = 0

        elif h.tool_type == "stock_index_future":
            total += h.notional * 0.15

        elif h.tool_type == "treasury_future":
            total += h.notional * 0.05

        elif h.tool_type == "bulk_commodity_future":
            total += h.notional * 0.10

        elif h.tool_type == "onsite_option":
            if h.direction == "short":
                delta_amount = (h.option_delta or 0.5) * h.notional
                total += delta_amount * 0.15

        elif h.tool_type in ("equity_swap", "otc_option"):
            if ct in ("option", "income_certificate"):
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
