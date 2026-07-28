# ============================================================
# backend/test_calculators.py - 计算器自验证测试
# ============================================================
"""运行：cd risk_cal2 && python -m backend.test_calculators"""

import sys
import os

# 确保 risk_cal2 在 sys.path 中，使 backend 包的相对导入正常工作
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from backend.models.client_contract import OtcContract
from backend.models.hedge_trade import HedgeTrade
from backend.calculators.lcr import calc_lcr_impact, _calc_hedge_hqla
from backend.calculators.nsfr import calc_nsfr_impact, _calc_hedge_rsf
from backend.calculators.risk_reserve import (
    calc_total_risk_reserve,
    _get_client_investment_scale,
    _get_hedge_investment_scale,
    _is_non_full_margin_swap,
    _is_individual_stock,
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
        print(f"  [FAIL] {name}  {detail}")


def make_hedge(*args, **kwargs):
    """快速创建 HedgeTrade，默认方向为对冲客户空头（买入）"""
    defaults = {
        "tool_type": "etf",
        "direction": "long",
        "notional": 500.0,
        "underlying_type": "index_component",
        "underlying_code": "000300",
    }
    defaults.update(kwargs)
    return HedgeTrade(**defaults)


# ============================================================
# 1. 场外期权 — 卖出看涨 (short call)
# ============================================================
def test_option_short():
    print("\n=== 卖出看涨期权 (short call) ===")
    otc = OtcContract(
        contract_type="call_option",
        direction="short",
        notional=10000.0,
        underlying_type="index_component",
        underlying_code="000300",
        option_type="call_option",
        premium_rate=5.0,
        term_days=180,
        stress_loss=200.0,
        expected_yield=0.08,
    )
    # 对冲: 买入 5000w 沪深300 ETF
    hedges = [make_hedge(tool_type="etf", notional=5000.0)]

    # LCR
    lcr = calc_lcr_impact(otc, hedges)
    # 客户端: 卖出收权利金 = 10000 * 5% = 500w → +HQLA
    # 对冲端: 买入ETF付现金 5000w, ETF折算 5000*50%=2500w → 净 -2500w
    # 总 HQLA = 500 - 2500 = -2000
    check("LCR HQLA (short call)", abs(lcr["hqla_change"] - (-2000.0)) < 0.01,
          f"got {lcr['hqla_change']}")
    # COF: S_short = max(5*200, 10000*0.5%) = max(1000, 50) = 1000; × 20% = 200
    check("LCR COF (short call)", abs(lcr["net_cof_change"] - 200.0) < 0.01,
          f"got {lcr['net_cof_change']}")

    # NSFR
    nsfr = calc_nsfr_impact(otc, hedges)
    # ASF: T=180天(<365, >=180) → 0% → 0
    check("NSFR ASF (short call 180d)", abs(nsfr["asf_change"] - 0.0) < 0.01,
          f"got {nsfr['asf_change']}")
    # RSF client: S_short=1000 × 12% = 120
    # RSF hedge: ETF index 5000×10% = 500 → total 620
    check("NSFR RSF (short call)", abs(nsfr["rsf_change"] - 620.0) < 0.01,
          f"got {nsfr['rsf_change']}")

    # Risk Reserve (unhedged)
    rr = calc_total_risk_reserve(otc, hedges, is_hedge_effective=False)
    # S_client = S_short = max(5*200, 10000*0.5%) = 1000
    # Market risk = 1000 × 30% × 1.0 = 300
    check("RiskReserve unhedged (short call)", abs(rr - 300.0) < 0.01,
          f"got {rr}")

    # Risk Reserve (hedged)
    rr_h = calc_total_risk_reserve(otc, hedges, is_hedge_effective=True)
    # Hedged: (1000 + 5000) × 5% × 1.0 = 300
    check("RiskReserve hedged (short call)", abs(rr_h - 300.0) < 0.01,
          f"got {rr_h}")

    # ASF 期限测试: T≥365
    otc_long = OtcContract(
        contract_type="call_option", direction="short", notional=10000.0,
        underlying_type="index_component", underlying_code="000300",
        option_type="call_option", premium_rate=5.0, term_days=400,
        stress_loss=200.0, expected_yield=0.08,
    )
    nsfr2 = calc_nsfr_impact(otc_long, [])
    # ASF: T=400天 ≥ 365 → premium × 100% = 500
    check("NSFR ASF (short call 400d)", abs(nsfr2["asf_change"] - 500.0) < 0.01,
          f"got {nsfr2['asf_change']}")

    # LCR: 买入期权无 COF
    otc_buy = OtcContract(
        contract_type="call_option", direction="buy", notional=10000.0,
        underlying_type="index_component", underlying_code="000300",
        option_type="call_option", premium_rate=5.0, term_days=90,
    )
    lcr_buy = calc_lcr_impact(otc_buy, [])
    check("LCR COF (buy option = 0)", abs(lcr_buy["net_cof_change"] - 0.0) < 0.01,
          f"got {lcr_buy['net_cof_change']}")
    # HQLA: 买入付权利金 -500
    check("LCR HQLA (buy option)", abs(lcr_buy["hqla_change"] - (-500.0)) < 0.01,
          f"got {lcr_buy['hqla_change']}")


# ============================================================
# 2. 收益互换
# ============================================================
def test_swap():
    print("\n=== 收益互换 ===")
    otc = OtcContract(
        contract_type="equity_swap",
        direction="short",
        notional=20000.0,
        underlying_type="general_stock",
        underlying_code="600519",
        margin_rate=10.0,
        term_days=365,
        expected_yield=0.06,
    )
    hedges = [
        make_hedge(tool_type="futures", notional=18000.0, direction="short"),
    ]

    # LCR
    lcr = calc_lcr_impact(otc, hedges)
    # HQLA client: 收保证金 = 20000 * 10% = 2000
    # HQLA hedge: 期货保证金 = 18000 * 12% = 2160 流出 → -2160
    # 总 = -160
    check("LCR HQLA (swap)", abs(lcr["hqla_change"] - (-160.0)) < 0.01,
          f"got {lcr['hqla_change']}")
    # COF: N × 0.2% = 20000 × 0.002 = 40
    check("LCR COF (swap)", abs(lcr["net_cof_change"] - 40.0) < 0.01,
          f"got {lcr['net_cof_change']}")

    # NSFR
    nsfr = calc_nsfr_impact(otc, hedges)
    # ASF: 保证金归交易性负债 → 0
    check("NSFR ASF (swap)", abs(nsfr["asf_change"] - 0.0) < 0.01,
          f"got {nsfr['asf_change']}")
    # RSF client: 20000 × 1% = 200
    # RSF hedge: 期货 18000 × 12% = 2160 → total 2360
    check("NSFR RSF (swap)", abs(nsfr["rsf_change"] - 2360.0) < 0.01,
          f"got {nsfr['rsf_change']}")

    # Risk Reserve (非全额 + 个股 → penalty)
    check("non-full-margin", _is_non_full_margin_swap(otc))
    check("individual-stock", _is_individual_stock(otc))

    rr = calc_total_risk_reserve(otc, hedges, is_hedge_effective=False)
    # Market: S_client=2000, 2000×30%=600, penalty ×2 = 1200
    # Credit: 20000×5%=1000
    # Total: (1200+1000)×1.0 = 2200
    check("RiskReserve unhedged (swap penalty)", abs(rr - 2200.0) < 0.01,
          f"got {rr}")

    rr_h = calc_total_risk_reserve(otc, hedges, is_hedge_effective=True)
    # Hedged market: (2000+2700)×5%×2 = 470, credit=1000 → (470+1000)×1.0=1470
    # S_hedge: futures=18000×15%=2700
    check("RiskReserve hedged (swap penalty)", abs(rr_h - 1470.0) < 0.01,
          f"got {rr_h}")

    # 无惩罚情况 (指数成分股)
    otc_no_pen = OtcContract(
        contract_type="equity_swap", direction="short", notional=20000.0,
        underlying_type="index_component", underlying_code="000300",
        margin_rate=10.0, term_days=365, expected_yield=0.06,
    )
    rr_np = calc_total_risk_reserve(otc_no_pen, [], is_hedge_effective=False)
    # Market: 2000×30%=600 (no penalty), Credit: 20000×5%=1000 → 1600
    check("RiskReserve (swap no penalty)", abs(rr_np - 1600.0) < 0.01,
          f"got {rr_np}")


# ============================================================
# 3. 收益凭证
# ============================================================
def test_income_cert():
    print("\n=== 收益凭证 ===")
    # 固定收益凭证 (无内嵌衍生品)
    otc_fixed = OtcContract(
        contract_type="income_certificate",
        direction="short",
        notional=50000.0,
        underlying_type="general_stock",
        underlying_code="000001",
        funds_raised=50000.0,
        term_days=60,
        expected_yield=0.04,
        stress_loss=None,  # 无内嵌期权
    )
    hedges = [
        make_hedge(tool_type="stock", notional=30000.0, stock_type="general_stock",
                   underlying_type="general_stock"),
        make_hedge(tool_type="etf", notional=20000.0, underlying_type="index_component"),
    ]

    # LCR
    lcr = calc_lcr_impact(otc_fixed, hedges)
    # HQLA: V=50000, hedge cash: -30000(stock)-20000(ETF) = -50000, ETF HQLA: 20000×50%=10000
    # stock: general_stock HQLA=0%
    # Total: 50000 - 50000 + 10000 = 10000
    check("LCR HQLA (fixed cert)", abs(lcr["hqla_change"] - 10000.0) < 0.01,
          f"got {lcr['hqla_change']}")
    # COF: T=60 > 30 → debt=0; no embedded → 0
    check("LCR COF (fixed cert 60d)", abs(lcr["net_cof_change"] - 0.0) < 0.01,
          f"got {lcr['net_cof_change']}")

    # T ≤ 30: debt outflow = V = 50000
    otc30 = OtcContract(
        contract_type="income_certificate", direction="short", notional=50000.0,
        underlying_type="general_stock", underlying_code="000001",
        funds_raised=50000.0, term_days=20, stress_loss=None,
    )
    lcr30 = calc_lcr_impact(otc30, [])
    check("LCR COF (≤30d)", abs(lcr30["net_cof_change"] - 50000.0) < 0.01,
          f"got {lcr30['net_cof_change']}")

    # NSFR
    nsfr = calc_nsfr_impact(otc_fixed, hedges)
    # ASF: T=60 < 180 → 0
    check("NSFR ASF (fixed cert 60d)", abs(nsfr["asf_change"] - 0.0) < 0.01,
          f"got {nsfr['asf_change']}")
    # RSF hedge: stock 30000×50%=15000, ETF 20000×10%=2000 → total 17000
    check("NSFR RSF (fixed cert)", abs(nsfr["rsf_change"] - 17000.0) < 0.01,
          f"got {nsfr['rsf_change']}")

    # T ≥ 365 → ASF = V × 100%
    otc1y = OtcContract(
        contract_type="income_certificate", direction="short", notional=50000.0,
        underlying_type="general_stock", underlying_code="000001",
        funds_raised=50000.0, term_days=400, stress_loss=None,
    )
    nsfr1y = calc_nsfr_impact(otc1y, [])
    check("NSFR ASF (≥1y)", abs(nsfr1y["asf_change"] - 50000.0) < 0.01,
          f"got {nsfr1y['asf_change']}")

    # Risk Reserve (固定 = 0)
    rr = calc_total_risk_reserve(otc_fixed, hedges, is_hedge_effective=False)
    check("RiskReserve (fixed cert = 0)", abs(rr - 0.0) < 0.01,
          f"got {rr}")

    # 浮动收益凭证
    otc_float = OtcContract(
        contract_type="income_certificate",
        direction="short",
        notional=50000.0,
        underlying_type="index_component",
        underlying_code="000300",
        funds_raised=50000.0,
        term_days=90,
        stress_loss=300.0,  # 含内嵌衍生品
        expected_yield=0.05,
    )
    # LCR: 浮动的内嵌期权 → S_short = max(5*300, 50000*0.5%) = max(1500, 250) = 1500
    # COF = 1500 × 20% = 300
    lcr_fl = calc_lcr_impact(otc_float, [])
    check("LCR COF (floating cert)", abs(lcr_fl["net_cof_change"] - 300.0) < 0.01,
          f"got {lcr_fl['net_cof_change']}")

    # NSFR: RSF = S_short × 12% = 1500 × 12% = 180
    nsfr_fl = calc_nsfr_impact(otc_float, [])
    check("NSFR RSF (floating cert)", abs(nsfr_fl["rsf_change"] - 180.0) < 0.01,
          f"got {nsfr_fl['rsf_change']}")

    # Risk Reserve: S_short=1500 × 30% = 450
    rr_fl = calc_total_risk_reserve(otc_float, [], is_hedge_effective=False)
    check("RiskReserve (floating cert)", abs(rr_fl - 450.0) < 0.01,
          f"got {rr_fl}")


# ============================================================
# 4. 辅助函数与边界情况
# ============================================================
def test_helpers():
    print("\n=== 辅助函数 ===")

    # 投资规模计算
    otc_buy_put = OtcContract(
        contract_type="put_option", direction="buy", notional=10000.0,
        underlying_type="index_component", underlying_code="000300",
        option_type="put_option", premium_rate=3.0,
    )
    s = _get_client_investment_scale(otc_buy_put)
    check("Scale buy option = premium", abs(s - 300.0) < 0.01, f"got {s}")

    otc_short = OtcContract(
        contract_type="put_option", direction="short", notional=10000.0,
        underlying_type="index_component", underlying_code="000300",
        option_type="put_option", premium_rate=3.0, stress_loss=100.0,
    )
    s2 = _get_client_investment_scale(otc_short)
    # S_short = max(5*100, 10000*0.5%) = max(500, 50) = 500
    check("Scale short option = S_short", abs(s2 - 500.0) < 0.01, f"got {s2}")

    otc_swap = OtcContract(
        contract_type="equity_swap", direction="short", notional=20000.0,
        underlying_type="index_component", underlying_code="000300",
    )
    s3 = _get_client_investment_scale(otc_swap)
    check("Scale swap = N×10%", abs(s3 - 2000.0) < 0.01, f"got {s3}")

    # 对冲工具投资规模
    h_futures = make_hedge(tool_type="futures", notional=10000.0)
    check("Hedge scale futures", abs(_get_hedge_investment_scale(h_futures) - 1500.0) < 0.01)

    h_otc = make_hedge(tool_type="otc_hedge", notional=8000.0)
    check("Hedge scale OTC", abs(_get_hedge_investment_scale(h_otc) - 800.0) < 0.01)

    h_etf = make_hedge(tool_type="etf", notional=6000.0)
    check("Hedge scale ETF", abs(_get_hedge_investment_scale(h_etf) - 6000.0) < 0.01)

    # 空 hedge_list
    lcr_empty = calc_lcr_impact(otc_short, [])
    check("LCR with empty hedges", isinstance(lcr_empty, dict))

    nsfr_empty = calc_nsfr_impact(otc_short, [])
    check("NSFR with empty hedges", isinstance(nsfr_empty, dict))

    # 各种对冲类型 HQLA 测试
    h_etf_idx = make_hedge(tool_type="etf", notional=1000.0, direction="long", underlying_type="index_component")
    hqla1 = _calc_hedge_hqla([h_etf_idx])
    # cash=-1000, asset=1000×50%=500 → net=-500
    check("HQLA ETF index", abs(hqla1 - (-500.0)) < 0.01, f"got {hqla1}")

    h_stock_gen = make_hedge(tool_type="stock", notional=1000.0, direction="long",
                             stock_type="general_stock", underlying_type="general_stock")
    hqla2 = _calc_hedge_hqla([h_stock_gen])
    # cash=-1000, asset=0 → net=-1000
    check("HQLA stock general", abs(hqla2 - (-1000.0)) < 0.01, f"got {hqla2}")

    h_fut = make_hedge(tool_type="futures", notional=10000.0, direction="short")
    hqla3 = _calc_hedge_hqla([h_fut])
    # margin = 10000×12% = 1200 paid out → hqla -= 1200 → -1200
    check("HQLA futures margin", abs(hqla3 - (-1200.0)) < 0.01, f"got {hqla3}")

    # 多种对冲 RSF
    rsf_test = _calc_hedge_rsf([
        make_hedge(tool_type="etf", notional=2000.0),
        make_hedge(tool_type="stock", notional=1000.0, stock_type="restricted_stock"),
        make_hedge(tool_type="futures", notional=5000.0),
        make_hedge(tool_type="otc_hedge", notional=3000.0),
        make_hedge(tool_type="private_fund", subscription_amount=4000.0),
    ])
    # ETF index: 2000×10% = 200
    # stock restricted: 1000×100% = 1000
    # futures: 5000×12% = 600
    # otc: 3000×1% = 30
    # private_fund: 4000×20% = 800
    # total = 2630
    check("RSF multi-hedge", abs(rsf_test - 2630.0) < 0.01, f"got {rsf_test}")


# ============================================================
# 运行
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Calculators Self-Validation Tests")
    print("=" * 60)

    test_option_short()
    test_swap()
    test_income_cert()
    test_helpers()

    print(f"\n{'='*60}")
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
    else:
        print("All tests passed!")
