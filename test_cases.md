# 风控模型回归测试案例

> 生成日期：2026-08-03；全程离线，不调用iFinD。

## 公司基准与口径

- 风险资本准备分类系数：1.0
- 表内外资产分类系数：1.0
- LCR毛流出/毛流入基数（元）：7,977,000,000 / 0
- 场外卖出期权：风险资本/表内外资产用压力规模；LCR用名义×20%；NSFR用名义×12%。
- 卖出场内期权：LCR和NSFR均以Delta金额×15%作为最终填列额，不再重复乘20%/12%。
- 用于对冲权益互换的证券不计入HQLA；宽基ETF仍计入NSFR和市场风险资本准备。

## TC01 卖出场外看涨期权（无对冲）

### 输入

- 客户端：`OtcContract(contract_type='call_option', direction='short', notional=10000, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', underlying_instrument='index', option_type='call_option', premium_rate=5.0, total_premium_amount=None, single_premium_amount=None, contract_multiplier=None, contract_size=None, exercise_price=None, option_delta=-0.5, option_margin_amount=None, option_margin_rate=None, stress_loss=200, margin_rate=None, margin_amount=None, equity_swap_delta=None, funds_raised=None, income_certificate_delta=None, has_embedded_option=False, embedded_option_notional=None, margin_liability_term_days=None, expected_yield=0.08, expiry_date=None, begin_date=None, term_days=180)`
- 对冲端：`[]`

### 输出

| 指标 | 结果 |
|---|---:|
| `net_day1_cash` | 500.000000 |
| `new_risk_reserve` | 300.000000 |
| `market_credit_risk_reserve` | 300.000000 |
| `operational_risk_reserve` | 0.000000 |
| `hqla_change` | 500.000000 |
| `gross_outflow_change` | 2,000.000000 |
| `net_cof_change` | 2,000.000000 |
| `asf_change` | 0.000000 |
| `rsf_change` | 1,200.000000 |
| `assets_change` | 1,500.000000 |
| `net_capital_change` | 0.000000 |
| `equity_scale_change` | 1000 |
| `lcr_new` | 1.486307 |
| `nsfr_new` | 1.409863 |
| `leverage_new` | 0.054984 |
| `risk_coverage_new` | 22.201884 |
| `equity_scale_ratio_new` | 0.000606 |
| `expected_income` | 800.000000 |
| `roc` | 2.666667 |
| `ro_lcr` | 0.533333 |
| `ro_nsfr` | 0.666667 |

- 监管有效对冲：`[False, '未填写对冲工具标的代码，不满足有效对冲条件']`
- 公司业务范围：`{'is_compliant': True, 'errors': [], 'warnings': []}`

## TC02 卖出场外看涨期权（宽基ETF有效对冲）

### 输入

- 客户端：`OtcContract(contract_type='call_option', direction='short', notional=10000, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', underlying_instrument='index', option_type='call_option', premium_rate=5.0, total_premium_amount=None, single_premium_amount=None, contract_multiplier=None, contract_size=None, exercise_price=None, option_delta=-0.5, option_margin_amount=None, option_margin_rate=None, stress_loss=200, margin_rate=None, margin_amount=None, equity_swap_delta=None, funds_raised=None, income_certificate_delta=None, has_embedded_option=False, embedded_option_notional=None, margin_liability_term_days=None, expected_yield=0.08, expiry_date=None, begin_date=None, term_days=180)`
- 对冲端：`[HedgeTrade(tool_type='etf', direction='long', notional=5000, tool_code=None, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', cash_spent=None, is_broad_based_etf=True, stock_type=None, futures_margin=None, futures_margin_rate=None, future_type=None, future_delta=None, option_premium=None, option_type=None, option_strike_price=None, option_start_date=None, option_expiry_date=None, option_delta=None, option_margin=None, option_margin_rate=None, otc_payment=None, pass_through_fee=None, otc_hedge_contract_type=None, otc_stress_loss=None, subscription_amount=None, fund_structure=None, fund_lookthrough_risk_rate=None, asset_maturity_days=None, fund_delta=None)]`

### 输出

| 指标 | 结果 |
|---|---:|
| `net_day1_cash` | -4,500.000000 |
| `new_risk_reserve` | 300.000000 |
| `market_credit_risk_reserve` | 300.000000 |
| `operational_risk_reserve` | 0.000000 |
| `hqla_change` | -2,000.000000 |
| `gross_outflow_change` | 2,000.000000 |
| `net_cof_change` | 2,000.000000 |
| `asf_change` | 0.000000 |
| `rsf_change` | 1,700.000000 |
| `assets_change` | 1,500.000000 |
| `net_capital_change` | 0.000000 |
| `equity_scale_change` | 6000 |
| `lcr_new` | 1.483181 |
| `nsfr_new` | 1.409538 |
| `leverage_new` | 0.054984 |
| `risk_coverage_new` | 22.201884 |
| `equity_scale_ratio_new` | 0.003637 |
| `expected_income` | 800.000000 |
| `roc` | 2.666667 |
| `ro_lcr` | 0.200000 |
| `ro_nsfr` | 0.470588 |

- 监管有效对冲：`[True, None]`
- 公司业务范围：`{'is_compliant': True, 'errors': [], 'warnings': []}`

## TC03 境内个股收益互换（非全额保证金、期货对冲未认定有效）

### 输入

- 客户端：`OtcContract(contract_type='equity_swap', direction='short', notional=20000, underlying_type='general_stock', underlying_name=None, underlying_code='600519.SH', underlying_market='CN', underlying_instrument='stock', option_type=None, premium_rate=None, total_premium_amount=None, single_premium_amount=None, contract_multiplier=None, contract_size=None, exercise_price=None, option_delta=None, option_margin_amount=None, option_margin_rate=None, stress_loss=None, margin_rate=10.0, margin_amount=None, equity_swap_delta=-1.0, funds_raised=None, income_certificate_delta=None, has_embedded_option=False, embedded_option_notional=None, margin_liability_term_days=None, expected_yield=0.06, expiry_date=None, begin_date=None, term_days=365)`
- 对冲端：`[HedgeTrade(tool_type='futures', direction='long', notional=18000, tool_code=None, underlying_type='index_component', underlying_name=None, underlying_code='', underlying_market='CN', cash_spent=None, is_broad_based_etf=False, stock_type=None, futures_margin=2160, futures_margin_rate=None, future_type=None, future_delta=1.0, option_premium=None, option_type=None, option_strike_price=None, option_start_date=None, option_expiry_date=None, option_delta=None, option_margin=None, option_margin_rate=None, otc_payment=None, pass_through_fee=None, otc_hedge_contract_type=None, otc_stress_loss=None, subscription_amount=None, fund_structure=None, fund_lookthrough_risk_rate=None, asset_maturity_days=None, fund_delta=None)]`

### 输出

| 指标 | 结果 |
|---|---:|
| `net_day1_cash` | -160.000000 |
| `new_risk_reserve` | 3,010.000000 |
| `market_credit_risk_reserve` | 3,010.000000 |
| `operational_risk_reserve` | 0.000000 |
| `hqla_change` | -160.000000 |
| `gross_outflow_change` | 3,640.000000 |
| `net_cof_change` | 3,640.000000 |
| `asf_change` | 0.000000 |
| `rsf_change` | 2,360.000000 |
| `assets_change` | 8,700.000000 |
| `net_capital_change` | -2,160.000000 |
| `equity_scale_change` | 4,700.000000 |
| `lcr_new` | 1.482442 |
| `nsfr_new` | 1.409109 |
| `leverage_new` | 0.054899 |
| `risk_coverage_new` | 21.392546 |
| `equity_scale_ratio_new` | 0.002853 |
| `expected_income` | 1,200.000000 |
| `roc` | 0.398671 |
| `ro_lcr` | 0.315789 |
| `ro_nsfr` | 0.508475 |

- 监管有效对冲：`[False, '对冲工具#1未填写标的代码，不满足有效对冲条件']`
- 公司业务范围：`{'is_compliant': True, 'errors': [], 'warnings': []}`

## TC04 指数收益互换（宽基ETF同标的有效对冲）

### 输入

- 客户端：`OtcContract(contract_type='equity_swap', direction='long', notional=10000, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', underlying_instrument='index', option_type=None, premium_rate=None, total_premium_amount=None, single_premium_amount=None, contract_multiplier=None, contract_size=None, exercise_price=None, option_delta=None, option_margin_amount=None, option_margin_rate=None, stress_loss=None, margin_rate=10.0, margin_amount=None, equity_swap_delta=1.0, funds_raised=None, income_certificate_delta=None, has_embedded_option=False, embedded_option_notional=None, margin_liability_term_days=None, expected_yield=0.06, expiry_date=None, begin_date=None, term_days=365)`
- 对冲端：`[HedgeTrade(tool_type='etf', direction='short', notional=10000, tool_code=None, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', cash_spent=None, is_broad_based_etf=True, stock_type=None, futures_margin=None, futures_margin_rate=None, future_type=None, future_delta=None, option_premium=None, option_type=None, option_strike_price=None, option_start_date=None, option_expiry_date=None, option_delta=None, option_margin=None, option_margin_rate=None, otc_payment=None, pass_through_fee=None, otc_hedge_contract_type=None, otc_stress_loss=None, subscription_amount=None, fund_structure=None, fund_lookthrough_risk_rate=None, asset_maturity_days=None, fund_delta=None)]`

### 输出

| 指标 | 结果 |
|---|---:|
| `net_day1_cash` | 11,000.000000 |
| `new_risk_reserve` | 1,050.000000 |
| `market_credit_risk_reserve` | 1,050.000000 |
| `operational_risk_reserve` | 0.000000 |
| `hqla_change` | 11,000.000000 |
| `gross_outflow_change` | 20.000000 |
| `net_cof_change` | 20.000000 |
| `asf_change` | 0.000000 |
| `rsf_change` | 1,100.000000 |
| `assets_change` | 12,000.000000 |
| `net_capital_change` | 0.000000 |
| `equity_scale_change` | 11,000.000000 |
| `lcr_new` | 1.503159 |
| `nsfr_new` | 1.409928 |
| `leverage_new` | 0.054965 |
| `risk_coverage_new` | 21.980013 |
| `equity_scale_ratio_new` | 0.006668 |
| `expected_income` | 600.000000 |
| `roc` | 0.571429 |
| `ro_lcr` | 不适用 |
| `ro_nsfr` | 0.545455 |

- 监管有效对冲：`[True, None]`
- 公司业务范围：`{'is_compliant': True, 'errors': [], 'warnings': []}`

## TC05 固定收益凭证（无内嵌衍生品）

### 输入

- 客户端：`OtcContract(contract_type='income_certificate', direction='issue', notional=50000, underlying_type='index_component', underlying_name=None, underlying_code=None, underlying_market='CN', underlying_instrument=None, option_type=None, premium_rate=None, total_premium_amount=None, single_premium_amount=None, contract_multiplier=None, contract_size=None, exercise_price=None, option_delta=None, option_margin_amount=None, option_margin_rate=None, stress_loss=None, margin_rate=None, margin_amount=None, equity_swap_delta=None, funds_raised=50000, income_certificate_delta=None, has_embedded_option=False, embedded_option_notional=None, margin_liability_term_days=None, expected_yield=0.04, expiry_date=None, begin_date=None, term_days=400)`
- 对冲端：`[]`

### 输出

| 指标 | 结果 |
|---|---:|
| `net_day1_cash` | 50000 |
| `new_risk_reserve` | 0.000000 |
| `market_credit_risk_reserve` | 0.000000 |
| `operational_risk_reserve` | 0.000000 |
| `hqla_change` | 50,000.000000 |
| `gross_outflow_change` | 0.000000 |
| `net_cof_change` | 0.000000 |
| `asf_change` | 50000 |
| `rsf_change` | 0.000000 |
| `assets_change` | 50,000.000000 |
| `net_capital_change` | 0.000000 |
| `equity_scale_change` | 0.000000 |
| `lcr_new` | 1.552087 |
| `nsfr_new` | 1.433746 |
| `leverage_new` | 0.054895 |
| `risk_coverage_new` | 22.291892 |
| `equity_scale_ratio_new` | 0.000000 |
| `expected_income` | 2,000.000000 |
| `roc` | 不适用 |
| `ro_lcr` | 不适用 |
| `ro_nsfr` | 不适用 |

- 监管有效对冲：`[False, '未填写场外合约标的代码，不满足有效对冲条件']`
- 公司业务范围：`{'is_compliant': True, 'errors': [], 'warnings': []}`

## TC06 浮动收益凭证（内嵌期权+期货有效对冲）

### 输入

- 客户端：`OtcContract(contract_type='income_certificate', direction='issue', notional=50000, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', underlying_instrument='index', option_type=None, premium_rate=None, total_premium_amount=None, single_premium_amount=None, contract_multiplier=None, contract_size=None, exercise_price=None, option_delta=-0.5, option_margin_amount=None, option_margin_rate=None, stress_loss=300, margin_rate=None, margin_amount=None, equity_swap_delta=None, funds_raised=50000, income_certificate_delta=None, has_embedded_option=True, embedded_option_notional=50000, margin_liability_term_days=None, expected_yield=0.05, expiry_date=None, begin_date=None, term_days=270)`
- 对冲端：`[HedgeTrade(tool_type='futures', direction='long', notional=25000, tool_code=None, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', cash_spent=None, is_broad_based_etf=False, stock_type=None, futures_margin=3000, futures_margin_rate=None, future_type=None, future_delta=1.0, option_premium=None, option_type=None, option_strike_price=None, option_start_date=None, option_expiry_date=None, option_delta=None, option_margin=None, option_margin_rate=None, otc_payment=None, pass_through_fee=None, otc_hedge_contract_type=None, otc_stress_loss=None, subscription_amount=None, fund_structure=None, fund_lookthrough_risk_rate=None, asset_maturity_days=None, fund_delta=None)]`

### 输出

| 指标 | 结果 |
|---|---:|
| `net_day1_cash` | 47000 |
| `new_risk_reserve` | 262.500000 |
| `market_credit_risk_reserve` | 262.500000 |
| `operational_risk_reserve` | 0.000000 |
| `hqla_change` | 47,000.000000 |
| `gross_outflow_change` | 15,000.000000 |
| `net_cof_change` | 15,000.000000 |
| `asf_change` | 0.000000 |
| `rsf_change` | 9,000.000000 |
| `assets_change` | 55,250.000000 |
| `net_capital_change` | -3,000.000000 |
| `equity_scale_change` | 5,250.000000 |
| `lcr_new` | 1.519749 |
| `nsfr_new` | 1.404804 |
| `leverage_new` | 0.054786 |
| `risk_coverage_new` | 22.172698 |
| `equity_scale_ratio_new` | 0.003188 |
| `expected_income` | 2,500.000000 |
| `roc` | 9.523810 |
| `ro_lcr` | 不适用 |
| `ro_nsfr` | 0.277778 |

- 监管有效对冲：`[True, None]`
- 公司业务范围：`{'is_compliant': True, 'errors': [], 'warnings': []}`

## TC07 场外期权+卖出场内期权（验证15%不重复折算）

### 输入

- 客户端：`OtcContract(contract_type='call_option', direction='buy', notional=1000, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', underlying_instrument='index', option_type='call_option', premium_rate=None, total_premium_amount=30, single_premium_amount=None, contract_multiplier=None, contract_size=None, exercise_price=None, option_delta=0.5, option_margin_amount=None, option_margin_rate=None, stress_loss=None, margin_rate=None, margin_amount=None, equity_swap_delta=None, funds_raised=None, income_certificate_delta=None, has_embedded_option=False, embedded_option_notional=None, margin_liability_term_days=None, expected_yield=0.08, expiry_date=None, begin_date=None, term_days=90)`
- 对冲端：`[HedgeTrade(tool_type='onsite_option', direction='short', notional=1000, tool_code=None, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', cash_spent=None, is_broad_based_etf=False, stock_type=None, futures_margin=None, futures_margin_rate=None, future_type=None, future_delta=None, option_premium=20, option_type='call_option', option_strike_price=None, option_start_date=None, option_expiry_date=None, option_delta=-0.5, option_margin=150, option_margin_rate=None, otc_payment=None, pass_through_fee=None, otc_hedge_contract_type=None, otc_stress_loss=None, subscription_amount=None, fund_structure=None, fund_lookthrough_risk_rate=None, asset_maturity_days=None, fund_delta=None)]`

### 输出

| 指标 | 结果 |
|---|---:|
| `net_day1_cash` | -10 |
| `new_risk_reserve` | 5.250000 |
| `market_credit_risk_reserve` | 5.250000 |
| `operational_risk_reserve` | 0.000000 |
| `hqla_change` | -10.000000 |
| `gross_outflow_change` | 75.000000 |
| `net_cof_change` | 75.000000 |
| `asf_change` | 0.000000 |
| `rsf_change` | 75.000000 |
| `assets_change` | 95.000000 |
| `net_capital_change` | -150.000000 |
| `equity_scale_change` | 105.000000 |
| `lcr_new` | 1.489254 |
| `nsfr_new` | 1.410596 |
| `leverage_new` | 0.054981 |
| `risk_coverage_new` | 22.288284 |
| `equity_scale_ratio_new` | 0.000064 |
| `expected_income` | 80.000000 |
| `roc` | 15.238095 |
| `ro_lcr` | 0.941176 |
| `ro_nsfr` | 1.066667 |

- 监管有效对冲：`[True, None]`
- 公司业务范围：`{'is_compliant': True, 'errors': [], 'warnings': []}`

## TC08 收益互换+一对一SPV申购（未提供组合Delta）

### 输入

- 客户端：`OtcContract(contract_type='equity_swap', direction='short', notional=20000, underlying_type='index_component', underlying_name=None, underlying_code='000300.SH', underlying_market='CN', underlying_instrument='index', option_type=None, premium_rate=None, total_premium_amount=None, single_premium_amount=None, contract_multiplier=None, contract_size=None, exercise_price=None, option_delta=None, option_margin_amount=None, option_margin_rate=None, stress_loss=None, margin_rate=25.0, margin_amount=None, equity_swap_delta=-1.0, funds_raised=None, income_certificate_delta=None, has_embedded_option=False, embedded_option_notional=None, margin_liability_term_days=None, expected_yield=0.06, expiry_date=None, begin_date=None, term_days=365)`
- 对冲端：`[HedgeTrade(tool_type='private_fund', direction='long', notional=14000, tool_code=None, underlying_type=None, underlying_name=None, underlying_code='000300.SH', underlying_market='CN', cash_spent=None, is_broad_based_etf=False, stock_type=None, futures_margin=None, futures_margin_rate=None, future_type=None, future_delta=None, option_premium=None, option_type=None, option_strike_price=None, option_start_date=None, option_expiry_date=None, option_delta=None, option_margin=None, option_margin_rate=None, otc_payment=None, pass_through_fee=None, otc_hedge_contract_type=None, otc_stress_loss=None, subscription_amount=14000, fund_structure='single_product', fund_lookthrough_risk_rate=None, asset_maturity_days=None, fund_delta=None)]`

### 输出

| 指标 | 结果 |
|---|---:|
| `net_day1_cash` | -9,000.000000 |
| `new_risk_reserve` | 8,600.000000 |
| `market_credit_risk_reserve` | 8,600.000000 |
| `operational_risk_reserve` | 0.000000 |
| `hqla_change` | -9,000.000000 |
| `gross_outflow_change` | 40.000000 |
| `net_cof_change` | 40.000000 |
| `asf_change` | 0.000000 |
| `rsf_change` | 14,200.000000 |
| `assets_change` | 7,000.000000 |
| `net_capital_change` | 0.000000 |
| `equity_scale_change` | 2,000.000000 |
| `lcr_new` | 1.478050 |
| `nsfr_new` | 1.401450 |
| `leverage_new` | 0.054974 |
| `risk_coverage_new` | 19.970944 |
| `equity_scale_ratio_new` | 0.001212 |
| `expected_income` | 1,200.000000 |
| `roc` | 0.139535 |
| `ro_lcr` | 0.132743 |
| `ro_nsfr` | 0.084507 |

- 监管有效对冲：`[False, 'Delta 敞口数据缺失，不满足有效对冲条件']`
- 公司业务范围：`{'is_compliant': True, 'errors': [], 'warnings': []}`
