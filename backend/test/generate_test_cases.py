"""生成与当前监管口径一致的离线示例 ``test_cases.md``。

生成过程不登录iFinD、不包含账号密码；有效对冲示例只使用同标的代码，避免外部调用。
"""

from datetime import date
from pathlib import Path

from backend.analyzer import analyze_contract
from backend.config import DEFAULT_CONFIG
from backend.models.client_contract import OtcContract
from backend.models.hedge_trade import HedgeTrade


def build_cases():
    return [
        (
            "TC01 卖出场外看涨期权（无对冲）",
            OtcContract(
                contract_type="call_option", direction="short", notional=10_000,
                underlying_type="index_component", underlying_instrument="index",
                underlying_market="CN", underlying_code="000300.SH",
                option_type="call_option", option_delta=-0.5,
                premium_rate=5.0, stress_loss=200, term_days=180,
                expected_yield=0.08,
            ),
            [],
        ),
        (
            "TC02 卖出场外看涨期权（宽基ETF有效对冲）",
            OtcContract(
                contract_type="call_option", direction="short", notional=10_000,
                underlying_type="index_component", underlying_instrument="index",
                underlying_market="CN", underlying_code="000300.SH",
                option_type="call_option", option_delta=-0.5,
                premium_rate=5.0, stress_loss=200, term_days=180,
                expected_yield=0.08,
            ),
            [HedgeTrade(
                tool_type="etf", direction="long", notional=5_000,
                underlying_type="index_component", underlying_market="CN",
                underlying_code="000300.SH", is_broad_based_etf=True,
            )],
        ),
        (
            "TC03 境内个股收益互换（非全额保证金、期货对冲未认定有效）",
            OtcContract(
                contract_type="equity_swap", direction="short", notional=20_000,
                underlying_type="general_stock", underlying_instrument="stock",
                underlying_market="CN", underlying_code="600519.SH",
                margin_rate=10.0, equity_swap_delta=-1.0, term_days=365,
                expected_yield=0.06,
            ),
            [HedgeTrade(
                tool_type="futures", direction="long", notional=18_000,
                futures_margin=2_160, future_delta=1.0,
                underlying_type="index_component", underlying_market="CN",
                underlying_code="",  # 不用外部行情时无法认定监管有效对冲
            )],
        ),
        (
            "TC04 指数收益互换（宽基ETF同标的有效对冲）",
            OtcContract(
                contract_type="equity_swap", direction="long", notional=10_000,
                underlying_type="index_component", underlying_instrument="index",
                underlying_market="CN", underlying_code="000300.SH",
                margin_rate=10.0, equity_swap_delta=1.0, term_days=365,
                expected_yield=0.06,
            ),
            [HedgeTrade(
                tool_type="etf", direction="short", notional=10_000,
                underlying_type="index_component", underlying_market="CN",
                underlying_code="000300.SH", is_broad_based_etf=True,
            )],
        ),
        (
            "TC05 固定收益凭证（无内嵌衍生品）",
            OtcContract(
                contract_type="income_certificate", direction="issue",
                notional=50_000, funds_raised=50_000, underlying_type="index_component",
                underlying_market="CN", has_embedded_option=False,
                term_days=400, expected_yield=0.04,
            ),
            [],
        ),
        (
            "TC06 浮动收益凭证（内嵌期权+期货有效对冲）",
            OtcContract(
                contract_type="income_certificate", direction="issue",
                notional=50_000, funds_raised=50_000,
                underlying_type="index_component", underlying_instrument="index",
                underlying_market="CN", underlying_code="000300.SH",
                has_embedded_option=True, embedded_option_notional=50_000,
                option_delta=-0.5, stress_loss=300, term_days=270,
                expected_yield=0.05,
            ),
            [HedgeTrade(
                tool_type="futures", direction="long", notional=25_000,
                futures_margin=3_000, future_delta=1.0,
                underlying_type="index_component", underlying_market="CN",
                underlying_code="000300.SH",
            )],
        ),
        (
            "TC07 场外期权+卖出场内期权（验证15%不重复折算）",
            OtcContract(
                contract_type="call_option", direction="buy", notional=1_000,
                underlying_type="index_component", underlying_instrument="index",
                underlying_market="CN", underlying_code="000300.SH",
                option_type="call_option", option_delta=0.5,
                total_premium_amount=30, term_days=90, expected_yield=0.08,
            ),
            [HedgeTrade(
                tool_type="onsite_option", direction="short", notional=1_000,
                underlying_type="index_component", underlying_market="CN",
                underlying_code="000300.SH", option_type="call_option",
                option_delta=-0.5, option_premium=20, option_margin=150,
            )],
        ),
        (
            "TC08 收益互换+一对一SPV申购（未提供组合Delta）",
            OtcContract(
                contract_type="equity_swap", direction="short", notional=20_000,
                underlying_type="index_component", underlying_instrument="index",
                underlying_market="CN", underlying_code="000300.SH",
                margin_rate=25.0, equity_swap_delta=-1.0,
                term_days=365, expected_yield=0.06,
            ),
            [HedgeTrade(
                tool_type="private_fund", direction="long", notional=14_000,
                subscription_amount=14_000, fund_structure="single_product",
                asset_maturity_days=None, fund_delta=None,
                underlying_market="CN", underlying_code="000300.SH",
            )],
        ),
    ]


def fmt(value):
    if value is None:
        return "不适用"
    if isinstance(value, float):
        return f"{value:,.6f}"
    return str(value)


def generate_markdown(output_path: Path):
    lines = [
        "# 风控模型回归测试案例",
        "",
        f"> 生成日期：{date.today().isoformat()}；全程离线，不调用iFinD。",
        "",
        "## 公司基准与口径",
        "",
        f"- 风险资本准备分类系数：{DEFAULT_CONFIG['firm']['classification_factor']}",
        f"- 表内外资产分类系数：{DEFAULT_CONFIG['firm']['asset_adjustment_factor']}",
        f"- LCR毛流出/毛流入基数（元）：{DEFAULT_CONFIG['firm']['LCR_outflow_base']:,} / {DEFAULT_CONFIG['firm']['LCR_inflow_base']:,}",
        "- 场外卖出期权：风险资本/表内外资产用压力规模；LCR用名义×20%；NSFR用名义×12%。",
        "- 卖出场内期权：LCR和NSFR均以Delta金额×15%作为最终填列额，不再重复乘20%/12%。",
        "- 用于对冲权益互换的证券不计入HQLA；宽基ETF仍计入NSFR和市场风险资本准备。",
        "",
    ]

    for title, client, hedges in build_cases():
        result = analyze_contract(client, hedges)
        lines.extend([
            f"## {title}",
            "",
            "### 输入",
            "",
            f"- 客户端：`{client}`",
            f"- 对冲端：`{hedges}`",
            "",
            "### 输出",
            "",
            "| 指标 | 结果 |",
            "|---|---:|",
        ])
        for key in (
            "net_day1_cash", "new_risk_reserve", "market_credit_risk_reserve",
            "operational_risk_reserve", "hqla_change", "gross_outflow_change",
            "net_cof_change", "asf_change", "rsf_change", "assets_change",
            "net_capital_change", "equity_scale_change", "lcr_new", "nsfr_new",
            "leverage_new", "risk_coverage_new", "equity_scale_ratio_new",
            "expected_income", "roc", "ro_lcr", "ro_nsfr",
        ):
            lines.append(f"| `{key}` | {fmt(result[key])} |")
        lines.extend([
            "",
            f"- 监管有效对冲：`{result['is_effective_hedge']}`",
            f"- 公司业务范围：`{result['business_constraints']}`",
            "",
        ])

    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[2] / "test_cases.md"
    generate_markdown(output)
    print(f"Generated {output}")
