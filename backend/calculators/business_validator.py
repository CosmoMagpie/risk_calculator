"""公司业务范围与对冲工具约束。

这些约束与监管“有效对冲”判定分开：一笔交易可能在Delta/相关性上满足
监管条件，但仍不在公司的牌照或内部可用工具范围内。
"""

from typing import Dict, List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade


DOMESTIC_MARKETS = {None, "", "CN", "CHINA", "A_SHARE"}


def validate_business_constraints(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> Dict[str, object]:
    """返回公司业务范围校验结果，不以猜测替代牌照事实。"""
    errors: List[str] = []
    warnings: List[str] = []

    market = (otc.underlying_market or "CN").upper()
    if market not in DOMESTIC_MARKETS:
        errors.append("公司无海外业务凭证，客户端标的市场不得为境外市场")

    for index, hedge in enumerate(hedge_list, 1):
        hedge_market = (hedge.underlying_market or "CN").upper()
        if hedge_market not in DOMESTIC_MARKETS:
            errors.append(f"对冲工具#{index}为境外市场工具，不在公司业务范围内")

        # 用户明确的公司约束：不得用个股现货对冲股权衍生品。
        if hedge.tool_type == "stock":
            errors.append(f"对冲工具#{index}为个股现货，公司当前不允许个股对冲")

        if hedge.tool_type == "etf" and not hedge.is_broad_based_etf:
            warnings.append(
                f"对冲工具#{index}不是宽基股票指数ETF：无50% HQLA资格，"
                "市场风险资本准备按其他权益类基金10%计提"
            )

        if hedge.tool_type == "private_fund" and hedge.fund_structure not in (
            "collective_product",
            "single_product",
        ):
            errors.append(
                f"对冲工具#{index}私募基金/SPV未区分一对多集合产品或一对一单一产品"
            )

        if hedge.tool_type == "otc_hedge" and hedge.otc_hedge_contract_type not in (
            "equity_swap",
            "option",
        ):
            errors.append(f"对冲工具#{index}场外背对背未填写平盘合约类型")

    if otc.contract_type == "income_certificate" and otc.has_embedded_option:
        if otc.embedded_option_notional is None or otc.embedded_option_notional <= 0:
            errors.append("浮动收益凭证未填写内嵌期权实际名义金额")
        if otc.stress_loss is None:
            errors.append("浮动收益凭证未填写内嵌期权±20%压力情景最大损失")

    return {"is_compliant": not errors, "errors": errors, "warnings": warnings}
