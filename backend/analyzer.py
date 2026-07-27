# ============================================================
# backend/analyzer.py - 主编排函数：串联所有子计算，输出完整指标变动报告
# ============================================================

from typing import Dict, Any, List

from .models.client_contract import OtcContract
from .models.hedge_trade import HedgeTrade
from .config import DEFAULT_CONFIG
from .calculators.hedge_validator import is_effective_hedge
from .calculators.risk_reserve import calc_total_risk_reserve
from .calculators.lcr import calc_lcr_impact
from .calculators.nsfr import calc_nsfr_impact


def analyze_contract(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, Any]:
    """
    主分析函数 —— 将以上所有子计算串联起来，输出完整的指标变动报告

    【数据流】
      输入：OtcContract（场外合约）+ [HedgeTrade, ...]（对冲工具列表）
      处理：计算现金流 → 对冲有效性 → 三项风险指标（风险覆盖率/LCR/NSFR）
      输出：一个字典，包含所有核心指标的"变动前 → 变动后"数据

    【单位转换说明】
      DEFAULT_CONFIG["firm"] 中的基准数据单位是"元"
      本函数中除法的 /10000 是将"元"转为"万元"
      而 calc_* 函数返回的值已经是"万元"
      所以最终计算时：基准(元)/10000(→万元) + 变动(万元) = 新的万元值

    Returns:
        Dict[str, Any]: 包含以下键的完整分析结果字典
    """
    # ===== 步骤1：现金流计算 =====
    otc_cash = otc.get_otc_cash_inflow()                              # 场外合约端现金净流入
    total_trade_cash = sum(h.get_trade_cash_outflow() for h in hedge_list)  # sum(生成器)：求和
    net_day1_cash = otc_cash - total_trade_cash                       # 净现金 = 合约端流入 - 对冲端流出
    expected_income = otc.get_expected_income()

    # ===== 步骤2：对冲有效性判断 =====
    is_effective = is_effective_hedge(otc, hedge_list)

    # ===== 步骤3：风险资本准备 =====
    new_risk_reserve = calc_total_risk_reserve(otc, hedge_list, is_effective[0])

    # ===== 步骤4：LCR影响 =====
    lcr = calc_lcr_impact(otc, hedge_list)

    # ===== 步骤5：NSFR影响 =====
    nsfr = calc_nsfr_impact(otc, hedge_list)

    # ===== 步骤6：表内外资产总额变动（简化：名义本金的10%）=====
    new_assets = otc.notional * 0.10 + sum(h.notional * 0.10 for h in hedge_list)

    # ===== 步骤7：计算三大指标的前后对比 =====

    # --- LCR ---
    # HQLA_new = 基准HQLA(元→万元) + 变动(万元)
    hqla_new = DEFAULT_CONFIG["firm"]["HQLA_base"] / 10000 + lcr["hqla_change"]
    cof_new = DEFAULT_CONFIG["firm"]["LCR_COF_base"] / 10000 + lcr["net_cof_change"]
    lcr_new = hqla_new / cof_new if cof_new > 0 else 999  # 除零保护
    lcr_old = (DEFAULT_CONFIG["firm"]["HQLA_base"] / 10000) / (DEFAULT_CONFIG["firm"]["LCR_COF_base"] / 10000)

    # --- NSFR ---
    asf_new = DEFAULT_CONFIG["firm"]["ASF_base"] / 10000 + nsfr["asf_change"]
    rsf_new = DEFAULT_CONFIG["firm"]["RSF_base"] / 10000 + nsfr["rsf_change"]
    nsfr_new = asf_new / rsf_new if rsf_new > 0 else 999
    nsfr_old = (DEFAULT_CONFIG["firm"]["ASF_base"] / 10000) / (DEFAULT_CONFIG["firm"]["RSF_base"] / 10000)

    # --- 风险覆盖率 ---
    risk_reserve_new = DEFAULT_CONFIG["firm"]["total_risk_reserve_base"] / 10000 + new_risk_reserve
    risk_old = DEFAULT_CONFIG["firm"]["net_capital_base"] / 10000 / (DEFAULT_CONFIG["firm"]["total_risk_reserve_base"] / 10000)
    risk_new = DEFAULT_CONFIG["firm"]["net_capital_base"] / 10000 / risk_reserve_new if risk_reserve_new > 0 else 999

    # ===== 步骤8：组装返回结果 =====
    return {
        # 现金流与创收
        "net_day1_cash": net_day1_cash,              # 首日净现金流（万元）
        "expected_income": expected_income,           # 预期年化创收（万元）

        # 风险资本准备与表内外资产
        "new_risk_reserve": new_risk_reserve,         # 新增风险资本准备（万元）
        "new_assets": new_assets,                     # 新增表内外资产（万元）

        # LCR 指标
        "lcr_net_cof_change": lcr["net_cof_change"],  # LCR分母变动
        "lcr_old": lcr_old,                            # 业务前LCR
        "lcr_new": lcr_new,                            # 业务后LCR
        "lcr_change": lcr_new - lcr_old,              # LCR变动
        "lcr_status": "safe" if lcr_new >= 1.20 else "warning" if lcr_new >= 1.00 else "danger",

        # NSFR 指标
        "nsfr_old": nsfr_old,
        "nsfr_new": nsfr_new,
        "nsfr_change": nsfr_new - nsfr_old,
        "nsfr_status": "safe" if nsfr_new >= 1.20 else "warning" if nsfr_new >= 1.00 else "danger",

        # 风险覆盖率 指标
        "risk_coverage_old": risk_old,
        "risk_coverage_new": risk_new,
        "risk_coverage_change": risk_new - risk_old,
        "risk_coverage_status": "safe" if risk_new >= 1.20 else "warning" if risk_new >= 1.00 else "danger",

        # 性价比指标（创收 / 指标消耗）
        # RO_* = Return On *，衡量每消耗1单位指标能创造多少收入
        "ro_capital": expected_income / new_risk_reserve if new_risk_reserve > 0 else 999,
        "ro_assets": expected_income / new_assets if new_assets > 0 else 999,
        "ro_lcr": expected_income / abs(lcr["net_cof_change"]) if lcr["net_cof_change"] != 0 else 999,

        # 对冲有效性标记
        "is_effective_hedge": is_effective,
    }
