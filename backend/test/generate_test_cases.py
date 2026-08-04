# ============================================================
# backend/test/generate_test_cases.py
# 生成典型业务测试样例并写入 test_cases.md
# ============================================================
"""运行：cd risk_cal2 && python -m backend.test.generate_test_cases"""

import sys
import os
import math
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List

# 可选：如需用真实 iFinD 数据生成 TC02/TC08/TC10，可在本机临时填写；
# 提交或发送代码前务必保持为空。留空时脚本使用既有 Mock 路径，仍生成全部11例。
IFIND_USER_NAME = "glzq703"
IFIND_PASSWORD = "96998XuY"
if IFIND_USER_NAME and IFIND_PASSWORD:
    os.environ["IFIND_USER_NAME"] = IFIND_USER_NAME
    os.environ["IFIND_PASSWORD"] = IFIND_PASSWORD

# 将项目根目录加入 sys.path，使 backend 包可被导入
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend import ClientContract, HedgeTrade, analyze_contract, DEFAULT_CONFIG
from backend.calculators import hedge_validator


# ============================================================
# iFinD 可用性探测与 Mock（保证离线/无终端时仍能生成样例）
# ============================================================

def _try_ifind_login() -> bool:
    """尝试登录 iFinD；通过 ifind_client 封装函数走缓存登录。"""
    try:
        from backend.services.ifind_client import ifind_login, ifind_logout
        return ifind_login(force=True)
    except Exception:
        return False


IFIND_AVAILABLE = _try_ifind_login()


def _mock_price_series(underlying_code: str, price_type: str = "close", **kwargs):
    """模拟历史收盘价序列（252 个交易日），返回 List[float]。"""
    base = {"000300.SH": 4000, "510300.SH": 4.0, "510050.SH": 2.5,
            "000852.SH": 6000, "600519.SH": 1700, "000001.SH": 3000}.get(underlying_code, 1000)
    prices = [base * (1 + 0.001 * math.sin(i / 10) + 0.0002 * i) for i in range(252)]
    return {underlying_code: prices}


def _mock_corr(otc_code, otc_prices, hedge_code, hedge_prices):
    """模拟高相关性（同指数与其 ETF 视为高度相关）。"""
    return 0.99


def _mock_greeks(option_code: str, greek_letter: str = 'delta'):
    """模拟场内期权 Greeks；仅对看起来像合约编码的代码返回固定值，否则模拟 iFinD 返回 None。"""
    if not option_code or not isinstance(option_code, str):
        return None, "Mock: 期权代码为空或无效"
    code = option_code.strip()
    # 模拟真实 iFinD：8 位数字合约编码视为有效，其他视为无效
    is_valid = code.isdigit() and len(code) == 8
    if is_valid and greek_letter.lower() == 'delta':
        return 0.65, None
    return None, "Mock: 无效期权代码"


if not IFIND_AVAILABLE:
    # 替换 hedge_validator 中使用的 iFinD 函数为本地 mock
    hedge_validator.get_underlying_price_series = _mock_price_series
    hedge_validator.calculate_correlation_between_price_series = _mock_corr
    hedge_validator.get_onsite_option_greeks = _mock_greeks


# ============================================================
# 测试样例定义
# ============================================================

def _make_contract(kwargs: Dict[str, Any]) -> ClientContract:
    """快速构造 OtcContract（前端映射后的英文参数字段）。"""
    return ClientContract(**kwargs)


def _make_hedge(kwargs: Dict[str, Any]) -> HedgeTrade:
    """快速构造 HedgeTrade。"""
    return HedgeTrade(**kwargs)


TEST_CASES: List[Dict[str, Any]] = [
    {
        "id": "TC01",
        "name": "卖出看涨期权 + 宽基 ETF 现货对冲（未提供对冲代码 → 无效对冲）",
        "scenario": "典型短 call 业务，交易台买入沪深 300 ETF 做 Delta 对冲，但未填写 ETF 代码，系统按最保守方式判定对冲无效。",
        "client": {
            "contract_type": "call_option",
            "direction": "short",
            "notional": 10000.0,
            "underlying_type": "index_component",
            "underlying_name": "沪深300指数",
            "underlying_code": "000300.SH",
            "option_type": "call_option",
            "premium_rate": 5.0,
            "option_delta": -0.72,
            "stress_loss": 200.0,
            "expected_yield": 0.08,
            "term_days": 180,
        },
        "hedges": [
            {
                "tool_type": "etf",
                "direction": "long",
                "notional": 9000.0,
                "underlying_type": "index_component",
                "underlying_name": "沪深300ETF",
                "is_broad_based_etf": True,
                # 故意不填 underlying_code（前端实际传空字符串），使有效对冲判定失败
                "underlying_code": "",
                "cash_spent": 9000.0,
            },
        ],
    },
    {
        "id": "TC02",
        "name": "卖出看涨期权 + 沪深300 ETF 对冲（依赖 iFinD 价格相关性判定有效对冲）",
        "scenario": "与 TC01 类似，但填写了 ETF 代码 510300.SH。标的不完全相同，系统将通过 iFinD 获取 000300.SH 与 510300.SH 近一年收盘价并计算相关性，>=95% 且 Delta 比例 80%-125% 时达成有效对冲。",
        "client": {
            "contract_type": "call_option",
            "direction": "short",
            "notional": 10000.0,
            "underlying_type": "index_component",
            "underlying_name": "沪深300指数",
            "underlying_code": "000300.SH",
            "option_type": "call_option",
            "premium_rate": 5.0,
            "option_delta": -0.72,
            "stress_loss": 200.0,
            "expected_yield": 0.08,
            "term_days": 180,
        },
        "hedges": [
            {
                "tool_type": "etf",
                "direction": "long",
                "notional": 9000.0,
                "underlying_type": "index_component",
                "underlying_name": "沪深300ETF",
                "is_broad_based_etf": True,
                "underlying_code": "510300.SH",
                "cash_spent": 9000.0,
            },
        ],
        "ifind_trigger": ["get_underlying_price_series(000300.SH)", "get_underlying_price_series(510300.SH)", "calculate_correlation_between_price_series(...)"],
    },
    {
        "id": "TC03",
        "name": "买入看跌期权（无对冲，风险资本准备按 100% 计提）",
        "scenario": "券商买入看跌期权，支付权利金，方向性敞口为做空标的。无对冲时市场风险资本准备 = 权利金 × 100%。",
        "client": {
            "contract_type": "put_option",
            "direction": "buy",
            "notional": 10000.0,
            "underlying_type": "index_component",
            "underlying_name": "沪深300指数",
            "underlying_code": "000300.SH",
            "option_type": "put_option",
            "premium_rate": 3.0,
            "option_delta": -0.50,
            "expected_yield": 0.05,
            "term_days": 90,
        },
        "hedges": [],
    },
    {
        "id": "TC04",
        "name": "收益互换（非全额保证金 + 境内个股）+ 个股现货对冲（公司约束阻断）",
        "scenario": "保留原个股收益互换样例，用于验证两层约束：监管上触发非全额保证金境内个股互换的市场风险加倍及信用风险；公司当前又禁止个股现货对冲，因此即使标的一致也不能认定为有效对冲。",
        "client": {
            "contract_type": "equity_swap",
            "direction": "short",
            "notional": 20000.0,
            "underlying_type": "general_stock",
            "underlying_name": "贵州茅台",
            "underlying_code": "600519.SH",
            "margin_rate": 10.0,
            "expected_yield": 0.06,
            "term_days": 365,
        },
        "hedges": [
            {
                "tool_type": "stock",
                "direction": "long",
                "notional": 18000.0,
                "stock_type": "general_stock",
                "underlying_type": "general_stock",
                "underlying_name": "贵州茅台",
                "underlying_code": "600519.SH",
                "cash_spent": 18000.0,
            },
        ],
    },
    {
        "id": "TC05",
        "name": "收益互换（全额保证金 + 指数成分股 → 无惩罚，信用风险为 0）",
        "scenario": "客户以 100% 保证金做指数收益互换，无信用风险资本准备，市场风险按正常比例计提。",
        "client": {
            "contract_type": "equity_swap",
            "direction": "short",
            "notional": 20000.0,
            "underlying_type": "index_component",
            "underlying_name": "沪深300指数",
            "underlying_code": "000300.SH",
            "margin_rate": 100.0,
            "expected_yield": 0.06,
            "term_days": 365,
        },
        "hedges": [
            {
                "tool_type": "etf",
                "direction": "long",
                "notional": 18000.0,
                "underlying_type": "index_component",
                "underlying_name": "沪深300ETF",
                "is_broad_based_etf": True,
                "underlying_code": "510300.SH",
                "cash_spent": 18000.0,
            },
        ],
    },
    {
        "id": "TC06",
        "name": "固定收益凭证 + 股票/ETF 组合（本体为零、独立头寸计提并触发公司约束）",
        "scenario": "保留原60天固定收益凭证及股票/ETF配置。固定收益凭证本体不计权益衍生品市场风险，但配置头寸不能随本体归零：ETF独立计提，个股工具还会触发公司禁止个股现货对冲的约束。",
        "client": {
            "contract_type": "income_certificate",
            "direction": "short",
            "notional": 50000.0,
            "underlying_type": "general_stock",
            "underlying_name": "平安银行",
            "underlying_code": "000001.SZ",
            "funds_raised": 50000.0,
            "stress_loss": None,
            "expected_yield": 0.04,
            "term_days": 60,
        },
        "hedges": [
            {
                "tool_type": "stock",
                "direction": "long",
                "notional": 30000.0,
                "stock_type": "general_stock",
                "underlying_type": "general_stock",
                "underlying_name": "一般上市公司股票",
                "underlying_code": "000001.SZ",
            },
            {
                "tool_type": "etf",
                "direction": "long",
                "notional": 20000.0,
                "underlying_type": "index_component",
                "underlying_name": "沪深300ETF",
                "is_broad_based_etf": True,
                "underlying_code": "510300.SH",
                "cash_spent": 20000.0,
            },
        ],
    },
    {
        "id": "TC07",
        "name": "浮动收益凭证（含内嵌期权）+ 股指期货对冲（达成有效对冲）",
        "scenario": "浮动收益凭证内嵌期权结构视同卖出场外期权（券商在标的上行时亏损），交易台用股指期货多头对冲内嵌期权风险。内嵌期权默认 Delta = -0.5×N，对冲多头 Delta = +N，比例恰为 100%，标的一致（000300.SH），达成有效对冲。",
        "client": {
            "contract_type": "income_certificate",
            "direction": "short",
            "notional": 50000.0,
            "underlying_type": "index_component",
            "underlying_name": "沪深300指数",
            "underlying_code": "000300.SH",
            "funds_raised": 50000.0,
            "has_embedded_option": True,
            "embedded_option_notional": 50000.0,
            "stress_loss": 300.0,
            "expected_yield": 0.05,
            "term_days": 90,
        },
        "hedges": [
            {
                "tool_type": "futures",
                "direction": "long",
                "notional": 25000.0,
                "underlying_name": "沪深300股指期货",
                "underlying_code": "000300.SH",
                "futures_margin": 3000.0,
            },
        ],
    },
    {
        "id": "TC08",
        "name": "卖出看涨期权 + 场内期权对冲（依赖 iFinD 获取实时 Greeks）",
        "scenario": "重点测试 iFinD 场内期权 Greeks 接口。卖出 50ETF 看涨期权，交易台买入 50ETF 场内看涨期权对冲。填写场内期权合约编码后，系统通过 iFinD 获取实时 Delta 值替代手动输入。",
        "client": {
            "contract_type": "call_option",
            "direction": "short",
            "notional": 10000.0,
            "underlying_type": "index_component",
            "underlying_name": "上证50ETF",
            "underlying_code": "510050.SH",
            "option_type": "call_option",
            "premium_rate": 5.0,
            "option_delta": -0.72,
            "stress_loss": 200.0,
            "expected_yield": 0.08,
            "term_days": 180,
        },
        "hedges": [
            {
                "tool_type": "onsite_option",
                "direction": "long",
                "notional": 9000.0,
                "option_type": "call_option",
                "option_delta": 0.80,
                "option_premium": 180.0,
                "tool_code": "10011855",
                "underlying_name": "50ETF 场内看涨期权",
                "underlying_code": "510050.SH",
            },
        ],
        "ifind_trigger": ["get_onsite_option_greeks(10011855, 'delta')"],
    },
    {
        "id": "TC09",
        "name": "卖出看涨期权 + 股指期货同标的对冲（直接判定有效对冲，无需 iFinD 相关性）",
        "scenario": "股指期货标的代码与客户合约标的代码完全一致（均为 000300.SH），系统直接判定标的一致，不触发 iFinD 相关性查询。",
        "client": {
            "contract_type": "call_option",
            "direction": "short",
            "notional": 10000.0,
            "underlying_type": "index_component",
            "underlying_name": "沪深300指数",
            "underlying_code": "000300.SH",
            "option_type": "call_option",
            "premium_rate": 5.0,
            "option_delta": -0.72,
            "stress_loss": 200.0,
            "expected_yield": 0.08,
            "term_days": 180,
        },
        "hedges": [
            {
                "tool_type": "futures",
                "direction": "long",
                "notional": 9000.0,
                "future_delta": 1.0,
                "underlying_name": "沪深300股指期货",
                "underlying_code": "000300.SH",
                "futures_margin": 1080.0,
            },
        ],
    },
    {
        "id": "TC10",
        "name": "买入看跌期权 + 场内看涨期权对冲（iFinD Greeks 实时 Delta）",
        "scenario": "买入 50ETF 看跌期权（负 Delta 敞口），交易台买入 50ETF 场内看涨期权（正 Delta）对冲。系统优先通过 iFinD 获取场内期权实时 Delta 系数。",
        "client": {
            "contract_type": "put_option",
            "direction": "buy",
            "notional": 10000.0,
            "underlying_type": "index_component",
            "underlying_name": "上证50ETF",
            "underlying_code": "510050.SH",
            "option_type": "put_option",
            "premium_rate": 3.0,
            "option_delta": -0.50,
            "expected_yield": 0.05,
            "term_days": 90,
        },
        "hedges": [
            {
                "tool_type": "onsite_option",
                "direction": "long",
                "notional": 8000.0,
                "option_type": "call_option",
                "option_delta": 0.45,
                "option_premium": 160.0,
                "tool_code": "10011855",
                "underlying_name": "50ETF 场内看涨期权",
                "underlying_code": "510050.SH",
            },
        ],
        "ifind_trigger": ["get_onsite_option_greeks(10011855, 'delta')"],
    },
    {
        "id": "TC11",
        "name": "卖出看涨期权 + 场内期权对冲（iFinD Greeks 获取失败，回退到手动 Delta）",
        "scenario": "填写了无效场内期权合约编码，iFinD 无法返回有效 Greeks，系统回退到交易台手动输入的 option_delta 进行有效对冲判定。",
        "client": {
            "contract_type": "call_option",
            "direction": "short",
            "notional": 10000.0,
            "underlying_type": "index_component",
            "underlying_name": "上证50ETF",
            "underlying_code": "510050.SH",
            "option_type": "call_option",
            "premium_rate": 5.0,
            "option_delta": -0.72,
            "stress_loss": 200.0,
            "expected_yield": 0.08,
            "term_days": 180,
        },
        "hedges": [
            {
                "tool_type": "onsite_option",
                "direction": "long",
                "notional": 9000.0,
                "option_type": "call_option",
                "option_delta": 0.80,
                "option_premium": 180.0,
                "tool_code": "INVALID_OPTION",
                "underlying_name": "50ETF 场内看涨期权（无效代码）",
                "underlying_code": "510050.SH",
            },
        ],
        "ifind_trigger": ["get_onsite_option_greeks(INVALID_OPTION, 'delta') -> None -> fallback"],
    },
]


# ============================================================
# Markdown 生成
# ============================================================

# 字段名 → 中文
FIELD_CN: Dict[str, str] = {
    "contract_type": "合约类型",
    "direction": "方向",
    "expected_yield": "预期年化收益率",
    "notional": "名义本金",
    "option_delta": "期权Delta",
    "option_type": "期权类型",
    "premium_rate": "权利金率",
    "stress_loss": "压力损失",
    "term_days": "期限/天",
    "underlying_code": "标的代码",
    "underlying_name": "标的名称",
    "underlying_type": "标的类型",
    "margin_rate": "保证金率",
    "cash_spent": "现金支出",
    "tool_type": "工具类型",
    "futures_margin": "期货保证金",
    "stock_type": "股票类型",
    "option_premium": "期权权利金",
    "tool_code": "工具代码",
    "funds_raised": "募集资金",
    "future_delta": "期货Delta",
}

# 值 → 中文（不含 direction，因为根据上下文不同）
VALUE_CN: Dict[str, str] = {
    "call_option": "看涨期权",
    "put_option": "看跌期权",
    "equity_swap": "收益互换",
    "income_certificate": "收益凭证",
    "index_component": "指数成分",
    "general_stock": "一般个股",
    "etf": "ETF",
    "futures": "期货",
    "stock": "股票",
    "onsite_option": "场内期权",
    "safe": "安全",
    "danger": "危险",
}

# direction 值 → 中文，按产品类型区分
# 期权/收益凭证的 short/buy；对冲工具的 long/short；互换的 short
DIRECTION_CN_CLIENT: Dict[str, str] = {
    "short": "卖出 / 做空",
    "buy": "买入 / 做多",
}
DIRECTION_CN_EQUITY_SWAP: Dict[str, str] = {
    "short": "空头 / 卖出",
}
DIRECTION_CN_HEDGE: Dict[str, str] = {
    "long": "多头 / 买入",
    "short": "空头 / 卖出",
}


def _translate_direction(value: str, contract_type: str = "", is_hedge: bool = False) -> str:
    """按产品类型和对冲/合约角色翻译 direction 值。"""
    if is_hedge:
        return DIRECTION_CN_HEDGE.get(value, value)
    if contract_type == "equity_swap":
        return DIRECTION_CN_EQUITY_SWAP.get(value, value)
    return DIRECTION_CN_CLIENT.get(value, value)


def _dict_to_md_table(
    d: Dict[str, Any],
    contract_type: str = "",
    is_hedge: bool = False,
    header: str = "字段 | 值",
    align: str = "--- | ---",
) -> str:
    """将字典格式化为两列 markdown 表格，字段名和值均附加中文翻译。"""
    lines = [header, align]
    items = sorted(d.items()) if isinstance(d, dict) else list(d.items())
    for k, v in items:
        # 字段名翻译
        k_cn = FIELD_CN.get(k, "")
        k_display = f"{k}（{k_cn}）" if k_cn else k
        # 值翻译
        display_raw = v if v is not None else "（未填写）"
        # 空字符串不翻译
        if isinstance(display_raw, str) and display_raw.strip() == "":
            display = "（空）"
        elif isinstance(display_raw, str) and display_raw != "（未填写）":
            # 优先用上下文相关的 direction 翻译
            if k == "direction":
                cn = _translate_direction(str(v), contract_type, is_hedge)
                display = f"{v}（{cn}）" if cn else str(v)
            else:
                cn = VALUE_CN.get(str(v), "")
                display = f"{v}（{cn}）" if cn else str(v)
        else:
            # 数值或 None
            display = str(v) if v is not None else "（未填写）"
        lines.append(f"{k_display} | {display}")
    return "\n".join(lines)


def _fmt_status(s: str) -> str:
    """状态值附加中文翻译。"""
    return f"{s}（{VALUE_CN.get(s, s)}）"


def _fmt_money(x: float) -> str:
    return f"{x:,.2f} 万元"


def _fmt_pct(x: float | None) -> str:
    # 新后端对无经济含义的性价比返回 None；兼容旧版 999 哨兵。
    if x is None or abs(x - 999.0) < 1e-6:
        return "不适用"
    return f"{x:.4%}"


def _fmt_ratio(x: float | None) -> str:
    if x is None or abs(x - 999.0) < 1e-6:
        return "不适用"
    return f"{x:.4f} 元/元"


def generate_markdown() -> str:
    lines = [
        "# 场外衍生品风控影响测算 — 典型测试样例",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> iFinD 终端状态：{'可用（已登录）' if IFIND_AVAILABLE else '不可用（已使用 Mock 数据模拟）'}",
        "> 公司基准参数来源：[backend/config.py](file:///e:/Desktop/risk_cal2/backend/config.py)",
        "",
        "## 说明",
        "",
        "以下样例覆盖三种主要业务类型（场外期权、收益互换、收益凭证）及关键边界条件，包括：",
        "- 有效对冲 / 无效对冲判定；",
        "- 收益互换的惩罚条件（非全额保证金 + 境内个股）；",
        "- 收益凭证固定型 / 浮动型（内嵌期权）区别；",
        "- 需要调用 iFinD 数据的价格相关性与场内期权 Greeks 场景。",
        "",
        "每个样例包含：业务场景、完整输入参数（模块 A + 模块 B）、模型输出三层指标、关键判断说明。",
        "输出单位为**万元**，百分比为**小数形式**（如 0.08 = 8%）。",
        "",
        "---",
        "",
    ]

    for case in TEST_CASES:
        result = analyze_contract(
            _make_contract(case["client"]),
            [_make_hedge(h) for h in case["hedges"]],
        )

        lines.extend([
            f"## {case['id']}：{case['name']}",
            "",
            f"**业务场景**：{case['scenario']}",
            "",
        ])

        if case.get("ifind_trigger"):
            lines.extend([
                "**本用例触发的 iFinD 数据查询**：",
                "",
            ])
            for item in case["ifind_trigger"]:
                lines.append(f"- `{item}`")
            lines.append("")
            if not IFIND_AVAILABLE:
                lines.append(
                    "> ⚠️ 当前环境未检测到 iFinD 终端，上述查询已使用 Mock 数据返回高相关性 / 默认 Greeks。"
                    "实际在前端验证时，请确保 iFinD 已登录，结果可能因真实行情而略有差异。"
                )
                lines.append("")

        # 模块 A 输入
        lines.extend([
            "### 模块 A：客户端场外合约输入",
            "",
            _dict_to_md_table(case["client"], contract_type=case["client"].get("contract_type", "")),
            "",
        ])

        # 模块 B 输入
        lines.extend([
            "### 模块 B：交易端（对冲工具）输入",
            "",
        ])
        if case["hedges"]:
            for idx, hedge in enumerate(case["hedges"], 1):
                lines.extend([
                    f"#### 对冲工具 #{idx}",
                    "",
                    _dict_to_md_table(hedge, is_hedge=True),
                    "",
                ])
        else:
            lines.extend(["无对冲工具。", ""])

        # 输出
        effective, reason = result["is_effective_hedge"]
        lines.extend([
            "### 模型输出",
            "",
            "#### 第一层：现金流与资源消耗绝对值",
            "",
            "| 输出项 | 数值 | 说明 |",
            "|---|---|---|",
            f"| 首日净现金流 | {_fmt_money(result['net_day1_cash'])} | 合约端流入 - 交易端流出 |",
            f"| 新增风险资本准备 | {_fmt_money(result['new_risk_reserve'])} | 含市场风险 + 信用风险 |",
            f"| 新增未来 30 日现金净流出 | {_fmt_money(result['net_cof_change'])} | LCR 分母增量 |",
            f"| 新增表内外资产总额 | {_fmt_money(result['assets_change'])} | 杠杆率分母增量 |",
            f"| 净资本变动 | {_fmt_money(result['net_capital_change'])} | 保证金扣减 |",
            "",
            "#### 第二层：核心风控指标边际变动",
            "",
            "| 指标 | 原值 | 新值 | 变动 | 状态 | 监管红线 |",
            "|---|---|---|---|---|---|",
            f"| LCR | {_fmt_pct(result['lcr_old'])} | {_fmt_pct(result['lcr_new'])} | {result['lcr_change']:+.4%} | {_fmt_status(result['lcr_status'])} | ≥100% |",
            f"| NSFR | {_fmt_pct(result['nsfr_old'])} | {_fmt_pct(result['nsfr_new'])} | {result['nsfr_change']:+.4%} | {_fmt_status(result['nsfr_status'])} | ≥100% |",
            f"| 资本杠杆率 | {_fmt_pct(result['leverage_old'])} | {_fmt_pct(result['leverage_new'])} | {result['leverage_change']:+.4%} | {_fmt_status(result['leverage_status'])} | ≥8% |",
            f"| 风险覆盖率 | {_fmt_pct(result['risk_coverage_old'])} | {_fmt_pct(result['risk_coverage_new'])} | {result['risk_coverage_change']:+.4%} | {_fmt_status(result['risk_coverage_status'])} | ≥100% |",
            "",
            "#### 第三层：动态性价比指标",
            "",
            "| 指标 | 数值 | 说明 |",
            "|---|---|---|",
            f"| ROC 资本收益率 | {_fmt_ratio(result['roc'])} | 预期创收 / 新增风险资本准备 |",
            f"| RO-LCR 流动性创收率 | {_fmt_ratio(result['ro_lcr'])} | 预期创收 / max(0, ΔOutflow - ΔHQLA) |",
            f"| RO-NSFR 稳定资金创收率 | {_fmt_ratio(result['ro_nsfr'])} | 预期创收 / ΔRSF |",
            f"| 预期年化创收 | {_fmt_money(result['expected_income'])} | 名义本金 × 预期年化收益率 |",
            "",
            "#### 对冲有效性判定",
            "",
            f"- 是否达成有效对冲：{'是' if effective else '否'}",
        ])
        if reason:
            lines.append(f"- 原因：{reason}")
        lines.append("")

        # 关键判断说明
        lines.extend([
            "### 关键判断与说明",
            "",
            _explain_case(case, result),
            "",
            "---",
            "",
        ])

    lines.extend([
        "## 附录：公司基准参数（config.py）",
        "",
        "| 参数 | 数值（万元） |",
        "|---|---|",
        f"| HQLA_base（优质流动性资产基数） | {DEFAULT_CONFIG['firm']['HQLA_base'] / 10000:,.2f} |",
        f"| LCR_COF_base（LCR现金流出基数） | {DEFAULT_CONFIG['firm']['LCR_COF_base'] / 10000:,.2f} |",
        f"| ASF_base（可用稳定资金基数） | {DEFAULT_CONFIG['firm']['ASF_base'] / 10000:,.2f} |",
        f"| RSF_base（所需稳定资金基数） | {DEFAULT_CONFIG['firm']['RSF_base'] / 10000:,.2f} |",
        f"| net_capital_base（净资本基数） | {DEFAULT_CONFIG['firm']['net_capital_base'] / 10000:,.2f} |",
        f"| total_risk_reserve_base（风险资本准备总额基数） | {DEFAULT_CONFIG['firm']['total_risk_reserve_base'] / 10000:,.2f} |",
        f"| on_off_balance_total_asset_base（表内外资产总额基数） | {DEFAULT_CONFIG['firm']['on_off_balance_total_asset_base'] / 10000:,.2f} |",
        f"| classification_factor（分类评价系数 k_class） | {DEFAULT_CONFIG['firm']['classification_factor']} |",
        f"| asf_rating_factor（ASF评级系数） | {DEFAULT_CONFIG['firm']['asf_rating_factor']} |",
        "",
    ])

    return "\n".join(lines)


def _explain_case(case: Dict[str, Any], result: Dict[str, Any]) -> str:
    """根据用例与结果生成关键判断说明。"""
    client = case["client"]
    ct = client["contract_type"]
    direction = client["direction"]
    notional = client["notional"]
    effective, reason = result["is_effective_hedge"]
    notes = []

    # 1. 有效对冲
    if effective:
        notes.append("- 已达成监管有效对冲，市场风险资本准备按 **5%** 计提。")
    else:
        notes.append(f"- 未达成有效对冲：{reason}")
        if ct in ("call_option", "put_option"):
            notes.append("- 场外期权按单边敞口计提市场风险资本准备：卖出 **30%**，买入 **100%**。")

    # 2. 收益互换惩罚
    if ct == "equity_swap":
        margin_rate = client.get("margin_rate")
        is_full = margin_rate is not None and abs(margin_rate - 100.0) < 0.001
        is_stock = client["underlying_type"] != "index_component"
        if not is_full and is_stock:
            notes.append("- 触发收益互换惩罚条件：非全额保证金 + 境内个股，市场风险资本准备 **加倍**。")
            notes.append("- 同时计提信用风险资本准备 = 名义本金 × 5%。")
        elif not is_full:
            notes.append("- 非全额保证金，计提信用风险资本准备 = 名义本金 × 5%，但无个股惩罚加倍。")
        else:
            notes.append("- 全额保证金，信用风险资本准备为 0。")

    # 3. 收益凭证
    if ct == "income_certificate":
        if not client.get("has_embedded_option", False):
            notes.append("- 固定收益凭证：本金负债部分不计提市场/信用风险资本准备。")
            notes.append("- 固定收益凭证本体 Delta 为0；配置的交易端头寸仍按各自类别独立计提。")
        else:
            notes.append("- 浮动收益凭证：内嵌衍生品视同卖出场外期权，按 S_short × 30% 计提市场风险资本准备。")
            embedded_notional = client.get("embedded_option_notional") or notional
            s_short = max(5 * client["stress_loss"], embedded_notional * 0.005)
            notes.append(f"- S_short = max(5×{client['stress_loss']}, {embedded_notional}×0.5%) = {s_short:.2f} 万元。")
            notes.append("- 浮动收益凭证默认 Delta 按卖出场外期权口径为负（视同卖出看涨期权），可参与有效对冲判定。")

    # 4. 期权 S_short
    if ct in ("call_option", "put_option") and direction == "short":
        loss = client.get("stress_loss") or 0.0
        s_short = max(5 * loss, notional * 0.005)
        notes.append(f"- 卖出期权投资规模 S_short = max(5×{loss}, {notional}×0.5%) = {s_short:.2f} 万元。")
        notes.append(f"- LCR毛流出增量按期末名义金额 = N × 20% = {notional * 0.20:.2f} 万元；不使用S_short。")

    # 5. 净资本变动（保证金扣减）
    nc_change = result["net_capital_change"]
    if abs(nc_change) > 0.01:
        notes.append(f"- 净资本变动 {nc_change:,.2f} 万元，来源于期货/卖出期权保证金占用扣减。")
    else:
        notes.append("- 净资本变动为 0，本组合无额外保证金扣减。")

    # 5.5 对冲端 LCR 资金流出（问题6 修复）
    has_futures = any(h.get("tool_type") == "futures" for h in case["hedges"])
    has_onsite_short = any(
        h.get("tool_type") == "onsite_option" and h.get("direction") == "short"
        for h in case["hedges"]
    )
    has_otc_back = any(h.get("tool_type") == "otc_hedge" for h in case["hedges"])
    if has_futures or has_onsite_short or has_otc_back:
        detail = []
        if has_futures:
            detail.append("股指期货按名义价值 × 20% 计提资金流出")
        if has_onsite_short:
            detail.append("卖出场内期权按 Delta金额 × 15% 作为最终填列额，不再乘20%")
        if has_otc_back:
            detail.append("场外背对背互换按名义本金 × 0.2% 计提资金流出")
        notes.append("- 交易端衍生品对冲已按 LCR 口径计入自营资金流出（" + "；".join(detail) + "）。")

    # 6. iFinD 提示
    if case.get("ifind_trigger"):
        notes.append("- 本用例依赖 iFinD 数据：")
        for item in case["ifind_trigger"]:
            notes.append(f"  - `{item}`")
        if any("onsite_option_greeks" in str(item) for item in case["ifind_trigger"]):
            notes.append("- 场内期权 Greeks：系统优先尝试 iFinD 实时 Delta；若查询失败或返回异常，自动回退到手动输入的 option_delta。")

    return "\n".join(notes) if notes else "- 常规计算，无特殊边界触发。"


def main():
    md = generate_markdown()
    output_path = os.path.join(_project_root, "test_cases.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"已生成测试样例文档：{output_path}")
    print(f"iFinD 状态：{'可用' if IFIND_AVAILABLE else 'Mock'}")


if __name__ == "__main__":
    main()
