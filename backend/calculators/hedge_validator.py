# ============================================================
# backend/calculators/hedge_validator.py - 有效对冲判断
# ============================================================

import numpy as np
from typing import List, Optional

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from ..services.ifind_client import (
    get_underlying_price_series,
    calculate_correlation_between_price_series,
    get_onsite_option_greeks,
)


def _collect_deltas(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Optional[List[float]]:
    """
    收集所有头寸的带符号 Delta 敞口金额（万元），正数=多头，负数=空头

    【重要】场外期权的 direction 是 "buy"/"short"，互换是 "long"/"short"，
           此函数不依赖 direction 字符串，而是依赖 get_*_delta_amount 返回
           的数学符号（正=做多标的，负=做空标的）。

    Returns:
        所有 delta 值的列表，如 [50, -30, -20]；任一获取失败则返回 None
    """
    deltas = []

    # OTC 合约端
    otc_delta = otc.get_otc_delta_amount()
    if otc_delta is None or otc_delta == 0.0:
        return None
    deltas.append(otc_delta)

    # 对冲端
    for hedge in hedge_list:
        if hedge.get_tool_type() == "onsite_option":
            # 场内期权优先从 iFinD API 获取实时 Delta，失败则回落本地计算
            hedge_delta = get_onsite_option_greeks(hedge.get_tool_code(), "delta")
            if hedge_delta is None:
                hedge_delta = hedge.get_hedge_delta_amount()
        else:
            hedge_delta = hedge.get_hedge_delta_amount()

        if hedge_delta is None or hedge_delta == 0.0:
            return None
        deltas.append(hedge_delta)

    return deltas


def is_effective_hedge(
    otc: OtcContract, hedge_list: List[HedgeTrade], price_type: str = "close"
) -> List:
    """
    判断场外合约与对冲工具组合是否构成"有效对冲"

    【监管依据】《证券公司风险控制指标计算标准规定》：
      符合以下条件的可认为已对冲风险：
        (1) 投资组合中的标的一致，或相关标的过去一年价格相关系数不低于 95%
        (2) 投资组合中相关投资为对冲目的而持有（本模型默认满足）
        (3) 投资组合中的多头 Delta 绝对值与空头 Delta 绝对值的比例
            处于 80%-125% 之间

    【监管效果】达成有效对冲后，市场风险资本准备计提比例从 30%/100% 降至 5%

    Args:
        otc: 场外合约对象
        hedge_list: 对冲工具列表
        price_type: 标的价格类型

    Returns:
        [bool, str]: [是否达成有效对冲, 失败原因（成功时为 None）]
    """
    # ====== 条件1：标的一致 或 相关性 ≥ 95% ======
    otc_code = otc.get_otc_underlying_code()
    if otc_code is None:
        return [False, "未填写场外合约标的代码，不满足有效对冲条件"]

    hedge_codes = [
        h.get_tool_underlying_code()
        for h in hedge_list
        if h.get_tool_underlying_code() is not None
    ]
    if not hedge_codes:
        return [False, "未填写对冲工具标的代码，不满足有效对冲条件"]

    # 子条件1.1：任一工具的标的代码与场外合约相同 → 标的一致
    underlying_is_same = any(otc_code == hc for hc in hedge_codes)

    # 子条件1.2：标的不同时，检查过去一年价格相关性 ≥ 95%
    if not underlying_is_same:
        otc_price = get_underlying_price_series(otc_code, price_type)
        if not otc_price.get(otc_code, []):
            return [False, f"获取产品标的 {otc_code} 价格数据失败"]

        for hc in hedge_codes:
            h_price = get_underlying_price_series(hc, price_type)
            if not h_price.get(hc, []):
                return [False, f"获取对冲工具标的 {hc} 价格数据失败"]

            corr = calculate_correlation_between_price_series(
                otc_code, otc_price, hc, h_price
            )
            if np.isnan(corr) or corr < 0.95:
                return [False, f"标的 {otc_code} 与 {hc} 相关性 {corr:.2%}，未达 95%"]

    # ====== 条件3：多头 Delta |绝对值| : 空头 Delta |绝对值| ∈ [80%, 125%] ======
    deltas = _collect_deltas(otc, hedge_list)
    if deltas is None:
        return [False, "Delta 敞口数据缺失，不满足有效对冲条件"]

    # 按数学符号分组：正 delta = 多头，负 delta = 空头
    long_delta_sum = sum(d for d in deltas if d > 0)
    short_delta_sum = sum(abs(d) for d in deltas if d < 0)

    if long_delta_sum == 0 or short_delta_sum == 0:
        return [False, "多头 Delta 或空头 Delta 为零，不满足有效对冲条件"]

    ratio = min(long_delta_sum, short_delta_sum) / max(long_delta_sum, short_delta_sum)
    if ratio < 0.80:
        return [False, f"多头/空头 Delta 比例 {ratio:.1%}，不在 80%-125% 之间"]

    return [True, None]
