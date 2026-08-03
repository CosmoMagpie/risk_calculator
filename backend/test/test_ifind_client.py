"""iFinD适配层与有效对冲判定的离线测试。

本文件不得写入真实账号密码，也不得在测试中登录第三方服务。线上连通性应由
用户在前端显式登录后单独验证；单元测试只校验本地逻辑和Mock返回值。
"""

import math
from unittest.mock import patch

import numpy as np

from backend.models.client_contract import OtcContract
from backend.models.hedge_trade import HedgeTrade
from backend.calculators.hedge_validator import is_effective_hedge
from backend.services.ifind_client import (
    calculate_correlation_between_price_series,
    normalize_a_share_code,
)


PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def make_option(delta=0.5):
    return OtcContract(
        contract_type="call_option",
        direction="buy",
        notional=1000,
        underlying_type="index_component",
        underlying_code="000300.SH",
        option_type="call_option",
        option_delta=delta,
        total_premium_amount=50,
    )


def test_code_normalization():
    print("\n=== 代码标准化 ===")
    check("Shanghai index suffix", normalize_a_share_code("000300") == "000300.SH")
    check("Shenzhen stock suffix", normalize_a_share_code("000001") == "000001.SZ")
    check("already normalized", normalize_a_share_code("510050.SH") == "510050.SH")
    check("blank remains blank/None", not normalize_a_share_code(""))


def test_correlation_helper():
    print("\n=== 相关性计算 ===")
    a = {"000300.SH": [1.0, 2.0, 3.0, 4.0]}
    b = {"510300.SH": [2.0, 4.0, 6.0, 8.0]}
    corr = calculate_correlation_between_price_series(
        "000300.SH", a, "510300.SH", b
    )
    check("perfect correlation", math.isclose(corr, 1.0))


def test_same_underlying_and_delta():
    print("\n=== 同标的与Delta比例 ===")
    otc = make_option(delta=0.5)  # +500
    hedge = HedgeTrade(
        tool_type="futures",
        direction="short",
        notional=500,
        future_delta=1.0,
        underlying_code="000300.SH",
    )
    result = is_effective_hedge(otc, [hedge])
    check("same underlying 100% delta hedge", result[0] is True, str(result))

    too_small = HedgeTrade(
        tool_type="futures",
        direction="short",
        notional=300,
        future_delta=1.0,
        underlying_code="000300.SH",
    )
    result_small = is_effective_hedge(otc, [too_small])
    check("delta below 80% rejected", result_small[0] is False, str(result_small))


def test_every_hedge_code_is_checked():
    print("\n=== 混合标的逐项检查 ===")
    otc = make_option(delta=1.0)  # +1000
    same = HedgeTrade(
        tool_type="futures", direction="short", notional=500,
        future_delta=1.0, underlying_code="000300.SH",
    )
    unrelated = HedgeTrade(
        tool_type="futures", direction="short", notional=500,
        future_delta=1.0, underlying_code="000001.SZ",
    )

    def fake_prices(code, _price_type):
        return {code: [1.0, 2.0, 3.0, 4.0]}

    with patch(
        "backend.calculators.hedge_validator.get_underlying_price_series",
        side_effect=fake_prices,
    ), patch(
        "backend.calculators.hedge_validator.calculate_correlation_between_price_series",
        return_value=0.50,
    ) as corr_mock:
        result = is_effective_hedge(otc, [same, unrelated])

    check("unrelated hedge is not skipped because another code matches", result[0] is False)
    check("correlation called for different code", corr_mock.call_count == 1)


def test_nan_correlation_message():
    print("\n=== 无法计算相关性 ===")
    otc = make_option(delta=0.5)
    hedge = HedgeTrade(
        tool_type="futures", direction="short", notional=500,
        underlying_code="000001.SZ",
    )

    def fake_prices(code, _price_type):
        return {code: [1.0, 1.0, 1.0]}

    with patch(
        "backend.calculators.hedge_validator.get_underlying_price_series",
        side_effect=fake_prices,
    ), patch(
        "backend.calculators.hedge_validator.calculate_correlation_between_price_series",
        return_value=np.nan,
    ):
        result = is_effective_hedge(otc, [hedge])
    check("NaN correlation rejected without misleading percentage", result[0] is False)
    check("NaN reason is readable", "无法计算" in result[1])


def test_partial_missing_hedge_code():
    print("\n=== 部分对冲工具缺少标的代码 ===")
    otc = make_option(delta=0.5)
    same = HedgeTrade(
        tool_type="futures", direction="short", notional=250,
        future_delta=1.0, underlying_code="000300.SH",
    )
    missing = HedgeTrade(
        tool_type="futures", direction="short", notional=250,
        future_delta=1.0, underlying_code=None,
    )
    result = is_effective_hedge(otc, [same, missing])
    check("partial missing hedge code rejected", result[0] is False)
    check("missing hedge reason identifies item", "#2" in result[1])


if __name__ == "__main__":
    print("=" * 60)
    print("Offline iFinD / Hedge Validation Tests")
    print("=" * 60)
    test_code_normalization()
    test_correlation_helper()
    test_same_underlying_and_delta()
    test_every_hedge_code_is_checked()
    test_nan_correlation_message()
    test_partial_missing_hedge_code()
    print("\n" + "=" * 60)
    print(f"Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)
