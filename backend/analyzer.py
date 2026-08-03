# ============================================================
# backend/analyzer.py - 主编排函数：串联所有子计算，输出完整指标变动报告
# ============================================================

from typing import Dict, Any, List

from .models.client_contract import OtcContract
from .models.hedge_trade import HedgeTrade
from .config import DEFAULT_CONFIG
from .calculators.hedge_validator import is_effective_hedge
from .calculators.risk_reserve import calc_total_risk_reserve, calc_self_operated_equity_scale
from .calculators.lcr import calc_lcr_impact
from .calculators.nsfr import calc_nsfr_impact
from .calculators.leverage import calc_leverage_impact
from .calculators.net_capital import calc_nc_impact
from .calculators.business_validator import validate_business_constraints


def analyze_contract(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, Any]:
    """
    主分析函数 —— 串联所有子计算，输出完整指标变动报告

    【数据流】
      输入：OtcContract（场外合约）+ [HedgeTrade, ...]（对冲工具列表）
      处理：现金流 → 对冲有效性 → 风险资本准备 → LCR/NSFR/资本杠杆率/风险覆盖率
      输出：三层指标体系（绝对值 / 边际变动 / 性价比）

    【单位转换说明】
      DEFAULT_CONFIG["firm"] 中的基准数据单位是"元"
      本函数中除法的 /10000 是将"元"转为"万元"
      而 calc_* 函数返回的值已经是"万元"
      所以最终计算时：基准(元)/10000(→万元) + 变动(万元) = 新的万元值

    输出对应 calculation.md 的三层结构：
      第一层 — 现金流与资源消耗绝对值：首日净现金流、新增风险资本准备、新增未来30日现金净流出
      第二层 — 核心风控指标边际变动：LCR、NSFR、资本杠杆率、风险覆盖率
      第三层 — 动态性价比指标：ROC、RO-LCR、RO-NSFR

    Returns:
        Dict[str, Any]: 包含所有核心指标及状态的完整分析结果字典
    """
    # ===== 步骤1：现金流计算 =====
    otc_cash = otc.get_otc_cash_inflow()                              # 场外合约端现金净流入
    total_trade_cash = sum(h.get_trade_cash_outflow() for h in hedge_list)  # sum(生成器)：求和
    net_day1_cash = otc_cash - total_trade_cash                       # 净现金 = 合约端流入 - 对冲端流出
    gross_expected_income = otc.get_expected_income()
    hedge_annual_cost = sum(
        h.notional * h.pass_through_fee / 100.0
        for h in hedge_list
        if h.tool_type == "otc_hedge" and h.pass_through_fee is not None
    )
    expected_income = gross_expected_income - hedge_annual_cost

    # ===== 步骤2：对冲有效性判断 =====
    business_constraints = validate_business_constraints(otc, hedge_list)
    if business_constraints["is_compliant"]:
        is_effective = is_effective_hedge(otc, hedge_list)
    else:
        is_effective = [
            False,
            "；".join(business_constraints["errors"]),
        ]

    # ===== 步骤3：风险资本准备 =====
    market_credit_risk_reserve = calc_total_risk_reserve(
        otc, hedge_list, is_effective[0]
    )
    operational_risk_reserve = (
        max(0.0, expected_income)
        * 0.18
        * DEFAULT_CONFIG["firm"].get("operational_risk_recognition_weight", 0.0)
        * DEFAULT_CONFIG["firm"]["classification_factor"]
    )
    new_risk_reserve = market_credit_risk_reserve + operational_risk_reserve

    # ===== 步骤3.5：净资本变动（保证金扣减） =====
    net_capital_change = calc_nc_impact(otc, hedge_list)
    equity_scale_change = calc_self_operated_equity_scale(otc, hedge_list)

    # ===== 步骤4：LCR影响 ====="
    lcr = calc_lcr_impact(otc, hedge_list)

    # ===== 步骤5：NSFR影响 =====
    nsfr = calc_nsfr_impact(otc, hedge_list)

    # ===== 步骤6：资本杠杆率影响 =====
    assets_change = calc_leverage_impact(otc, hedge_list)

    # ===== 步骤7：计算四大指标的前后对比 =====

    # --- LCR ---
    # HQLA_new = 基准HQLA(元→万元) + 变动(万元)
    hqla_new = DEFAULT_CONFIG["firm"]["HQLA_base"] / 10000 + lcr["hqla_change"]
    outflow_base = DEFAULT_CONFIG["firm"].get(
        "LCR_outflow_base", DEFAULT_CONFIG["firm"]["LCR_COF_base"]
    ) / 10000
    inflow_base = DEFAULT_CONFIG["firm"].get("LCR_inflow_base", 0.0) / 10000
    cof_base = outflow_base - min(inflow_base, 0.75 * outflow_base)
    cof_new = cof_base + lcr["net_cof_change"]
    lcr_new = hqla_new / cof_new if cof_new > 0 else 999  # 除零保护
    lcr_old = (DEFAULT_CONFIG["firm"]["HQLA_base"] / 10000) / cof_base

    # --- NSFR ---
    asf_new = DEFAULT_CONFIG["firm"]["ASF_base"] / 10000 + nsfr["asf_change"]
    rsf_new = DEFAULT_CONFIG["firm"]["RSF_base"] / 10000 + nsfr["rsf_change"]
    nsfr_new = asf_new / rsf_new if rsf_new > 0 else 999
    nsfr_old = (DEFAULT_CONFIG["firm"]["ASF_base"] / 10000) / (DEFAULT_CONFIG["firm"]["RSF_base"] / 10000)

    # --- 资本杠杆率 ---
    # 杠杆率 = 核心净资本 / 表内外资产总额 ≥ 8%
    # 分子口径与风险覆盖率保持一致：核心净资本需扣减期货（期权）保证金占用
    nc = DEFAULT_CONFIG["firm"]["net_capital_base"] / 10000
    nc_adjusted = nc + net_capital_change
    core_nc = DEFAULT_CONFIG["firm"].get(
        "core_net_capital_base", DEFAULT_CONFIG["firm"]["net_capital_base"]
    ) / 10000
    core_nc_adjusted = core_nc + net_capital_change
    ta_base = DEFAULT_CONFIG["firm"]["on_off_balance_total_asset_base"] / 10000
    leverage_old = core_nc / ta_base if ta_base > 0 else 999
    leverage_new = core_nc_adjusted / (ta_base + assets_change) if (ta_base + assets_change) > 0 else 999

    # --- 风险覆盖率 ---
    # 风险覆盖率 = (净资本 + Δ净资本) / (各项风险资本准备 + 新增风险资本准备)
    # 保证金占用会扣减净资本，因此分子需要加入 Δ净资本 调整
    risk_reserve_new = DEFAULT_CONFIG["firm"]["total_risk_reserve_base"] / 10000 + new_risk_reserve
    risk_old = nc / (DEFAULT_CONFIG["firm"]["total_risk_reserve_base"] / 10000)
    risk_new = nc_adjusted / risk_reserve_new if risk_reserve_new > 0 else 999
    equity_scale_base = DEFAULT_CONFIG["firm"].get(
        "self_operated_equity_scale_base", 0.0
    ) / 10000
    equity_scale_ratio_old = equity_scale_base / nc if nc > 0 else 999
    equity_scale_ratio_new = (
        (equity_scale_base + equity_scale_change) / nc_adjusted
        if nc_adjusted > 0
        else 999
    )

    # ===== 步骤8：组装返回结果（对应 calculation.md 三层结构）=====

    # --- 第一层：现金流与资源消耗绝对值 ---
    # 首日净现金流（合约端流入 - 交易端流出，万元）
    # 新增风险资本准备（万元）
    # 新增未来30日现金净流出（LCR分母变动，万元）

    # --- 第二层：核心风控指标边际变动 ---
    # LCR = HQLA / 未来30日现金净流出 ≥ 100%
    # NSFR = ASF / RSF ≥ 100%
    # 资本杠杆率 = 核心净资本 / 表内外资产总额 ≥ 8%
    # 风险覆盖率 = 净资本 / 各项风险资本准备之和 ≥ 100%

    # --- 第三层：动态性价比指标 ---
    # ROC  = 预期创收 / 新增风险资本准备
    # RO-LCR = 预期创收 / max(0, ΔOutflow - ΔHQLA)
    # RO-NSFR = 预期创收 / ΔRSF

    # 流动性净消耗（ΔOutflow - ΔHQLA），正值=流动性净消耗，负值=流动性改善
    net_liquidity_drain = lcr["net_cof_change"] - lcr["hqla_change"]

    return {
        # ===== 第一层：现金流与资源消耗绝对值 =====
        "net_day1_cash": net_day1_cash,           # 首日净现金流（万元）
        "new_risk_reserve": new_risk_reserve,      # 新增风险资本准备（万元）
        "market_credit_risk_reserve": market_credit_risk_reserve,
        "operational_risk_reserve": operational_risk_reserve,
        "net_cof_change": lcr["net_cof_change"],  # 新增未来30日现金净流出（万元）
        "gross_outflow_change": lcr["gross_outflow_change"],
        "hqla_change": lcr["hqla_change"],
        "asf_change": nsfr["asf_change"],
        "rsf_change": nsfr["rsf_change"],
        "assets_change": assets_change,            # 新增表内外资产总额（万元，用于杠杆率分母）
        "net_capital_change": net_capital_change,  # 净资本变动（万元，保证金扣减）
        "equity_scale_change": equity_scale_change,

        # ===== 第二层：核心风控指标边际变动 =====
        # -- LCR --
        "lcr_old": lcr_old,
        "lcr_new": lcr_new,
        "lcr_change": lcr_new - lcr_old,
        "lcr_status": "safe" if lcr_new >= 1.20 else "warning" if lcr_new >= 1.00 else "danger",

        # -- NSFR --
        "nsfr_old": nsfr_old,
        "nsfr_new": nsfr_new,
        "nsfr_change": nsfr_new - nsfr_old,
        "nsfr_status": "safe" if nsfr_new >= 1.20 else "warning" if nsfr_new >= 1.00 else "danger",

        # -- 资本杠杆率 --
        "leverage_old": leverage_old,
        "leverage_new": leverage_new,
        "leverage_change": leverage_new - leverage_old,
        "leverage_status": "safe" if leverage_new >= 0.096 else "warning" if leverage_new >= 0.08 else "danger",

        # -- 风险覆盖率 --
        "risk_coverage_old": risk_old,
        "risk_coverage_new": risk_new,
        "risk_coverage_change": risk_new - risk_old,
        "risk_coverage_status": "safe" if risk_new >= 1.20 else "warning" if risk_new >= 1.00 else "danger",
        "equity_scale_ratio_old": equity_scale_ratio_old,
        "equity_scale_ratio_new": equity_scale_ratio_new,
        "equity_scale_ratio_change": equity_scale_ratio_new - equity_scale_ratio_old,
        "equity_scale_status": "safe" if equity_scale_ratio_new <= 0.80 else "warning" if equity_scale_ratio_new <= 1.00 else "danger",

        # ===== 第三层：动态性价比指标 =====
        "gross_expected_income": gross_expected_income,
        "hedge_annual_cost": hedge_annual_cost,
        "expected_income": expected_income,        # 净预期年化创收（万元）
        "roc": expected_income / new_risk_reserve if new_risk_reserve > 0 else None,
        "ro_lcr": expected_income / net_liquidity_drain if net_liquidity_drain > 0 else None,
        "ro_nsfr": expected_income / nsfr["rsf_change"] if nsfr["rsf_change"] > 0 else None,

        # 对冲有效性标记
        "is_effective_hedge": is_effective,
        "business_constraints": business_constraints,
    }
