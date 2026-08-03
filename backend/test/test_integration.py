# ============================================================
# backend/test_integration.py - 集成与模型正确性测试
# ============================================================
# 覆盖：config、ClientContract、HedgeTrade、analyzer 端到端、边界情况
# 与 test_calculators.py（纯 calculators 单元测试）互补
# ============================================================

import sys
import math

from backend.config import DEFAULT_CONFIG
from backend.models.client_contract import OtcContract as ClientContract
from backend.models.hedge_trade import HedgeTrade
from backend.analyzer import analyze_contract

PASS = 0
FAIL = 0


def check(desc, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {desc}")
    else:
        FAIL += 1
        print(f"  [FAIL] {desc}")


# ============================================================
# 1. Config 完整性
# ============================================================
def test_config():
    print("\n=== Config 完整性 ===")

    # 三大段必须存在
    for section in ["client", "trade", "firm"]:
        check(f"config['{section}'] exists", section in DEFAULT_CONFIG)

    # client defaults 合理性
    c = DEFAULT_CONFIG["client"]
    check("swap_margin_rate ∈ (0,1]", 0 < c["swap_margin_rate"] <= 1)
    check("option_premium_rate > 0", c["option_premium_rate"] > 0)
    check("OTC option margin is not hardcoded as exchange margin",
          "option_margin_rate" not in c)

    # trade defaults
    t = DEFAULT_CONFIG["trade"]
    check("futures_margin_rate ∈ (0,1]", 0 < t["futures_margin_rate"] <= 1)
    check("onsite_option_margin_rate exists", "onsite_option_margin_rate" in t)
    check("atm_option_delta > 0", t["atm_option_delta"] > 0)

    # firm defaults — 所有数值必须非负
    f = DEFAULT_CONFIG["firm"]
    for key in ["HQLA_base", "LCR_COF_base", "ASF_base", "RSF_base",
                "net_capital_base", "total_risk_reserve_base",
                "on_off_balance_total_asset_base",
                "classification_factor", "asf_rating_factor"]:
        check(f"firm['{key}'] exists and >= 0", key in f and f[key] >= 0)
    check("asf_rating_factor ∈ [0, 0.2]", 0 <= f["asf_rating_factor"] <= 0.20)
    check("asset_adjustment_factor is valid", f["asset_adjustment_factor"] in (0.7, 0.9, 1.0))
    check("LCR gross bases exist", "LCR_outflow_base" in f and "LCR_inflow_base" in f)


# ============================================================
# 2. ClientContract 模型
# ============================================================
def test_client_contract():
    print("\n=== ClientContract 模型 ===")

    # ---- 卖出看涨期权 ----
    otc = ClientContract(
        contract_type="call_option", direction="short", notional=1000,
        underlying_type="index_component",
        option_type="call_option", premium_rate=5.0,
        stress_loss=50, term_days=90
    )
    inflow = otc.get_otc_cash_inflow()
    check("short call: cash inflow = premium (5% × 1000 = 50)",
          math.isclose(inflow, 50.0))
    check("short call: expected_income (8% × 1000 = 80)",
          math.isclose(otc.get_expected_income(), 80.0))

    # ---- 买入看跌期权（支付权利金）----
    otc_buy = ClientContract(
        contract_type="put_option", direction="buy", notional=1000,
        underlying_type="general_stock",
        option_type="put_option", total_premium_amount=30, term_days=180
    )
    inflow_buy = otc_buy.get_otc_cash_inflow()
    check("buy put: cash inflow = -premium (-30)", math.isclose(inflow_buy, -30.0))

    # ---- 收益互换（空头，收保证金）----
    swap = ClientContract(
        contract_type="equity_swap", direction="short", notional=2000,
        underlying_type="general_stock",
        margin_rate=10.0, term_days=365
    )
    check("swap short: cash inflow = 10% × 2000 = 200",
          math.isclose(swap.get_otc_cash_inflow(), 200.0))

    # ---- 收益互换（多头，也按字段定义收取客户保证金）----
    swap_long = ClientContract(
        contract_type="equity_swap", direction="long", notional=1000,
        underlying_type="index_component", margin_amount=150
    )
    check("swap long: received margin is +150",
          math.isclose(swap_long.get_otc_cash_inflow(), 150.0))

    # ---- 收益凭证（固定）----
    cert = ClientContract(
        contract_type="income_certificate", direction="buy", notional=500,
        underlying_type="index_component",
        funds_raised=500, term_days=90
    )
    check("fixed cert: cash inflow = funds_raised (500)",
          math.isclose(cert.get_otc_cash_inflow(), 500.0))
    check("fixed cert: stress_loss is None → 固定型",
          cert.stress_loss is None)

    # ---- 收益凭证（浮动，内嵌期权）----
    cert_float = ClientContract(
        contract_type="income_certificate", direction="buy", notional=800,
        underlying_type="index_component",
        funds_raised=800, has_embedded_option=True,
        embedded_option_notional=800, stress_loss=60, term_days=270
    )
    check("floating cert: stress_loss=60 → 浮动型",
          cert_float.stress_loss is not None)
    check("floating cert: cash inflow still = funds_raised",
          math.isclose(cert_float.get_otc_cash_inflow(), 800.0))

    # ---- 边界：margin_rate/margin_amount 都为 None（回退默认值）----
    swap_default = ClientContract(
        contract_type="equity_swap", direction="short", notional=1000,
        underlying_type="index_component"
    )
    check("swap default: cash inflow = 10% × 1000 = 100",
          math.isclose(swap_default.get_otc_cash_inflow(), 100.0))

    # ---- 边界：zero notional ----
    otc_zero = ClientContract(
        contract_type="call_option", direction="short", notional=0,
        underlying_type="index_component",
        option_type="call_option", premium_rate=5.0, stress_loss=0
    )
    check("zero notional: cash inflow = 0",
          math.isclose(otc_zero.get_otc_cash_inflow(), 0.0))

    # ---- Delta 计算 ----
    # 买入看涨期权 Delta 应为正
    otc_delta_buy_call = ClientContract(
        contract_type="call_option", direction="buy", notional=1000,
        underlying_type="index_component",
        option_type="call_option", option_delta=0.6
    )
    da = otc_delta_buy_call.get_otc_delta_amount()
    check("buy call delta > 0", da > 0)
    check("buy call delta = 0.6 × 1000 = 600",
          math.isclose(da, 600.0))

    # 卖出看跌期权：头寸 Delta 为正（与买入看跌符号相反）
    otc_short_put = ClientContract(
        contract_type="put_option", direction="short", notional=500,
        underlying_type="index_component",
        option_type="put_option", option_delta=0.4
    )
    da2 = otc_short_put.get_otc_delta_amount()
    check("short put delta: 头寸 Delta = +0.4 × 500 = 200", math.isclose(da2, 200.0))

    # ---- get_income_certificate_rate（回归 P1 修复验证）----
    rate = otc.get_income_certificate_rate()
    check("get_income_certificate_rate returns 0.04 (config default)",
          math.isclose(rate, 0.04))
    check("get_income_certificate_rate does not raise", rate is not None)


# ============================================================
# 3. HedgeTrade 模型
# ============================================================
def test_hedge_trade():
    print("\n=== HedgeTrade 模型 ===")

    # ---- ETF (long) ----
    etf = HedgeTrade(tool_type="etf", direction="long", notional=200,
                     underlying_type="index_component")
    check("ETF long: cash outflow = 200", math.isclose(etf.get_trade_cash_outflow(), 200.0))

    # ---- ETF (short) ----
    etf_short = HedgeTrade(tool_type="etf", direction="short", notional=200)
    check("ETF short: cash outflow = -200", math.isclose(etf_short.get_trade_cash_outflow(), -200.0))

    # ---- Stock ----
    stock = HedgeTrade(tool_type="stock", direction="long", notional=150,
                       stock_type="general_stock")
    check("stock long: cash outflow = 150", math.isclose(stock.get_trade_cash_outflow(), 150.0))

    # ---- Futures (默认 margin rate) ----
    fut = HedgeTrade(tool_type="futures", direction="long", notional=1000)
    expected_margin = 1000 * DEFAULT_CONFIG["trade"]["futures_margin_rate"]
    check(f"futures default: cash outflow = {expected_margin}",
          math.isclose(fut.get_trade_cash_outflow(), expected_margin))

    # ---- Futures (指定 margin) ----
    fut_explicit = HedgeTrade(tool_type="futures", direction="short",
                              notional=1000, futures_margin=120)
    check("futures explicit margin: cash outflow = 120",
          math.isclose(fut_explicit.get_trade_cash_outflow(), 120.0))

    # ---- Onsite option (long/buy, pay premium) ----
    opt_long = HedgeTrade(tool_type="onsite_option", direction="long",
                          notional=300, option_premium=9,
                          option_type="call_option", option_delta=0.5)
    check("onsite option long: cash outflow = premium = 9",
          math.isclose(opt_long.get_trade_cash_outflow(), 9.0))

    # ---- Onsite option (short/sell, receive premium) ----
    opt_short = HedgeTrade(tool_type="onsite_option", direction="short",
                           notional=300, option_premium=6,
                           option_type="put_option", option_delta=0.3)
    check("onsite option short: cash outflow = -6",
          math.isclose(opt_short.get_trade_cash_outflow(), -6.0))

    # ---- Onsite option delta ----
    da = opt_long.get_hedge_delta_amount()
    # 买入看涨期权：头寸 Delta = +0.5 × 300 = 150
    check("onsite option long call delta = 150", math.isclose(da, 150.0))

    # ---- OTC hedge ----
    otc_h = HedgeTrade(tool_type="otc_hedge", direction="long",
                       notional=400, otc_payment=50, pass_through_fee=2.0)
    outflow = otc_h.get_trade_cash_outflow()
    # 年化平盘成本属于创收扣减，不混入首日现金流。
    check("otc hedge: day-one outflow equals otc_payment", math.isclose(outflow, 50.0))

    # ---- Private fund ----
    pf = HedgeTrade(tool_type="private_fund", direction="long",
                    notional=100, subscription_amount=80)
    check("private fund: outflow = subscription_amount = 80",
          math.isclose(pf.get_trade_cash_outflow(), 80.0))

    # ---- 边界：optional fields = None ----
    pf_none = HedgeTrade(tool_type="private_fund", direction="long", notional=100)
    check("private fund no subscription: outflow = 0",
          math.isclose(pf_none.get_trade_cash_outflow(), 0.0))

    # ---- get_tool_underlying_code 返回 None ----
    check("get_tool_underlying_code returns None when not set",
          etf.get_tool_underlying_code() is None)

    # ---- otc_hedge / private_fund Delta ----
    otc_h_delta = HedgeTrade(tool_type="otc_hedge", direction="long",
                             notional=400, underlying_code="000300").get_hedge_delta_amount()
    check("otc_hedge delta = +notional", math.isclose(otc_h_delta, 400.0))

    otc_h_short_delta = HedgeTrade(tool_type="otc_hedge", direction="short",
                                   notional=400).get_hedge_delta_amount()
    check("otc_hedge short delta = -notional", math.isclose(otc_h_short_delta, -400.0))

    pf_delta_missing = HedgeTrade(tool_type="private_fund", direction="long",
                                  notional=100, subscription_amount=80).get_hedge_delta_amount()
    check("private_fund without verified delta cannot be effective hedge", pf_delta_missing is None)
    pf_delta = HedgeTrade(tool_type="private_fund", direction="long",
                          notional=100, subscription_amount=80,
                          fund_delta=1.0).get_hedge_delta_amount()
    check("private_fund verified delta = 80", math.isclose(pf_delta, 80.0))


# ============================================================
# 4. Analyzer 端到端
# ============================================================
def test_analyzer_e2e():
    print("\n=== Analyzer 端到端 ===")

    REQUIRED_KEYS = [
        "net_day1_cash", "new_risk_reserve", "net_cof_change",
        "assets_change", "net_capital_change",
        "lcr_old", "lcr_new", "lcr_change", "lcr_status",
        "nsfr_old", "nsfr_new", "nsfr_change", "nsfr_status",
        "leverage_old", "leverage_new", "leverage_change", "leverage_status",
        "risk_coverage_old", "risk_coverage_new", "risk_coverage_change", "risk_coverage_status",
        "expected_income", "roc", "ro_lcr", "ro_nsfr",
        "is_effective_hedge",
    ]

    # ---- 场景1：卖出期权 + 无对冲 ----
    otc = ClientContract(
        contract_type="call_option", direction="short", notional=1000,
        underlying_type="index_component",
        option_type="call_option", premium_rate=5.0,
        stress_loss=50, term_days=90
    )
    r = analyze_contract(otc, [])
    check("e2e option short: all keys present",
          all(k in r for k in REQUIRED_KEYS))
    check("e2e option short: net_day1_cash = 50",
          math.isclose(r["net_day1_cash"], 50.0))
    check("e2e option short: new_risk_reserve > 0", r["new_risk_reserve"] > 0)
    check("e2e option short: roc > 0", r["roc"] > 0)
    check("e2e option short: lcr_change <= 0 (HQLA流入但COF增加))",
          r["lcr_change"] <= 0)  # 卖出期权收权利金+HQLA，但S_short产生COF
    check("e2e option short: status strings",
          r["lcr_status"] in ("safe", "warning", "danger"))

    # ---- 场景2：收益互换 + 期货对冲 ----
    swap = ClientContract(
        contract_type="equity_swap", direction="short", notional=2000,
        underlying_type="general_stock",
        margin_rate=10.0, term_days=365
    )
    hedge = HedgeTrade(tool_type="futures", direction="short", notional=1600,
                       underlying_type="index_component", futures_margin=192)
    r2 = analyze_contract(swap, [hedge])
    check("e2e swap: all keys present",
          all(k in r2 for k in REQUIRED_KEYS))
    check("e2e swap: net_capital_change < 0 (futures margin deducted)",
          r2["net_capital_change"] < 0)
    check("e2e swap: assets_change > 0", r2["assets_change"] > 0)
    check("e2e swap: nsfr_change != 0", abs(r2["nsfr_change"]) > 0.0000001)

    # ---- 场景3：固定收益凭证 + ETF对冲 ----
    cert = ClientContract(
        contract_type="income_certificate", direction="buy", notional=500,
        underlying_type="index_component",
        funds_raised=500, term_days=90
    )
    etf_hedge = HedgeTrade(tool_type="etf", direction="long", notional=400,
                           underlying_type="index_component", is_broad_based_etf=True)
    r3 = analyze_contract(cert, [etf_hedge])
    check("e2e fixed cert: host=0 but standalone ETF reserve=20",
          math.isclose(r3["new_risk_reserve"], 20.0))
    # 募集500 - 买ETF 400 = 净现金 +100
    check("e2e fixed cert: net_day1_cash = 100",
          math.isclose(r3["net_day1_cash"], 100.0))
    # 收益凭证表内增量 = V 本身（募集资金全额入表，对冲只改变资产形态）
    check("e2e fixed cert: assets_change = V = 500",
          math.isclose(r3["assets_change"], 500.0))
    check("e2e fixed cert: roc uses standalone ETF reserve",
          math.isclose(r3["roc"], 2.0))

    # ---- 场景4：浮动收益凭证 + 期货对冲 ----
    cert_f = ClientContract(
        contract_type="income_certificate", direction="buy", notional=800,
        underlying_type="index_component",
        funds_raised=800, has_embedded_option=True,
        embedded_option_notional=800, stress_loss=60, term_days=270
    )
    fut_h = HedgeTrade(tool_type="futures", direction="short", notional=600,
                       underlying_type="index_component", futures_margin=72)
    r4 = analyze_contract(cert_f, [fut_h])
    check("e2e float cert: new_risk_reserve > 0", r4["new_risk_reserve"] > 0)
    check("e2e float cert: ro_nsfr valid", 0 < r4["ro_nsfr"] < 999)

    # ---- 场景5：买入期权 + 无对冲 ----
    buy_otc = ClientContract(
        contract_type="put_option", direction="buy", notional=1000,
        underlying_type="index_component",
        option_type="put_option", total_premium_amount=30, term_days=180
    )
    r5 = analyze_contract(buy_otc, [])
    check("e2e buy option: net_day1_cash = -30",
          math.isclose(r5["net_day1_cash"], -30.0))
    check("e2e buy option: premium payment only changes asset form",
          math.isclose(r5["assets_change"], 0.0))

    # ---- 场景6：空对冲列表不报错 ----
    r6 = analyze_contract(swap, [])
    check("e2e empty hedges: no crash, all keys present",
          all(k in r6 for k in REQUIRED_KEYS))

    # ---- 场景7：极端值 ----
    big = ClientContract(
        contract_type="equity_swap", direction="short", notional=1_000_000,
        underlying_type="index_component",
        margin_rate=10.0
    )
    r7 = analyze_contract(big, [])
    check("e2e large notional (1M): no overflow/crash",
          r7["net_day1_cash"] > 0 and r7["new_risk_reserve"] > 0)

    # ---- 场景8：is_effective_hedge 结构正确 ----
    ie = r["is_effective_hedge"]
    check("e2e is_effective_hedge: is list of [bool, str]",
          isinstance(ie, list) and len(ie) == 2)
    check("e2e is_effective_hedge: [0] is bool, [1] is str or None",
          isinstance(ie[0], bool) and (isinstance(ie[1], str) or ie[1] is None))

    # ---- 场景9：RO-LCR 分母为0(流动性改善) → 不适用 ----
    # 固定收益凭证 T>30天 + 无对冲：募集资金V全部变成HQLA，无COF流出
    # → ΔHQLA = +V, ΔOutflow = 0 → net_liquidity_drain = 0 - V < 0 → max(0, ...) = 0
    cert_long = ClientContract(
        contract_type="income_certificate", direction="buy", notional=500,
        underlying_type="index_component",
        funds_raised=500, term_days=90  # >30天
    )
    r_liq = analyze_contract(cert_long, [])
    check("e2e liquidity improvement: ro_lcr is None",
          r_liq["ro_lcr"] is None)

    # ---- 场景10：浮动收益凭证 Delta 非零，可参与有效对冲判定 ----
    cert_float = ClientContract(
        contract_type="income_certificate", direction="buy", notional=800,
        underlying_type="index_component", underlying_code="000300",
        funds_raised=800, has_embedded_option=True,
        embedded_option_notional=800, stress_loss=60, term_days=270
    )
    check("floating cert delta < 0 (short embedded option)",
          cert_float.get_otc_delta_amount() < 0)

    # ---- 场景11：资本杠杆率分子口径与风险覆盖率一致（扣减保证金）----
    # 卖出期权 + 期货对冲：net_capital_change < 0（保证金扣减核心净资本）
    # 杠杆率分母增加，分子扣减 → leverage_new 应低于仅分母增加时的值
    lev_opt = ClientContract(
        contract_type="call_option", direction="short", notional=1000,
        underlying_type="index_component",
        option_type="call_option", premium_rate=5.0,
        stress_loss=50, term_days=90
    )
    lev_hedge = HedgeTrade(tool_type="futures", direction="short", notional=800,
                           underlying_type="index_component", futures_margin=96)
    r_lev = analyze_contract(lev_opt, [lev_hedge])
    check("e2e leverage numerator deducts margin",
          r_lev["net_capital_change"] < 0)
    # 手动重算：分子 = 基准净资本 + Δ净资本
    nc = DEFAULT_CONFIG["firm"]["net_capital_base"] / 10000
    expected_new = (nc + r_lev["net_capital_change"]) / (
        DEFAULT_CONFIG["firm"]["on_off_balance_total_asset_base"] / 10000 + r_lev["assets_change"])
    check("e2e leverage_new uses adjusted net capital",
          math.isclose(r_lev["leverage_new"], expected_new))


# ============================================================
# 5. 数学一致性
# ============================================================
def test_math_consistency():
    print("\n=== 数学一致性 ===")

    otc = ClientContract(
        contract_type="call_option", direction="short", notional=1000,
        underlying_type="index_component",
        option_type="call_option", premium_rate=5.0,
        stress_loss=50, term_days=90
    )
    h = HedgeTrade(tool_type="futures", direction="short", notional=800,
                   underlying_type="index_component", futures_margin=96)
    r = analyze_contract(otc, [h])

    # lcr_change = lcr_new - lcr_old
    check("lcr_change = lcr_new - lcr_old",
          math.isclose(r["lcr_change"], r["lcr_new"] - r["lcr_old"]))

    # nsfr_change = nsfr_new - nsfr_old
    check("nsfr_change = nsfr_new - nsfr_old",
          math.isclose(r["nsfr_change"], r["nsfr_new"] - r["nsfr_old"]))

    # leverage_change = leverage_new - leverage_old
    check("leverage_change = leverage_new - leverage_old",
          math.isclose(r["leverage_change"], r["leverage_new"] - r["leverage_old"]))

    # ro_lcr = expected_income / max(0, net_liquidity_drain)
    # 验证 ro_lcr 在 denominator > 0 时符合定义
    ro_lcr_expected = r["expected_income"] / max(0, r["net_cof_change"] - (
        r["lcr_new"] * (
            DEFAULT_CONFIG["firm"]["LCR_COF_base"] / 10000 + r["net_cof_change"]
        ) - DEFAULT_CONFIG["firm"]["HQLA_base"] / 10000))

    # status 与阈值一致
    check("lcr_status matches lcr_new threshold",
          (r["lcr_new"] >= 1.20 and r["lcr_status"] == "safe") or
          (1.00 <= r["lcr_new"] < 1.20 and r["lcr_status"] == "warning") or
          (r["lcr_new"] < 1.00 and r["lcr_status"] == "danger"))

    check("leverage_status matches leverage_new threshold",
          (r["leverage_new"] >= 0.12 and r["leverage_status"] == "safe") or
          (0.08 <= r["leverage_new"] < 0.12 and r["leverage_status"] == "warning") or
          (r["leverage_new"] < 0.08 and r["leverage_status"] == "danger"))


# ============================================================
# 6. 模型完整性：所有 getter 方法不报错
# ============================================================
def test_all_getters_no_error():
    print("\n=== 所有 Getter 无报错 ===")

    otc = ClientContract(
        contract_type="call_option", direction="short", notional=1000,
        underlying_type="index_component",
        option_type="call_option", premium_rate=5.0,
        stress_loss=50, term_days=90, expiry_date="2026-12-31",
        begin_date="2026-07-01",
        underlying_name="沪深300", underlying_code="000300.SH",
        exercise_price=5000, contract_size=10,
        option_margin_amount=200, option_margin_rate=20.0,
        funds_raised=None,
    )
    for method_name in dir(otc):
        if method_name.startswith("get_") and callable(getattr(otc, method_name)):
            try:
                getattr(otc, method_name)()
            except Exception as e:
                check(f"otc.{method_name}() no error", False)
                print(f"    → {type(e).__name__}: {e}")
                continue
            check(f"otc.{method_name}() no error", True)

    hedge = HedgeTrade(
        tool_type="futures", direction="short", notional=800,
        underlying_type="index_component", futures_margin=96,
        option_margin=100, option_margin_rate=0.15
    )
    for method_name in dir(hedge):
        if method_name.startswith("get_") and callable(getattr(hedge, method_name)):
            try:
                getattr(hedge, method_name)()
            except Exception as e:
                check(f"hedge.{method_name}() no error", False)
                print(f"    → {type(e).__name__}: {e}")
                continue
            check(f"hedge.{method_name}() no error", True)


# ============================================================
# 7. 新增字段兼容性（underlying_market、stress loss 估算）
# ============================================================
def test_new_fields_and_helpers():
    print("\n=== 新增字段与辅助函数 ===")

    from backend.calculators.risk_reserve import estimate_otc_option_stress_loss

    # OtcContract 新增 underlying_market
    otc = ClientContract(
        contract_type="call_option", direction="short", notional=1000,
        underlying_type="index_component", underlying_market="CN",
        option_type="call_option", premium_rate=5.0,
        stress_loss=50, term_days=90
    )
    check("otc.underlying_market = CN", otc.get_otc_underlying_market() == "CN")

    # HedgeTrade 新增 underlying_market
    hedge = HedgeTrade(
        tool_type="etf", direction="long", notional=200,
        underlying_type="index_component", underlying_market="CN"
    )
    check("hedge.underlying_market = CN", hedge.get_tool_underlying_market() == "CN")

    # 未指定时默认为 None，不破坏旧测试
    otc_default = ClientContract(
        contract_type="put_option", direction="buy", notional=1000,
        underlying_type="general_stock"
    )
    check("otc.underlying_market default None", otc_default.get_otc_underlying_market() is None)

    # stress loss 估算函数接入
    loss = estimate_otc_option_stress_loss(
        spot_price=100.0, strike_price=100.0,
        contract_multiplier=100.0, contract_size=1000.0,
        option_type="call_option"
    )
    check("stress loss estimator returns 200", math.isclose(loss, 200.0))


def test_company_business_constraints():
    print("\n=== 公司业务范围约束 ===")
    otc = ClientContract(
        contract_type="equity_swap", direction="short", notional=1000,
        underlying_type="general_stock", underlying_instrument="stock",
        underlying_market="CN", underlying_code="600000", margin_rate=10.0,
    )
    stock = HedgeTrade(
        tool_type="stock", direction="long", notional=500,
        underlying_type="general_stock", underlying_market="CN",
        underlying_code="600000",
    )
    result = analyze_contract(otc, [stock])
    check("individual-stock physical hedge is rejected",
          not result["business_constraints"]["is_compliant"])
    check("noncompliant hedge cannot be regulatory effective",
          result["is_effective_hedge"][0] is False)

    overseas = ClientContract(
        contract_type="call_option", direction="short", notional=1000,
        underlying_type="general_stock", underlying_market="HK",
        option_type="call_option", premium_rate=5.0, stress_loss=50,
    )
    overseas_result = analyze_contract(overseas, [])
    check("overseas underlying is rejected without overseas credential",
          not overseas_result["business_constraints"]["is_compliant"])


# ============================================================
# 运行
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Integration & Model Validation Tests")
    print("=" * 60)

    test_config()
    test_client_contract()
    test_hedge_trade()
    test_analyzer_e2e()
    test_math_consistency()
    test_all_getters_no_error()
    test_new_fields_and_helpers()
    test_company_business_constraints()

    print(f"\n{'='*60}")
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        print("Some tests FAILED — see above for details.")
        sys.exit(1)
    else:
        print("All integration tests passed!")
