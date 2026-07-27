# ============================================================
# backend/calculators/risk_reserve.py - 风险资本准备计算
# ============================================================

from typing import List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from ..config import DEFAULT_CONFIG
from .ratios import RATES


def calc_market_risk_reserve(otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool) -> float:
    """
    计算市场风险资本准备（万元）

    【监管背景】这是风险覆盖率指标的分母组成部分。
               根据《证券公司风险控制指标计算标准规定》，不同资产类别有不同计提比例。

    【注意】当前函数有多处使用了不存在的key（如 RATES["buy_option"]、RATES["futures_swap"]），
           在实际运行时会抛出 KeyError。这是未完成代码的标志。
           原意应该是用 RATES 中定义的具体类型key。
    """
    reserve = 0.0

    # --- 场外合约风险敞口 ---
    # ⚠️ 注意：此处的 contract_type 判断用了 "option"/"swap"/"income_note"，
    #    但 OtcContract 中实际用的是 "call_option"/"put_option"/"equity_swap"/"income_certificate"
    #    这些判断可能无法正确匹配。使用前需确认字符串一致性。
    if otc.contract_type == "option":
        if otc.direction == "buy":
            premium = otc.notional * (otc.premium_rate or DEFAULT_CONFIG["client"]["option_premium_rate"]) / 100
            reserve += premium * RATES["buy_option"]  # ⚠️ BUG: "buy_option" 不在 RATES 中
        else:  # 卖出期权
            if otc.stress_loss is not None:
                # 卖出场外期权：虚拟本金 = max(压力损失×5, 名义本金×0.5%)
                virtual = max(otc.stress_loss * 5, otc.notional * 0.005)
                reserve += virtual * RATES["futures_swap"]  # ⚠️ BUG: "futures_swap" 不在 RATES 中
            elif otc.delta_amount is not None:
                # 卖出场内期权：Delta金额 × 15% × 风险系数
                # ⚠️ BUG: otc 没有 delta_amount 属性，应该是 otc.get_otc_delta_amount()
                reserve += otc.delta_amount * 0.15 * RATES["futures_swap"]
            else:
                # 默认按名义本金估算
                reserve += otc.notional * 0.30 * RATES["futures_swap"]

    elif otc.contract_type == "swap":
        exposure = otc.notional * 0.10  # 互换风险敞口 = 名义本金 × 10%
        reserve += exposure * RATES["futures_swap"]  # ⚠️ BUG: key不存在
        if otc.margin_rate is not None and otc.margin_rate < 100:
            reserve *= 2  # 非全额保证金互换，风险准备翻倍（监管要求）

    elif otc.contract_type == "income_note":
        if otc.expected_yield > 0.05:
            # 收益凭证预期收益率 > 5% 才有市场风险
            reserve += otc.notional * 0.05 * RATES["futures_swap"]  # ⚠️ BUG: key不存在

    # 有效对冲减免：对冲有效 → 风险准备打5%折扣（减免95%）
    if is_hedge_effective and hedge_list:
        reserve *= 0.05

    return reserve


def calc_credit_risk_reserve(otc: OtcContract) -> float:
    """
    计算信用风险资本准备（万元）

    【监管背景】对于非全额保证金的收益互换，客户可能违约不补保证金，
               因此需要计提信用风险资本准备。

    当前仅对标的为"general_stock"的非全额保证金互换计提5%
    """
    if otc.contract_type == "swap" and otc.margin_rate is not None and otc.margin_rate < 100:
        if otc.underlying_type == "general_stock":
            return otc.notional * 0.05
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
        # + calc_operational_risk_reserve()  # 操作风险资本准备（未实现）
        # + calc_specific_risk_reserve()     # 特定风险资本准备（未实现）
    )
    total *= DEFAULT_CONFIG["firm"]["classification_factor"]  # 乘以证监会分类评价系数
    return total
