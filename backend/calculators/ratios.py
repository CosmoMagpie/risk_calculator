# ============================================================
# backend/calculators/ratios.py - 监管系数常量表
# ============================================================
# 各类资产的市场风险计提比例、RSF系数、HQLA折算率等
# 依据：《证券公司风险控制指标计算标准规定》
# ============================================================

# ===================== 市场风险资本准备计提比例 =====================
RATES = {
    "index_component": 0.08,      # 指数成分股 8%
    "general_stock": 0.25,        # 一般上市股票 25%
    "restricted_stock": 0.50,     # 流通受限股票 50%
    "other_stock": 0.80,          # 其他股票 80%
    "stock_index_future": 0.30,   # 股指期货 30%
    "equity_swap": 0.30,          # 权益互换 30%
    "equity_short_option": 0.30,  # 权益类卖出期权 30%
    "equtity_long_option": 1.00,  # 权益类买入期权 100%（注意拼写：equtity→equity）
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

# ===================== RSF 系数（所需稳定资金） =====================
# 依据：calculation.md 标的资产分类表
RSF_RATES = {
    # 现货端
    "index_component_stock": 0.30,       # 指数成分股（沪深300/中证500/上证180/深证100）
    "index_component_etf": 0.10,         # 宽基ETF
    "general_stock": 0.50,               # 一般上市公司股票 / 非宽基ETF
    "restricted_stock": 1.00,            # 流动受限股票
    "other_stock": 1.00,                 # 其他股票
    # 衍生品端
    "stock_index_future": 0.12,          # 场内股指期货（名义价值 × 12%）
    "onsite_short_option": 0.15 * 0.12,  # 场内卖出期权（Delta金额 × 15% × 12%）
    "otc_short_option": 0.12,            # 场外卖出期权（名义规模 × 12%）
    "equity_swap": 0.01,                 # 收益互换（名义本金 × 1%）
}

# ===================== HQLA 折算率（优质流动性资产） =====================
HQLA_DISCOUNT = {
    "index_component": 0.50,    # 指数成分股/宽基ETF：50%
    "general_stock": 0.00,      # 一般股票：0%
    "restricted_stock": 0.00,   # 流动受限股票：0%
    "other_stock": 0.00,        # 其他股票：0%
    "cash": 1.00,               # 现金：100%
}
