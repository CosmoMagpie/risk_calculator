# ============================================================
# backend/config.py - 公司基数和监管参数（默认参数配置与监管系数常量）
# ============================================================

# ===================== 默认参数配置 =====================
# 【设计思路】将可调参数集中管理，三层嵌套：client（客户端）/ trade（交易端）/ firm（公司基准）
#           后续函数中若用户未显式指定某参数，就回退到这里取默认值，实现"约定优于配置"
DEFAULT_CONFIG = {

    # ---------- client：客户端业务的默认参数 ----------
    "client": {
        "swap_margin_rate": 0.10,           # 收益互换默认保证金比例 10%（监管允许最低保证金）
        "option_premium_rate": 0.05,        # 场外期权默认权利金/名义本金比例 5%
        "atm_option_delta": 0.50,           # 平值期权默认Delta（ATM = At-The-Money）
        "equity_swap_delta": 1.0,           # 互换默认Delta 100%（互换相当于直接持有标的）
        "income_certificate_delta": 0.0,     # 收益凭证默认Delta 0%（本质是固收产品，无权益敞口）
        "income_certificate_term": 1.0,            # 收益凭证默认期限（年）
        "income_certificate_rate": 0.04,           # 收益凭证默认票面利率 4%
    },

    # ---------- trade：交易端对冲工具的默认参数 ----------
    "trade": {
        "futures_margin_rate": 0.12,        # 期货默认保证金比例 12%（中金所股指期货约12%）
        "future_delta": 1.0,               # 期货默认Delta值（股指期货Delta≈1）
        "private_fund_cash_rate": 1.0,      # 私募基金申购资金占用比例 100%
        "etf_cash_rate": 1.0,               # ETF现货资金消耗比例 100%（全款买入）
        "onsite_option_premium_rate": 0.02, # 场内期权默认权利金比例 2%
        "onsite_option_margin_rate": 0.15,  # 场内卖出期权默认保证金比例 15%
        "otc_option_premium_rate": 0.03,    # 场外期权（背对背平盘）默认权利金比例 3%
        "atm_option_delta": 0.5,            # 场内外期权默认Delta值（平值期权≈0.5）
        "onsite_option_stress_loss": 0.0,   # 卖出压力测试最大损失（万元），默认0=未设置
    },

    # ---------- firm：公司当前基准数据（用于计算增量影响） ----------
    # 【设计思路】模型不计算绝对值，而是计算"增量"——即新业务对现有指标的影响
    #           先存储公司当前的各项基数，再叠加新业务变动，最后对比前后差异
    "firm": {
        # 风险资本准备分类调整系数：连续三年A类AA级以上0.4、连续三年A类0.6、
        # A类0.8、B类0.9、C类1.0、D类2.0。
        "classification_factor": 1.0,
        # 表内外资产总额分类调整系数：连续三年A类AA级以上0.7、连续三年A类0.9、其余1.0。
        "asset_adjustment_factor": 1.0,
        # 仅适用于剩余期限6个月（含）至1年的借款和负债；不适用于期权权利金。
        "asf_rating_factor": 0.00,
        # 新业务预计净收入进入“近三个年度平均净收入”的识别权重：当前快照0，
        # 已进入1/2/3个年度分别为1/3、2/3、1。用于预计操作风险资本准备。
        "operational_risk_recognition_weight": 0.0,
        "HQLA_base": 11_881_000_000,            # 当前优质流动性资产总额（元）—— LCR分子
        "LCR_COF_base": 7_977_000_000,          # 兼容字段：当前未来30日现金净流出（元）
        # LCR净流出具有75%流入上限，精确边际测算必须分别保存流出和流入。
        # 默认暂将历史净流出全部视为毛流出、毛流入为0（审慎口径）。
        "LCR_outflow_base": 7_977_000_000,
        "LCR_inflow_base": 0,
        # 已计入/原始可计入HQLA的指数成份股和宽基股票指数ETF金额（元）。
        # 用于执行该类资产不超过HQLA总额15%的上限；缺少公司数据时默认0。
        "HQLA_equity_raw_base": 0,
        "ASF_base": 30_532_000_000,             # 当前可用稳定资金总额（元）—— NSFR分子
        "RSF_base": 21_644_000_000,             # 当前所需稳定资金总额（元）—— NSFR分母
        "net_capital_base": 16_496_000_000,     # 当前净资本（元）—— 风险覆盖率分子
        "core_net_capital_base": 16_496_000_000,# 当前核心净资本（元）—— 资本杠杆率分子
        "total_risk_reserve_base": 740_000_000, # 当前各项风险资本准备之和（元）—— 风险覆盖率分母
        "self_operated_equity_scale_base": 0,    # 当前自营权益类证券及其衍生品规模（元）
        "on_off_balance_total_asset_base": 300_000_000_000,  # 表内外资产总额（元）
    }
}  # 数据来自之前业务的excel表格


# ===================== 市场风险资本准备计提比例（RATES） =====================
# 各类资产的市场风险计提比例（根据证监会规定）
RATES = {
    "index_component": 0.08,      # 指数成分股 8%
    "general_stock": 0.25,        # 一般上市股票 25%
    "restricted_stock": 0.50,     # 流通受限股票 50%
    "other_stock": 0.80,          # 其他股票 80%
    "stock_index_future": 0.30,   # 股指期货 30%
    "equity_swap": 0.30,          # 权益互换 30%
    "equity_short_option": 0.30,  # 权益类卖出期权 30%
    "equity_long_option": 1.00,   # 权益类买入期权 100%
    "equity_index_fund": 0.05,    # 权益类指数基金（含ETF）5%
    "other_equity_fund": 0.10,    # 其他权益类基金10%
    "monetary_fund": 0.05,        # 货币基金 5%
    "interest_rate_bond_index_fund": 0.06, # 利率债指数基金 6%
    "other_non_equity_fund": 0.10,  # 其他非权益类基金
    "treasury_future_and_interest_rate_swap": 0.20, # 国债期货和利率互换 20%
    "single_product": 0.50,        # 单一产品 50%
    "bulk_commodity": 0.08,       # 大宗商品 8%
    "bulk_commodity_derivatives": 0.20,     # 大宗商品衍生品 20%
    "non_equity_short_option": 0.20,  # 非权益类卖出期权 20%
    "non_equity_long_option": 1.00,  # 非权益类买入期权 100%
}
