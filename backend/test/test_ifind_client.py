# ============================================================
# backend/test/test_ifind_client.py - iFinD 数据接口联机功能测试
# ============================================================
# 用途：逐项测试 iFinD 数据接口各功能是否正常工作
#       输出清晰标注 PASS / FAIL / SKIP

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 可选的本地联机测试凭据。提交或发送代码前必须保持为空。
IFIND_USER_NAME = ""
IFIND_PASSWORD = ""
CREDENTIALS_CONFIGURED = bool(IFIND_USER_NAME and IFIND_PASSWORD)
if CREDENTIALS_CONFIGURED:
    os.environ["IFIND_USER_NAME"] = IFIND_USER_NAME
    os.environ["IFIND_PASSWORD"] = IFIND_PASSWORD

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.services.ifind_client import (
    ifind_login,
    ifind_logout,
    get_underlying_price_series,
    calculate_correlation_between_price_series,
    get_realtime_price,
    get_latest_close_price,
    get_underlying_spot_price,
    get_onsite_option_greeks,
    is_trading_time,
)

# try raw API imports for debugging
try:
    from iFinDPy import (
        THS_iFinDLogin,
        THS_iFinDLogout,
        THS_HQ,
        THS_DS,
        THS_RQ,
    )
    RAW_API_AVAILABLE = True
except ImportError as e:
    RAW_API_AVAILABLE = False
    print(f"[INIT] iFinDPy 导入失败: {e}")

# =============== 全局计数器 ===============
PASS = 0
FAIL = 0
SKIP = 0


def check(desc, condition, skip=False):
    global PASS, FAIL, SKIP
    if skip:
        SKIP += 1
        print(f"  [SKIP] {desc}")
    elif condition:
        PASS += 1
        print(f"  [PASS] {desc}")
    else:
        FAIL += 1
        print(f"  [FAIL] {desc}")


# ============================================================
# 0. 环境检查
# ============================================================
def test_environment():
    print("\n" + "=" * 60)
    print("0. 环境检查")
    print("=" * 60)

    check("iFinDPy 模块可导入", RAW_API_AVAILABLE)
    check("iFinD测试凭据已填写（当前留空则跳过联机测试）",
          CREDENTIALS_CONFIGURED, skip=not CREDENTIALS_CONFIGURED)
    check("当前时间", True)
    print(f"    当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    是否交易时间: {is_trading_time()}")


# ============================================================
# 1. 登录测试
# ============================================================
def test_login():
    print("\n" + "=" * 60)
    print("1. 登录测试")
    print("=" * 60)

    # 1a: 强制登录
    if not RAW_API_AVAILABLE or not CREDENTIALS_CONFIGURED:
        check("1a 强制登录", False, skip=True)
        return

    try:
        result = THS_iFinDLogin(IFIND_USER_NAME, IFIND_PASSWORD)
        print(f"    THS_iFinDLogin 返回码: {result}")
        # 0 = 成功, -201 = 已登录
        check("1a THS_iFinDLogin 返回 0 或 -201 (成功/已登录)",
              result in (0, -201))
    except Exception as e:
        print(f"    THS_iFinDLogin 异常: {e}")
        check(f"1a THS_iFinDLogin 调用 (异常: {e})", False)

    # 1b: ifind_login() 封装函数（带状态缓存）
    try:
        ok = ifind_login(force=True)
        check("1b ifind_login(force=True) 返回 True", ok)
    except Exception as e:
        print(f"    ifind_login 异常: {e}")
        check(f"1b ifind_login (异常: {e})", False)

    # 1c: 缓存登录（不 force）
    try:
        ok2 = ifind_login(force=False)
        check("1c ifind_login(force=False) 缓存命中返回 True", ok2)
    except Exception as e:
        check(f"1c ifind_login cached (异常: {e})", False)


# ============================================================
# 2. THS_HQ — 历史行情（不同参数组合调试 -209）
# ============================================================
def test_ths_hq():
    print("\n" + "=" * 60)
    print("2. THS_HQ — 历史行情")
    print("=" * 60)

    if not RAW_API_AVAILABLE:
        check("2 跳过：iFinDPy 不可用", False, skip=True)
        return

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    test_codes = ["000300.SH", "600519.SH"]

    for code in test_codes:
        print(f"\n  --- 标的: {code} ---")

        # 2a: 当前写法（与 ifind_client.py 一致）
        try:
            result = THS_HQ(code, 'close', 'fill:Omit', start_date, end_date)
            if result is None:
                print(f"    2a 返回 None")
                check(f"2a THS_HQ({code}, close) 返回 None", False)
            elif hasattr(result, 'errorcode'):
                print(f"    2a errorcode={result.errorcode}, errmsg={result.errmsg}")
                check(f"2a THS_HQ({code}, close) errorcode=0",
                      result.errorcode == 0)
            else:
                print(f"    2a 返回数据, type={type(result)}")
                try:
                    df = pd.DataFrame(result.data)
                    print(f"    2a 数据行数: {len(df)}, 列: {list(df.columns)[:5]}...")
                    check(f"2a THS_HQ({code}, close) 数据非空", not df.empty)
                except Exception as e:
                    check(f"2a THS_HQ({code}, close) 解析失败: {e}", False)
        except Exception as e:
            print(f"    2a THS_HQ 异常: {e}")
            check(f"2a THS_HQ({code}, close) (异常)", False)

        # 2b: 尝试不同 price_type — open
        try:
            result = THS_HQ(code, 'open', 'fill:Omit', start_date, end_date)
            if hasattr(result, 'errorcode') and result.errorcode != 0:
                print(f"    2b errorcode={result.errorcode}, errmsg={result.errmsg}")
                check(f"2b THS_HQ({code}, open) errorcode=0",
                      result.errorcode == 0)
            elif result is not None:
                df = pd.DataFrame(result.data)
                check(f"2b THS_HQ({code}, open) 数据非空", not df.empty)
            else:
                check(f"2b THS_HQ({code}, open) 返回 None", False)
        except Exception as e:
            print(f"    2b THS_HQ({code}, open) 异常: {e}")
            check(f"2b THS_HQ({code}, open) (异常)", False)

        # 2c: 尝试更换 fill 参数
        try:
            result = THS_HQ(code, 'close', 'fill:Previous', start_date, end_date)
            if hasattr(result, 'errorcode'):
                print(f"    2c fill:Previous — errorcode={result.errorcode}, errmsg={result.errmsg}")
                check(f"2c THS_HQ({code}, fill:Previous) errorcode=0",
                      result.errorcode == 0)
            elif result is not None:
                check(f"2c THS_HQ({code}, fill:Previous) 返回非None", True)
            else:
                check(f"2c THS_HQ({code}, fill:Previous) 返回 None", False)
        except Exception as e:
            print(f"    2c 异常: {e}")
            check(f"2c THS_HQ({code}, fill:Previous) (异常)", False)


# ============================================================
# 3. THS_RQ — 实时行情
# ============================================================
def test_ths_rq():
    print("\n" + "=" * 60)
    print("3. THS_RQ — 实时行情")
    print("=" * 60)

    if not RAW_API_AVAILABLE:
        check("3 跳过：iFinDPy 不可用", False, skip=True)
        return

    test_codes = ["000300.SH", "600519.SH"]

    for code in test_codes:
        print(f"\n  --- 标的: {code} ---")

        # 3a: 原始 THS_RQ
        try:
            result = THS_RQ(code, 'latest')
            if result is None:
                print(f"    3a 返回 None")
                check(f"3a THS_RQ({code}, latest) 返回 None", False)
            elif hasattr(result, 'errorcode'):
                print(f"    3a errorcode={result.errorcode}, errmsg={result.errmsg}")
                check(f"3a THS_RQ({code}, latest) errorcode=0",
                      result.errorcode == 0)
            else:
                df = pd.DataFrame(result.data)
                print(f"    3a 数据: {df.to_dict() if not df.empty else '空'}")
                check(f"3a THS_RQ({code}, latest) 数据非空", not df.empty)
        except Exception as e:
            print(f"    3a THS_RQ 异常: {e}")
            check(f"3a THS_RQ({code}, latest) (异常)", False)

        # 3b: 封装函数 get_realtime_price
        price = get_realtime_price(code)
        if price is not None:
            print(f"    3b get_realtime_price = {price}")
            check(f"3b get_realtime_price({code}) 返回有效价格", price > 0)
        else:
            print(f"    3b get_realtime_price = None")
            check(f"3b get_realtime_price({code}) 返回 None", False)


# ============================================================
# 4. THS_DS — 数据服务（不同参数组合调试 -209）
# ============================================================
def test_ths_ds():
    print("\n" + "=" * 60)
    print("4. THS_DS — 数据服务")
    print("=" * 60)

    if not RAW_API_AVAILABLE:
        check("4 跳过：iFinDPy 不可用", False, skip=True)
        return

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

    test_cases = [
        # (code, indicator, label)
        ("000300.SH", "ths_close_price_index", "沪深300收盘价"),
        ("600519.SH", "ths_close_price_stock", "茅台收盘价"),
    ]

    for code, indicator, label in test_cases:
        print(f"\n  --- {label}: {code} / {indicator} ---")

        # 4a: 当前写法（与 ifind_client.py 一致）
        try:
            result = THS_DS(code, indicator, '100', 'Days:Tradedays,Fill:Blank',
                           start_date, end_date)
            if result is None:
                print(f"    4a 返回 None")
                check(f"4a THS_DS({label}) 返回 None", False)
            elif hasattr(result, 'errorcode'):
                print(f"    4a errorcode={result.errorcode}, errmsg={result.errmsg}")
                check(f"4a THS_DS({label}) errorcode=0",
                      result.errorcode == 0)
            else:
                df = pd.DataFrame(result.data)
                print(f"    4a 数据行数: {len(df)}, 列: {list(df.columns)}")
                check(f"4a THS_DS({label}) 数据非空", not df.empty)
        except Exception as e:
            print(f"    4a THS_DS 异常: {e}")
            check(f"4a THS_DS({label}) (异常)", False)

        # 4b: 尝试不同参数格式 — 去掉 Days: 前缀
        try:
            result = THS_DS(code, indicator, '100', 'Tradedays,Fill:Blank',
                           start_date, end_date)
            if hasattr(result, 'errorcode'):
                print(f"    4b Tradedays,Fill:Blank — errorcode={result.errorcode}")
                if result.errorcode != 0:
                    print(f"        errmsg={result.errmsg}")
                check(f"4b THS_DS({label}) alt params errorcode=0",
                      result.errorcode == 0)
            elif result is not None:
                check(f"4b THS_DS({label}) alt params 返回非None", True)
            else:
                check(f"4b THS_DS({label}) alt params 返回 None", False)
        except Exception as e:
            print(f"    4b 异常: {e}")
            check(f"4b THS_DS({label}) alt params (异常)", False)

    # 4c: 测试 get_latest_close_price 封装函数
    print(f"\n  --- 封装函数 get_latest_close_price ---")
    price1 = get_latest_close_price("000300.SH", "index", market="CN")
    if price1 is not None:
        print(f"    4c 沪深300最新收盘价 = {price1}")
        check(f"4c get_latest_close_price(000300.SH, index) 有效", price1 > 0)
    else:
        print(f"    4c 沪深300最新收盘价 = None")
        check(f"4c get_latest_close_price(000300.SH, index) 返回 None", False)

    price2 = get_latest_close_price("600519.SH", "stock", market="CN")
    if price2 is not None:
        print(f"    4c 贵州茅台最新收盘价 = {price2}")
        check(f"4c get_latest_close_price(600519.SH, stock) 有效", price2 > 0)
    else:
        check(f"4c get_latest_close_price(600519.SH, stock) 返回 None", False)


# ============================================================
# 5. 历史价格序列 + 相关性计算
# ============================================================
def test_price_series_and_corr():
    print("\n" + "=" * 60)
    print("5. 历史价格序列 & 相关性计算")
    print("=" * 60)

    # 5a: 获取两个标的价格序列
    prices_300 = get_underlying_price_series("000300.SH", "close")
    has_300 = len(prices_300.get("000300.SH", [])) > 0
    n_300 = len(prices_300.get("000300.SH", []))
    print(f"    5a 000300.SH 获取到 {n_300} 条价格数据")
    check("5a get_underlying_price_series(000300.SH) 有数据", has_300)

    prices_519 = get_underlying_price_series("600519.SH", "close")
    has_519 = len(prices_519.get("600519.SH", [])) > 0
    n_519 = len(prices_519.get("600519.SH", []))
    print(f"    5a 600519.SH 获取到 {n_519} 条价格数据")
    check("5a get_underlying_price_series(600519.SH) 有数据", has_519)

    # 5b: 计算相关系数
    corr = calculate_correlation_between_price_series(
        "000300.SH", prices_300,
        "600519.SH", prices_519,
    )
    if not np.isnan(corr):
        print(f"    5b 000300.SH vs 600519.SH 相关系数 = {corr:.4f}")
        check("5b 相关系数计算成功", -1.0 <= corr <= 1.0)
    else:
        print(f"    5b 相关系数 = NaN（数据不足）")
        check("5b 相关系数计算", has_300 and has_519 and n_300 >= 2 and n_519 >= 2,
              skip=(not has_300 or not has_519))


# ============================================================
# 6. get_underlying_spot_price（综合实时+收盘价）
# ============================================================
def test_spot_price():
    print("\n" + "=" * 60)
    print("6. 现货价格综合获取")
    print("=" * 60)

    print(f"    当前是否交易时间: {is_trading_time()}")

    price = get_underlying_spot_price("000300.SH", "index", market="CN")
    if price is not None:
        print(f"    6 沪深300现货价 = {price}")
        check("6 get_underlying_spot_price(000300.SH, index) 有效", price > 0)
    else:
        print(f"    6 沪深300现货价 = None")
        check("6 get_underlying_spot_price(000300.SH, index) 返回 None", False)


# ============================================================
# 7. 场内期权 Greeks
# ============================================================
def test_option_greeks():
    print("\n" + "=" * 60)
    print("7. 场内期权 Greeks")
    print("=" * 60)

    # ---- 7a: iFinD API 获取（自动追加 .SH 后缀）----
    print("\n  --- 7a: iFinD API 获取（合约编码 10011855，自动追加 .SH 后缀）---")
    test_options = [
        "10011855",           # 合约编码（不带后缀，自动追加 .SH）
        "10011855.SH",        # 合约编码（带后缀）
    ]
    greek_types = ["delta", "gamma", "vega", "theta", "rho"]

    for opt_code in test_options:
        print(f"\n    代码: {opt_code}")
        for g in greek_types:
            val, err = get_onsite_option_greeks(opt_code, g)
            if val is not None:
                print(f"      {g:6s} = {val:.6f}")
                check(f"7a iFinD {opt_code} {g}", True)
            else:
                print(f"      {g:6s} = None (错误: {err})")
                check(f"7a iFinD {opt_code} {g}", False)
        # 只测第一种代码即可，无需重复
        break

    # ---- 7b: Black-Scholes 本地计算回退 ----
    print("\n  --- 7b: Black-Scholes 本地模型回退（不依赖 iFinD）---")
    # 模拟 50ETF 平值看涨期权: S≈3.02, K=3.00, 30天到期
    S, K, T = 3.02, 3.00, 30

    for g in greek_types:
        v_call, _ = get_onsite_option_greeks(
            None, g, spot_price=S, strike_price=K,
            days_to_expiry=T, option_type='call'
        )
        v_put, _ = get_onsite_option_greeks(
            None, g, spot_price=S, strike_price=K,
            days_to_expiry=T, option_type='put'
        )
        print(f"    {g:6s}: call={v_call:.6f}, put={v_put:.6f}")
        check(f"7b BS {g} call 非空", v_call is not None)
        check(f"7b BS {g} put 非空", v_put is not None)

    # 7c: BS 合理性校验 — call delta + |put delta| ≈ 1
    d_call, _ = get_onsite_option_greeks(
        None, 'delta', spot_price=S, strike_price=K,
        days_to_expiry=T, option_type='call'
    )
    d_put, _ = get_onsite_option_greeks(
        None, 'delta', spot_price=S, strike_price=K,
        days_to_expiry=T, option_type='put'
    )
    print(f"    校验: call_delta - put_delta = {d_call - d_put:.4f}（期望 ≈ 1.0）")
    check("7c BS delta 校验 (call-put≈1)", abs((d_call - d_put) - 1.0) < 0.01)

    # 7d: 空参数边界
    val_none, _ = get_onsite_option_greeks(None, "delta")
    check("7d get_onsite_option_greeks(None, delta) 无参数时返回 None", val_none is None)

    val_empty, _ = get_onsite_option_greeks("", "delta")
    check("7d get_onsite_option_greeks('', delta) 空字符串时返回 None", val_empty is None)

    # 7e: 缺失 BS 参数也返回 None
    val_partial, _ = get_onsite_option_greeks(
        None, 'delta', spot_price=3.0  # 缺少 strike 和 days
    )
    check("7d 缺少 BS 参数时返回 None", val_partial is None)


# ============================================================
# 8. 登出测试
# ============================================================
def test_logout():
    print("\n" + "=" * 60)
    print("8. 登出测试")
    print("=" * 60)

    if not RAW_API_AVAILABLE:
        check("8 跳过：iFinDPy 不可用", False, skip=True)
        return

    # 8a: 封装函数登出
    try:
        ifind_logout()
        check("8a ifind_logout() 无异常", True)
    except Exception as e:
        print(f"    ifind_logout 异常: {e}")
        check(f"8a ifind_logout (异常: {e})", False)

    # 8b: 登出后重新登录验证
    try:
        ok = ifind_login(force=True)
        check("8b 登出后重新登录成功", ok)
    except Exception as e:
        check(f"8b 登出后重新登录 (异常: {e})", False)


# ============================================================
# 9. 压力测试：多次调用是否稳定（排查 1010 logout 问题）
# ============================================================
def test_stress():
    print("\n" + "=" * 60)
    print("9. 多次调用稳定性测试")
    print("=" * 60)

    if not RAW_API_AVAILABLE:
        check("9 跳过：iFinDPy 不可用", False, skip=True)
        return

    # 确保已登录
    ifind_login(force=True)

    # 连续调用 5 次
    failures = 0
    for i in range(5):
        try:
            price = get_realtime_price("000300.SH")
            status = "OK" if price is not None else "None"
            print(f"    第{i+1}次: {status}")
            if price is None:
                failures += 1
        except Exception as e:
            print(f"    第{i+1}次: 异常 {e}")
            failures += 1

    check("9 连续5次调用 THS_RQ 无异常", failures == 0)
    if failures > 0:
        print(f"    [WARN] {failures}/5 次调用失败 — 可能存在 session 超时问题 (1010)")


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("iFinD Client — 功能测试")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    test_environment()
    if CREDENTIALS_CONFIGURED:
        test_login()
        test_ths_hq()
        test_ths_rq()
        test_ths_ds()
        test_price_series_and_corr()
        test_spot_price()
        test_option_greeks()
        test_stress()      # 稳定性在登出之前
        test_logout()
    else:
        print("\n[SKIP] 未填写 iFinD 测试账号和密码，联机接口测试全部跳过。")

    # ========== 汇总 ==========
    total = PASS + FAIL + SKIP
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    print(f"  PASS: {PASS}")
    print(f"  FAIL: {FAIL}")
    print(f"  SKIP: {SKIP}")
    print(f"  TOTAL: {total}")
    print("-" * 60)

    if FAIL == 0 and PASS > 0:
        print("  >>> 全部测试通过 <<<")
    elif FAIL > 0:
        print(f"  >>> {FAIL} 项测试失败，请查看上方详情 <<<")
        # 常见问题提示
        print("\n  常见问题排查:")
        print("  - -209 (params invalid): 检查代码格式(如000300.SH)和参数顺序")
        print("  - 1010 (logout): 可能是 session 超时或长时间未操作")
        print("  - 若全部 FAIL 但 0a 环境正常: 检查 iFinD 终端是否已启动并登录")
    else:
        print("  >>> 无有效测试结果，请检查 iFinD 环境 <<<")

    sys.exit(0 if FAIL == 0 else 1)
