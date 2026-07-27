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


def is_effective_hedge(otc: OtcContract, hedge_list: List[HedgeTrade], price_type: str = "close") -> List[bool, Optional[str]]:
    """
    判断场外合约与对冲工具组合是否构成"有效对冲"

    【监管背景】根据《证券公司风险控制指标计算标准规定》，有效对冲的头寸
               在计算市场风险资本准备时可以享受95%的减免（只计提5%）

    Args:
        otc: 场外合约对象
        hedge_list: 对冲工具列表
        price_type: 标的价格类型，如 'close', 'open', 'high', 'low', 'pre_close'
    Returns:
        [bool, str]: [是否构成有效对冲, 失败原因（成功时为None）]

    【两个条件必须同时满足】
      条件1：标的相同 OR 价格相关性 ≥ 95%
      条件2：多头Delta的绝对值与空头Delta的绝对值比例在 80%-125% 之间
            （即对冲覆盖率在80%以上，且不超过125%，避免过度对冲）
    """
    # ========== 条件1.1：判断标的物是否相同 ==========
    otc_underlying_code = otc.get_otc_underlying_code()
    if otc_underlying_code is None:
        return [False, "未填写场外合约标的代码，默认不满足有效对冲条件"]
    hedge_tool_underlying_codes = [h.get_tool_underlying_code() for h in hedge_list if h.get_tool_underlying_code() is not None]
    if not hedge_tool_underlying_codes:
        return [False, "未填写对冲工具标的代码，默认不满足有效对冲条件"]

    # 子条件1.1：任一工具的标的代码与场外合约相同即为"同一标的"
    underlying_is_same = any(otc_underlying_code == h_code for h_code in hedge_tool_underlying_codes)

    # ========== 条件1.2：判断标的物过去一年价格相关性 ≥ 95% ==========
    correlation_met = True
    if not underlying_is_same:
        otc_price_data = get_underlying_price_series(otc_underlying_code, price_type) # 产品底层过去一年价格
        if not otc_price_data.get(otc_underlying_code, []):
            return [False, f"获取{otc.get_otc_contract_type()}产品标的：{otc.get_otc_underlying_code()}价格数据失败"]
        for hedge_tool_underlying_code in hedge_tool_underlying_codes:
            hedge_price_data = get_underlying_price_series(hedge_tool_underlying_code, price_type) # 获取对冲工具底层过去一年的价格
            if not hedge_price_data.get(hedge_tool_underlying_code, []):
                return [False, f"获取对冲工具标的: {hedge_tool_underlying_code}价格数据失败"]
            # 计算相关系数
            corr = calculate_correlation_between_price_series(otc_underlying_code, otc_price_data, hedge_tool_underlying_code, hedge_price_data)
            if np.isnan(corr) or corr < 0.95:  # 阈值：95%相关性
                correlation_met = False
                break
        condition1 = underlying_is_same or correlation_met
        if not condition1:
            return [False, "标的代码不匹配或标的物过去一年价格相关性未达到95%"]

    # ========== 条件2：计算Delta值比例 ==========
    # 将场外合约与所有对冲工具的(direction, delta_amount)汇总到同一列表
    all_positions = []
    otc_delta_amount = otc.get_otc_delta_amount()
    otc_direction = otc.get_otc_contract_direction()
    if otc_delta_amount is not None:
        all_positions.append((otc_direction, otc_delta_amount))
    else:
        return [False, "未填写场外合约Delta金额，默认不满足有效对冲条件"]
    for hedge in hedge_list:
        hedge_direction = hedge.get_tool_direction()
        # 场内期权优先从 iFinD API 获取实时 Delta
        if hedge.get_tool_type() == "onsite_option":
            hedge_delta = get_onsite_option_greeks(hedge.get_tool_code(), "delta")
        else:
            hedge_delta = hedge.get_hedge_delta_amount()
        if hedge_delta is not None:
            all_positions.append((hedge_direction, hedge_delta))
        else:
            return [False, "未填写对冲工具Delta金额，或未成功获取相应期权delta值，请检查，否则默认不满足有效对冲条件"]
    if not all_positions:
        return [False, "未找到有效的Delta头寸数据"]

    # 分别统计多头和空头的Delta绝对值总和
    long_delta = sum(abs(delta) for dir_, delta in all_positions if dir_ == "long")
    short_delta = sum(abs(delta) for dir_, delta in all_positions if dir_ == "short")
    if long_delta == 0 or short_delta == 0:
        return [False, "多头Delta绝对值或空头Delta绝对值为0，默认不满足有效对冲条件"]
    ratio = min(long_delta, short_delta) / max(long_delta, short_delta)  # 始终 ≤ 1
    if ratio < 0.80:  # 对冲覆盖不足80%
        return [False, "多头Delta绝对值与空头Delta绝对值比例不在80%-125%之间"]

    return [True, None]
