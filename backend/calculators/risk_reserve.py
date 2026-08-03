# ============================================================
# backend/calculators/risk_reserve.py - 风险资本准备计算
# ============================================================

from typing import List

from ..models.client_contract import OtcContract
from ..models.hedge_trade import HedgeTrade
from ..config import DEFAULT_CONFIG
from .ratios import RATES


# ============================================================
# 辅助函数
# ============================================================

def estimate_otc_option_stress_loss(
    spot_price: float,
    strike_price: float,
    contract_multiplier: float,
    contract_size: float,
    option_type: str,
) -> float:
    """
    根据标的价格、行权价、合约乘数与合约规模，估算卖出场外期权的 ±20% 压力测试最大损失。

    【计算逻辑】
      - 看涨期权（call）：标的价格上涨 20% 时，每单位亏损 = max(1.2×spot - strike, 0)
      - 看跌期权（put）：标的价格下跌 20% 时，每单位亏损 = max(strike - 0.8×spot, 0)
      - 总亏损（元） = 每单位亏损 × 合约乘数 × 合约规模
      - 返回结果已转换为万元

    Args:
        spot_price: 标的当前价格（元）
        strike_price: 期权行权价（元）
        contract_multiplier: 合约乘数（元/点）
        contract_size: 合约规模/份数（份）
        option_type: "call_option" 或 "put_option"

    Returns:
        float: 压力测试最大损失（万元）
    """
    pressure_lower = spot_price * 0.80
    pressure_upper = spot_price * 1.20

    if option_type in ("call_option", "call"):
        unit_loss = max(pressure_upper - strike_price, 0.0)
    else:
        unit_loss = max(strike_price - pressure_lower, 0.0)

    total_loss_yuan = unit_loss * contract_multiplier * contract_size
    return total_loss_yuan / 10000.0


def _get_option_premium(otc: OtcContract) -> float:
    """获取场外期权的权利金绝对值 P（万元）"""
    return abs(otc.get_otc_cash_inflow())


def _get_short_investment_scale(notional: float, stress_loss: float = 0.0) -> float:
    """
    卖出期权投资规模 S_short = max(5 × L_stress, N × 0.5%)
    适用：场外卖出期权 / 浮动收益凭证内嵌期权
    """
    return max(5 * stress_loss, notional * 0.005)


def _get_client_investment_scale(otc: OtcContract) -> float:
    """
    获取场外合约客户端的投资规模 |S_client|
      买入期权: S = P（权利金）
      卖出期权: S = S_short
      收益互换: S = N × 10%
      收益凭证(浮): S = S_short; (固): S = 0
    """
    ct = otc.contract_type

    if ct in ("call_option", "put_option"):
        if otc.direction == "buy":
            return _get_option_premium(otc)
        else:
            loss = otc.stress_loss or 0.0
            return _get_short_investment_scale(otc.notional, loss)

    elif ct == "equity_swap":
        return otc.notional * 0.10

    elif ct == "income_certificate":
        if otc.has_embedded_option:
            embedded_notional = otc.embedded_option_notional or otc.notional
            return _get_short_investment_scale(embedded_notional, otc.stress_loss or 0.0)
        return 0.0

    return 0.0


def _get_hedge_investment_scale(hedge: HedgeTrade, client_ct: str = "equity_swap") -> float:
    """
    获取单个对冲工具的投资规模 |S_hedge|
      现货/ETF: 市值 = notional
      期货: 名义价值 × 15%
      场外背对背: 期权/收益凭证类 N × 0.5%（无 stress_loss 取地板值）；
                  互换类 N × 10%
      场内期权: 权利金（默认名义价值 × 2%）
      私募基金: 申购金额

    client_ct 用于区分场外背对背对冲的结构（期权平盘 vs 互换），
    与 leverage.py 中 _calc_hedge_off_balance 的口径保持一致。
    """
    if hedge.tool_type in ("etf", "stock"):
        return hedge.notional
    elif hedge.tool_type == "futures":
        return hedge.notional * 0.15
    elif hedge.tool_type == "otc_hedge":
        if hedge.otc_hedge_contract_type == "option":
            if hedge.direction == "short":
                return _get_short_investment_scale(
                    hedge.notional, hedge.otc_stress_loss or 0.0
                )
            return abs(hedge.otc_payment or 0.0)
        return hedge.notional * 0.10
    elif hedge.tool_type == "onsite_option":
        if hedge.direction == "short":
            return abs(hedge.option_delta or 0.0) * hedge.notional * 0.15
        if hedge.option_premium is not None:
            return abs(hedge.option_premium)
        return hedge.notional * DEFAULT_CONFIG["trade"]["onsite_option_premium_rate"]
    elif hedge.tool_type == "private_fund":
        return hedge.subscription_amount or 0.0
    return 0.0


def _is_non_full_margin_swap(otc: OtcContract) -> bool:
    """条件A：收益互换是否为非全额保证金（M < N）"""
    if otc.contract_type != "equity_swap":
        return False
    if otc.margin_amount is not None:
        return otc.margin_amount < otc.notional
    if otc.margin_rate is not None:
        return otc.margin_rate < 100.0
    return True  # 默认10%保证金，必然非全额


def _is_individual_stock(otc: OtcContract) -> bool:
    """条件B：标的是否为境内个股（非指数成分股）"""
    market = (otc.underlying_market or "CN").upper()
    if market not in ("CN", "CHINA", "A_SHARE"):
        return False
    if otc.underlying_instrument is not None:
        return otc.underlying_instrument == "stock"
    return otc.underlying_type not in ("index_component", "broad_based_etf", "index")


def _calc_hedge_market_risk(hedge_list: List[HedgeTrade], client_ct: str = "equity_swap") -> float:
    """
    未达成有效对冲时，单独计算各对冲工具自身的市场风险资本准备（万元，不含 k_class）

    监管逻辑：对冲端头寸若不满足有效对冲条件，应作为独立自营头寸按其对应类别计提。
      - 股票现货：按股票属性适用8%/25%/50%/80%（公司政策不允许其作为对冲）
      - ETF：作为权益类基金，指数基金5%，其他权益类基金10%
      - 股指期货：投资规模 = 名义价值 × 15%，市场风险准备 = 投资规模 × 30%
      - 卖出场内期权：投资规模 = Delta金额 × 15%，市场风险准备 = 投资规模 × 30%
      - 买入场内期权：投资规模 = 权利金，市场风险准备 = 权利金 × 100%
      - 场外背对背：期权/收益凭证类按 N×0.5%×30%，互换类按 N×10%×30%
      - 私募基金：归入集合及信托等产品，暂按 25% 计提（可穿透时替换为底层资产口径）
    """
    total = 0.0
    for h in hedge_list:
        tt = h.tool_type

        if tt == "stock":
            st = h.underlying_type or h.stock_type or "general_stock"
            rate = RATES.get(st, 0.25)
            total += h.notional * rate

        elif tt == "etf":
            rate = RATES["equity_index_fund"] if h.is_broad_based_etf else RATES["other_equity_fund"]
            total += h.notional * rate

        elif tt == "futures":
            # 股指期货投资规模 = 名义价值 × 15%；权益类衍生品计提 30%
            total += h.notional * 0.15 * RATES["stock_index_future"]

        elif tt == "onsite_option":
            if h.direction == "short":
                s_short = abs(h.option_delta or 0.5) * h.notional * 0.15
                total += s_short * RATES["equity_short_option"]
            else:
                premium = h.option_premium if h.option_premium is not None else h.notional * DEFAULT_CONFIG["trade"]["onsite_option_premium_rate"]
                total += premium * RATES["equity_long_option"]

        elif tt == "otc_hedge":
            if h.otc_hedge_contract_type == "option":
                if h.direction == "short":
                    scale = _get_short_investment_scale(
                        h.notional, h.otc_stress_loss or 0.0
                    )
                    total += scale * RATES["equity_short_option"]
                else:
                    total += abs(h.otc_payment or 0.0) * RATES["equity_long_option"]
            else:
                total += h.notional * 0.10 * RATES["equity_swap"]

        elif tt == "private_fund":
            # 一对多归入集合及信托等产品25%；一对一归入单一产品50%，
            # 可穿透时对单一产品执行“单一或穿透孰严”。
            amount = h.subscription_amount if h.subscription_amount is not None else 0.0
            base_rate = 0.25 if h.fund_structure == "collective_product" else 0.50
            if h.fund_structure == "single_product" and h.fund_lookthrough_risk_rate is not None:
                base_rate = max(base_rate, h.fund_lookthrough_risk_rate)
            total += amount * base_rate

    return total


# ============================================================
# 各产品市场风险资本准备
# ============================================================

def _calc_option_market_risk(
    otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool
) -> float:
    """
    场外期权的市场风险资本准备（万元，不含 k_class）
    """
    s_client = _get_client_investment_scale(otc)
    s_hedge_total = sum(_get_hedge_investment_scale(h, otc.contract_type) for h in hedge_list)

    if is_hedge_effective and hedge_list:
        # 达成有效对冲：(|S_client| + |S_hedge|) × 5%
        return (s_client + s_hedge_total) * 0.05

    # 单边未对冲：客户端 + 对冲端各自独立计提
    if otc.direction == "buy":
        client_risk = s_client * RATES["equity_long_option"]   # 买入期权 100%
    else:
        client_risk = s_client * RATES["equity_short_option"]   # 卖出期权 30%
    return client_risk + _calc_hedge_market_risk(hedge_list, otc.contract_type)


def _calc_swap_market_risk(
    otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool
) -> float:
    """
    收益互换的市场风险资本准备（万元，不含 k_class）

    惩罚条件：同时满足 条件A(非全额保证金) + 条件B(个股标的) → 加倍
    """
    s_client = _get_client_investment_scale(otc)  # N × 10%
    s_hedge_total = sum(_get_hedge_investment_scale(h, otc.contract_type) for h in hedge_list)
    is_penalty = _is_non_full_margin_swap(otc) and _is_individual_stock(otc)

    if is_hedge_effective and hedge_list:
        reserve = (s_client + s_hedge_total) * 0.05
    else:
        # 未对冲：客户端 + 对冲端各自独立计提；仅客户端部分受惩罚倍数影响
        client_risk = s_client * RATES["equity_swap"]   # N × 10% × 30% = N × 3%
        if is_penalty:
            client_risk *= 2.0
        reserve = client_risk + _calc_hedge_market_risk(hedge_list, otc.contract_type)
        return reserve

    if is_penalty:
        reserve *= 2.0

    return reserve


def _calc_income_cert_market_risk(
    otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool
) -> float:
    """
    收益凭证的市场风险资本准备（万元，不含 k_class）
    仅浮动收益凭证（含内嵌衍生品）才计提
    """
    if not otc.has_embedded_option:
        # 固定收益凭证本身无权益衍生品市场风险；若仍配置交易端头寸，
        # 这些头寸不能随主产品一起归零，须作为独立自营头寸计提。
        return _calc_hedge_market_risk(hedge_list, otc.contract_type)

    s_client = _get_client_investment_scale(otc)  # S_short
    s_hedge_total = sum(_get_hedge_investment_scale(h, otc.contract_type) for h in hedge_list)

    if is_hedge_effective and hedge_list:
        return (s_client + s_hedge_total) * 0.05

    # 未对冲：内嵌期权 + 对冲端各自独立计提
    return s_client * RATES["equity_short_option"] + _calc_hedge_market_risk(hedge_list, otc.contract_type)  # S_short × 30%


# ============================================================
# 信用风险资本准备（仅收益互换）
# ============================================================

def _calc_credit_risk(otc: OtcContract) -> float:
    """
    信用风险资本准备（万元，不含 k_class）

    仅对非全额保证金的收益互换计提：N × 5%
    对冲不减免信用风险
    """
    if otc.contract_type != "equity_swap":
        return 0.0
    if not _is_non_full_margin_swap(otc):
        return 0.0
    return otc.notional * 0.05


# ============================================================
# 合计入口
# ============================================================

def calc_total_risk_reserve(
    otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool
) -> float:
    """
    计算各项风险资本准备合计（万元，含 k_class 分类评价系数）

    【组成】市场风险 + 信用风险（操作风险/特定风险待实现）

    三种产品的计提规则：
      1. 场外期权
         - 买入: P × 100% × k_class
         - 卖出: S_short × 30% × k_class
         - 对冲: (|S_client| + |S_hedge|) × 5% × k_class
      2. 收益互换
         - 市场风险: N×3%×k_class（惩罚情况×2）
         - 信用风险: N×5%×k_class（非全额保证金，对冲不减免）
         - 对冲: (|S_swap|+|S_hedge|)×5%×k_class（惩罚仍×2）
      3. 收益凭证
         - 固定型: 0
         - 浮动型: S_short×30%×k_class / 对冲: (|S_short|+|S_hedge|)×5%×k_class

    【分类评价系数 k_class】
      连续三年A类且AA级以上=0.4，连续三年A类=0.6，A类=0.8，
      B类=0.9，C类=1.0，D类=2.0。
    """
    ct = otc.contract_type
    k_class = DEFAULT_CONFIG["firm"]["classification_factor"]

    if ct in ("call_option", "put_option"):
        market_risk = _calc_option_market_risk(otc, hedge_list, is_hedge_effective)
        credit_risk = 0.0

    elif ct == "equity_swap":
        market_risk = _calc_swap_market_risk(otc, hedge_list, is_hedge_effective)
        credit_risk = _calc_credit_risk(otc)

    elif ct == "income_certificate":
        market_risk = _calc_income_cert_market_risk(otc, hedge_list, is_hedge_effective)
        credit_risk = 0.0

    else:
        return 0.0

    total = (market_risk + credit_risk) * k_class
    return total


def calc_self_operated_equity_scale(
    otc: OtcContract, hedge_list: List[HedgeTrade]
) -> float:
    """附件6“自营权益类证券及其衍生品”新增投资规模（万元）。"""
    total = _get_client_investment_scale(otc)
    for hedge in hedge_list:
        # 当前private_fund按集合/单一产品填列，不在缺少穿透分类时并入权益类规模。
        if hedge.tool_type != "private_fund":
            total += _get_hedge_investment_scale(hedge, otc.contract_type)
    return total
