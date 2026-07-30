# ============================================================
# app.py - Streamlit 前端
# ============================================================
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
# app.py
from backend.models.client_contract import OtcContract
from backend.models.hedge_trade import HedgeTrade
from backend.analyzer import analyze_contract
from backend.config import DEFAULT_CONFIG

# ========== 中英文映射字典 ==========
CN_BUSINESS_TYPE = {"场外期权": "option", "收益互换": "equity_swap", "收益凭证": "income_certificate"}

CN_DIRECTION = {"买入": "long", "卖出": "short", "多头": "long", "空头": "short"}

# ==========标的中英文映射字典==========
UNDERLYING_TYPE_MAP = {
        "指数成分股": "index_component",
        "一般上市公司股票": "general_stock",
        "流动受限股票": "restricted_stock",
        "其他股票": "other_stock",
        "指数基金（含ETF）": "index_fund",
        "其他权益类基金": "other_equity_fund",
        "股指期货": "stock_index_future",
        "权益互换": "equity_swap",
        "权益类卖出期权": "equity_short_option",
        "权益类买入期权": "equity_long_option",
        "货币基金": "monetary_fund",
        "利率债指数基金": "interest_rate_bond_index_fund",
        "其他非权益类基金": "other_non_equity_fund",
        "国债期货": "treasury_future",
        "利率互换": "interest_rate_swap",
        "单一产品": "single_product",
        "集合及信托": "collection_and_trust",
        "大宗商品现货（含黄金）": "bulk_commodity",
        "大宗商品期货": "bulk_commodity_future",
        "非权益类卖出期权": "non_equity_short_option",
        "非权益类买入期权": "non_equity_long_option",
    }

EQUITY_TYPES = {
    "index_component",        # 指数成分股
    "general_stock",          # 一般上市公司股票
    "restricted_stock",       # 流动受限股票
    "other_stock",            # 其他股票
    "index_fund",             # 指数基金（含ETF）
    "other_equity_fund",      # 其他权益类基金
    "stock_index_future",     # 股指期货
    "equity_swap",            # 权益互换
    "equity_short_option",    # 权益类卖出期权
    "equity_long_option",     # 权益类买入期权
}

TOOL_TYPE_MAP = {
                "指数成分股": "index_component",
                "一般上市公司股票": "general_stock",
                "流动受限股票": "restricted_stock",
                "其他股票": "other_stock",
                "ETF": "etf",
                "其他指数基金": "other_index_fund",
                "其他权益类基金": "other_equity_fund",
                "货币基金": "monetary_fund",
                "利率债指数基金": "interest_rate_bond_index_fund",
                "其他非权益类基金": "other_non_equity_fund",
                "股指期货": "stock_index_future",
                "国债期货": "treasury_future",
                "大宗商品期货": "bulk_commodity_future",
                "权益互换": "equity_swap",
                "利率互换": "interest_rate_swap",
                "场内期权": "onsite_option",
                "场外期权": "otc_option",
                "单一产品（私募基金）": "single_product(private_fund)",
                "集合及信托": "collection_and_trust",
                "大宗商品现货（含黄金）": "bulk_commodity",
            }

BROAD_BASED = ['000010.SH', '000300.SH', '000905.SH', '399330.SZ', '000852.SZ', '000510.SH', '000010.SH', '000016.SH', '000688.SH']

# ========== 公共工具函数 ==========

def validate_option_delta(direction, option_type_str, delta_value):
    """
    校验期权 Delta 符号是否正确。
    
    参数:
        direction: 交易方向，如 "买入"/"卖出"/"多头"/"空头"
        option_type_str: 期权类型，如 "看涨期权"/"看跌期权"
        delta_value: Delta 数值（系数，如 0.50 表示 50%）
    
    返回:
        (is_valid: bool, message: str)
    """
    if delta_value is None or delta_value == 0:
        return False, "**Delta 值不能为 0**，请填写有效的 Delta 金额。"
    
    # 定义期望的 Delta 符号映射
    expected_sign_map = {
        ("买入", "看涨期权（call）"): "正",
        ("卖出", "看涨期权（call）"): "负",
        ("买入", "看跌期权（put）"): "负",
        ("卖出", "看跌期权（put）"): "正",
    }
    expected = expected_sign_map.get((direction, option_type_str), "未知")
    
    is_positive = delta_value > 0
    if expected == "正" and not is_positive:
        return False, f"**Delta 符号警告**：{direction}{option_type_str}的 Delta 应为 **正数**，当前为负数。请检查是否填错。"
    elif expected == "负" and is_positive:
        return False, f"**Delta 符号警告**：{direction}{option_type_str}的 Delta 应为 **负数**，当前为正数。请检查是否填错。"
    else:
        return True, "Delta 符号正确"


st.set_page_config(page_title="场外衍生品风控影响测算系统", layout="wide")
st.title("场外衍生品业务风控影响测算系统")
st.markdown(
    """
    <style>
    /* 主标题 */
    .stApp h1 {
        color: #10098F;
        font-size: 42px;
        font-weight: 700;
    }
    /* 二级标题 */
    .stApp h2 {
        color: #2c3e50;
        font-size: 30px;
        font-weight: 600;
    }
    /* 三级标题 */
    .stApp h3 {
        color: #34495e;
        font-size: 22px;
        font-weight: 500;
        padding-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ========== 侧边栏 ==========
with st.sidebar:
    st.header("公司基准参数")
    st.session_state['firm_params'] = {
        "HQLA_base": st.number_input("当前HQLA总额（万元）", value=DEFAULT_CONFIG["firm"]["HQLA_base"]/10000, step=10000.00),
        "LCR_COF_base": st.number_input("当前LCR未来30日净流出（万元）", value=DEFAULT_CONFIG["firm"]["LCR_COF_base"]/10000, step=10000.00),
        "ASF_base": st.number_input("当前ASF总额（万元）", value=DEFAULT_CONFIG["firm"]["ASF_base"]/10000, step=10000.00),
        "RSF_base": st.number_input("当前RSF总额（万元）", value=DEFAULT_CONFIG["firm"]["RSF_base"]/10000, step=10000.00),
        "net_capital_base": st.number_input("当前净资本（万元）", value=DEFAULT_CONFIG["firm"]["net_capital_base"]/10000, step=10000.00),
        "total_risk_reserve_base": st.number_input("当前风险资本准备（万元）", value=DEFAULT_CONFIG["firm"]["total_risk_reserve_base"]/10000, step=10000.00),
        "classification_factor": st.selectbox("分类评价系数", [0.4, 0.6, 0.8, 0.9, 1.0, 2.0], index=4),
    }

# ========== 主区域 ==========
tab1, tab2, tab3 = st.tabs(["📝 模块A：场外合约端", "🔄 模块B：交易端（对冲工具）", "📈 结果展示"])

with tab1:
    st.header("场外合约端业务要素")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("三大业务（场外期权、收益互换、收益凭证）通用输入字段")

        # 1.业务类型(contract_type)
        contract_type_input = st.selectbox("业务类型", ["场外期权", "收益互换", "收益凭证"])
        contract_type = CN_BUSINESS_TYPE[contract_type_input]
        # 2.交易方向(direction)
        direction_input = st.selectbox("交易方向（作为交易商）", ["买入", "卖出"] if contract_type != "equity_swap" else ["多头", "空头"],
                                       help="空头 = 浮动利率支付方（支付浮动收益，收取固定收益），多头 = 浮动利率收取方（收取浮动收益，支付固定收益）" if contract_type == "equity_swap" else "买入/卖出期权")
        direction = CN_DIRECTION[direction_input]
        # 3.名义本金/发行规模(notional)
        notional = st.number_input("名义本金/发行规模（万元）", min_value=0.0, value=1000.0, step=100.0)

        # 4.标的资产信息（标的名称、标的代码）用于有效对冲判定：填写后系统将通过代码判定标的一致性；留空则按最保守方式估算
        st.divider()
        st.caption("标的资产信息用于有效对冲判定：填写后系统将通过代码判定标的一致性；留空则按最保守方式估算。")
        st.caption("如若考虑对冲情况，业务底层资产的代码和分类是必填项，否则无法计算对冲有效性。")
        col_code1, col_code2 = st.columns(2)
        with col_code1:
            with st.container():
                st.caption("标的iFinD代码务必填写完整，如：000852.SH") # 可以来一个外部查询链接
                # 4.1 标的代码(underlying_code)
                underlying_code = st.text_input("标的iFinD代码", placeholder="如：159716.SZ", key="client_ul_code")

                # 4.2 标的类型(underlying_type)
                chinese_options = list(UNDERLYING_TYPE_MAP.keys())
                selected_chinese = st.selectbox("标的分类",options=chinese_options,index=0, key="client_ul_type")
                underlying_type = UNDERLYING_TYPE_MAP[selected_chinese]
            
        with col_code2:
            with st.container():
                st.space()
                # 4.3 标的名称(underlying_name)
                underlying_name = st.text_input("标的名称", placeholder="如：沪深300指数", key="client_ul_name")
                # 4.4 标的所在交易市场(underlying_market)
                market_options = {"A股（默认）": "CN", "美股": "US", "港股": "HK", "英股": "EN", "其他": "Other"}
                selected_market_label = st.selectbox("标的所在交易市场",options=list(market_options.keys()),index=0, key="client_ul_market")
                underlying_market = market_options[selected_market_label]

        # 5.是否为权益类业务
        is_equity = underlying_type in EQUITY_TYPES

        # 6.预期收益
        st.divider()
        st.caption("提示：预期年化收益率与合约期限应根据业务需求合理设置")
        expected_yield = st.number_input("预期年化收益率（%）", min_value=0.0, value=8.0, step=0.5) / 100.0

        # 7.期限
        st.divider()
        st.caption("请设置合约期限")
        use_date_picker = st.checkbox("手动选择到期日和起始日", value=False, help="勾选后，可通过日期选择器精确设置起止日期；不勾选则直接输入天数")
        if use_date_picker:
            begin_date = st.date_input("起始日", value=datetime.now().date(), key="begin_date")
            min_expiry = begin_date + timedelta(days=1) if begin_date is not None else datetime.now().date() + timedelta(days=1)
            expiry_date = st.date_input("到期日", value=datetime.now().date() + timedelta(days=90), key="expiry_date", min_value=min_expiry)
            # 显示计算出的期限
            term_days = 90
            if begin_date is not None and expiry_date is not None:
                term_days = (expiry_date - begin_date).days
                if term_days > 0:
                    st.info(f"合约期限：**{term_days} 天**（约 {term_days/30:.1f} 个月）")
                else:
                    st.warning("到期日必须晚于起始日，请重新选择")
            else:
                st.caption("📅 请选择起始日和到期日")
        else:
            term_days = st.number_input("合约期限（天）", min_value=1, value=90, step=1,help="输入合约存续期天数")
            begin_date = None
            expiry_date = None
            
            # 显示天数对应的约几个月
            st.caption(f" 约 {term_days/30:.1f} 个月")
    
    with col2:
        st.subheader("单一业务专用输入字段")

        if contract_type == "option":
            # 期权自有属性
            # 1.期权类型(option_type)
            client_option_type = st.selectbox("期权类型", ["看涨期权（call）", "看跌期权（put）"])
            if client_option_type == "看涨期权（call）":
                option_type = "call"
            else:
                option_type = "put"

            # 2.权利金/期权费(premium_rate, total_premium_amount, single_premium_amount)
            premium_input_method = st.radio("权利金/期权费录入方式（请选择一种）", options=["按比例","按权利金总额","按单笔期权权利金额与合约份数"], index=0, horizontal=True)

            premium_rate = None
            total_premium_amount = None
            single_premium_amount = None
            if premium_input_method == "按比例":
                suggested_rate = DEFAULT_CONFIG['client']['default_option_premium_rate']  # 默认5% 期权费
                premium_rate = st.number_input("权利金占名义本金比例（%）", min_value=0.0, value=5.0, step=0.5)
                premium_rate /= 100.0
            elif premium_input_method == "按业务总额":
                total_premium_amount = st.number_input("权利金总额（万元）", min_value=0.0, value=0.0, step=10.0)
            else:
                single_premium_amount = st.number_input("单笔权利金（万元）", min_value=0.0, value=0.0, step=10.0)


            # 3.合约乘数(contract_multiplier)
            st.divider()
            suggested_multiplier = DEFAULT_CONFIG['client']['default_option_contract_multiplier']
            contract_multiplier = st.number_input("合约乘数（万元/点）", min_value=1, value=suggested_multiplier, step=1)

            # 4.合约份数(contract_size)
            suggested_contract_size = DEFAULT_CONFIG['client']['default_option_contract_size']
            contract_size = st.number_input("合约份数（张）", value=suggested_contract_size, min_value=1, step=1)

            # 补充期权费相关信息
            if premium_rate is not None:
                total_premium_amount = notional * premium_rate
                single_premium_amount = total_premium_amount / contract_size
            elif total_premium_amount is not None:
                single_premium_amount = total_premium_amount / contract_size
                premium_rate = total_premium_amount / notional
            elif single_premium_amount is not None:
                total_premium_amount = single_premium_amount * contract_size
                premium_rate = total_premium_amount / notional

            # 5.行权价(exercise_price)
            suggested_exercise_price = float(DEFAULT_CONFIG['client']['default_option_exercise_price'])
            exercise_price = st.number_input("行权价（元）", value=suggested_exercise_price, min_value=0.0, step=1.0)
            
            # 6.期权Delta(option_delta)
            suggested_delta = DEFAULT_CONFIG['client']['atm_option_delta']
            if client_option_type == "看跌期权（call）" and direction == "买入":
                suggested_delta = -suggested_delta
            elif client_option_type == "看涨期权（put）" and direction == "卖出":
                suggested_delta = -suggested_delta
            # 买入看涨 / 卖出看跌 保持正数
            option_delta = st.number_input("Delta（系数，如 0.50=50%）", value = suggested_delta, key="client_option_delta", 
                                           help="期权价格对标的资产价格的敏感度，非百分比。买入看涨/卖出看跌应为正，买入看跌/卖出看涨应为负。如 50% Delta 请填入 0.50")
            # Delta 符号校验
            delta_valid, delta_warning_msg = validate_option_delta(direction_input, client_option_type, option_delta)
            expected_sign_map = {
                ("买入", "看涨期权（call）"): "正",
                ("卖出", "看涨期权（call）"): "负",
                ("买入", "看跌期权（put）"): "负",
                ("卖出", "看跌期权（put）"): "正",
            }
            expected = expected_sign_map.get((direction_input, client_option_type), "未知")
            if delta_valid:
                st.success(delta_warning_msg)
            else:
                st.error(delta_warning_msg)
            st.caption(f"提示：{direction_input}{client_option_type}的 Delta 期望符号为 **{expected}**")

            # 7.保证金/预付金(option_margin_amount, option_margin_rate)
            option_margin_rate = None
            option_margin_amount = None
            if direction == "short":
                st.divider()
                option_margin_input_method = st.radio("保证金/预付金录入方式（请选择一种）", options=["按比例","按保证金总额"], index=0, horizontal=True)
                if option_margin_input_method == "按比例":
                    suggested_option_margin_rate = DEFAULT_CONFIG['client']['default_option_margin_rate'] * 100  # 12% 为默认值
                    option_margin_rate = st.number_input("保证金占名义本金比例（%）", min_value=0.0, value=suggested_option_margin_rate, step=0.5)
                    option_margin_rate /= 100.0
                else:
                    option_margin_amount = st.number_input("保证金总额（万元）", min_value=0.0, value=0.0, step=10.0)
                if option_margin_rate is not None:
                    option_margin_amount = notional * option_margin_rate
                elif option_margin_amount is not None:
                    option_margin_rate = option_margin_amount / notional
            
        
        elif contract_type == "equity_swap":
            equity_swap_margin_amount = None
            equity_swap_margin_rate = None
            swap_margin_input_method = st.radio("保证金/预付金录入方式（请选择一种）", options=["按比例","按保证金总额"], index=0, horizontal=True)
            if swap_margin_input_method == "按比例":
                suggested_equity_swap_margin_rate = DEFAULT_CONFIG['client']['default_equity_swap_margin_rate'] * 100  # 10% 为默认值
                equity_swap_margin_rate = st.number_input("保证金/预付金比例（%）", min_value=0.0, max_value=100.0, value=suggested_equity_swap_margin_rate, step=0.5) / 100.0
            else:
                equity_swap_margin_amount = st.number_input("保证金总额（万元）", min_value=0.0, value=0.0, step=10.0)
            equity_swap_delta = st.number_input("收益互换 Delta（系数，如 1.00=100%）", min_value=0.0, max_value=100.0, value=1, step=0.5)
        
        else:  # 收益凭证
            funds_raised = st.number_input("募集资金总额（万元）", value=notional, step=100.0)
            is_float_income = st.checkbox("是否浮动收益")
            if is_float_income:
                income_certificate_delta = st.number_input("收益凭证 Delta（系数，如 1.00=100%）", min_value=0.0, max_value=100.0, value=1, step=0.5)
            else:
                income_certificate_delta = 0.0

    
    st.session_state['client_params'] = {
    # ===== 基础信息 =====
    "contract_type": contract_type,          # "option" | "equity_swap" | "income_certificate"
    "direction": direction,                  # "short" | "long"
    "notional": notional,                    # 名义本金（万元）
    
    # ===== 标的资产信息 =====
    "underlying_type": underlying_type,      # "index_component" | "general_stock" | ...
    "underlying_code": underlying_code or "",
    "underlying_name": underlying_name or "",
    "underlying_market": underlying_market,  # "CN" | "US" | "HK" | "EN" | "Other"
    "is_equity": is_equity,                  # True/False
    
    # ===== 通用字段：预期创收与期限 =====
    "expected_yield": expected_yield,        # 小数，如 0.08
    "begin_date": begin_date.isoformat() if begin_date else None,
    "expiry_date": expiry_date.isoformat() if expiry_date else None,
    "term_days": term_days if term_days > 0 else 90,
    
    # ===== 期权专有字段 =====
    "option_type": option_type if contract_type == "option" else None,  # "call" | "put"
    "premium_rate": premium_rate if contract_type == "option" else None,  # 小数，如 0.05
    "total_premium_amount": total_premium_amount if contract_type == "option" else None,
    "single_premium_amount": single_premium_amount if contract_type == "option" else None,
    "contract_multiplier": contract_multiplier if contract_type == "option" else None,
    "contract_size": contract_size if contract_type == "option" else None,
    "exercise_price": exercise_price if contract_type == "option" else None,
    "option_delta": option_delta if contract_type == "option" else None,
    "option_margin_amount": option_margin_amount if contract_type == "option" else None,
    "option_margin_rate": option_margin_rate if contract_type == "option" else None,
    
    # ===== 收益互换专有字段 =====
    "equity_swap_margin_rate": equity_swap_margin_rate if contract_type == "equity_swap" else None,  # 小数，如 0.10
    "equity_swap_margin_amount": equity_swap_margin_amount if contract_type == "equity_swap" else None,
    "equity_swap_delta": None,  # 互换 Delta 默认为 1.0，在 get_otc_delta_amount 中处理
    
    # ===== 收益凭证专有字段 =====
    "funds_raised": funds_raised if contract_type == "income_certificate" else None,
    "is_float_income": is_float_income if contract_type == "income_certificate" else None,
    "income_certificate_delta": income_certificate_delta if contract_type == "income_certificate" else None, # 固定为0，浮动自选
}

with tab2:
    st.subheader("对冲工具列表")
    
    # ===== 标的资产分类说明 =====
    with st.expander("📋 标的资产分类说明"):
        st.markdown("""
        | 资产分类（下拉选项） | 适用范围 | 股票RSF | ETF RSF | HQLA折算率 |
        |---------|------|--------|--------|-----------|
        | **指数成分股** | 沪深300/中证500/上证180/深证100成分股、宽基ETF | 30% | 10% | 50% |
        | **一般上市公司股票** | 非指数成分股的普通股票、非宽基ETF | 50% | 50% | 0% |
        | **流动受限股票** | 限售股等 | 100% | — | 0% |
        | **其他股票** | 上述之外的股票 | 100% | — | 0% |
        """)
        st.caption("提示：系统根据「工具类型」自动区分股票与ETF，在同一分类下应用各自的RSF系数。")
    
    if 'hedge_tools' not in st.session_state:
        st.session_state['hedge_tools'] = []
    
    with st.expander("➕ 新增对冲工具"):
        col1, col2 = st.columns(2)
        with col1:
            # 1.工具类型(tool_type)
            tool_type_display = st.selectbox(
                "工具类型",
                [
                    "指数成分股", "一般上市公司股票", "流动受限股票", "其他股票",  # 股票类
                    "ETF","其他指数基金", "其他权益类基金", "货币基金", "利率债指数基金", "其他非权益类基金",  # 基金类
                    "股指期货", "国债期货", "大宗商品期货",  # 期货类
                    "权益互换", "利率互换",  # 互换类
                    "场内期权", "场外期权",  # 期权类
                    "单一产品（私募基金）", "集合及信托",  # 产品类
                    "大宗商品现货（含黄金）",  # 商品类
                ],
                key="new_tool_type"
            )
            
            tool_type = TOOL_TYPE_MAP[tool_type_display]

            # 2.对冲方向(direction)
            tool_direction = st.selectbox("方向", ["买入", "卖出"], key="new_tool_dir")
            DIRECTION_MAP = {"买入": "long", "卖出": "short"}
            direction = DIRECTION_MAP[tool_direction]

            # 3.名义价值(notional)
            tool_notional = st.number_input("名义价值（万元）", min_value=0.0, value=500.0, key="new_tool_notional")
        
        with col2:
            # ===== 根据工具类型显示不同参数 =====
            # 初始化所有变量
            cash_spent = None
            futures_margin = None
            futures_margin_rate = None
            option_premium = None
            option_delta = None
            otc_payment = None
            pass_through_fee = None
            subscription_amount = None
            option_type = None
            delta_valid = True
            delta_warning_msg = ""
            etf_name = etf_code = stock_name = stock_code = None
            tool_code = None
            underlying_code = None
            underlying_type = None
            stock_type_value = None
            
            # --- 1.股票类 ---
            if tool_type in ["index_component", "general_stock", "restricted_stock", "other_stock"]:
                STOCK_TYPE_MAP = {
                    "指数成分股": "index_component",
                    "一般上市公司股票": "general_stock",
                    "流动受限股票": "restricted_stock",
                    "其他股票": "other_stock",
                }
                underlying_type = STOCK_TYPE_MAP[tool_type_display]
                st.caption("股票代码为有效对冲判定必填项；若不填，系统将无法判定标的一致/相关性")
                stock_name = st.text_input("股票名称", placeholder="如：贵州茅台", key="stock_name")
                stock_code = st.text_input("股票代码", placeholder="如：600519.SH", key="stock_code")
                underlying_code = stock_code
                tool_code = stock_code
            
            # --- 2.基金类 ---
            elif tool_type in ["etf", "other_index_fund", "other_equity_fund", "monetary_fund", "interest_rate_bond_index_fund", "other_non_equity_fund"]:
                fund_type_display = {
                    "etf": "ETF",
                    "other_index_fund": "其他指数基金",
                    "other_equity_fund": "其他权益类基金",
                    "monetary_fund": "货币基金",
                    "interest_rate_bond_index_fund": "利率债指数基金",
                    "other_non_equity_fund": "其他非权益类基金",
                }
                st.caption(f"当前工具：{fund_type_display.get(tool_type, tool_type)}")
                st.caption("基金代码为有效对冲判定必填项")
                etf_name = st.text_input("基金名称", placeholder="如：沪深300ETF", key="etf_name")
                etf_code = st.text_input("基金代码", placeholder="如：510300.SH", key="etf_code")
                underlying_code = st.text_input("基金挂钩指数代码", placeholder="如：000300.SH", key="etf_ul_code")
                tool_code = etf_code
                underlying_type = "index_component" if underlying_code in BROAD_BASED else "non_index_component"
            
            # --- 3.期货类 ---
            elif tool_type in ["stock_index_future", "treasury_future", "bulk_commodity_future"]:
                future_type_display = {"stock_index_future": "股指期货", "treasury_future": "国债期货", "bulk_commodity_future": "大宗商品期货"}
                st.caption(f"当前工具：{future_type_display.get(tool_type, tool_type)}")
    
                # ===== 期货保证金录入方式（仿期权） =====
                futures_margin_input_method = st.radio("期货保证金录入方式（请选择一种）", options=["按比例", "按保证金总额"], index=0, horizontal=True, key="futures_margin_method")
                futures_margin = None
                futures_margin_rate = None
                if futures_margin_input_method == "按比例":
                    suggested_futures_margin_rate = DEFAULT_CONFIG['trade']['futures_margin_rate'] * 100  # 12%
                    futures_margin_rate = st.number_input("保证金占名义本金比例（%）", min_value=0.0, value=suggested_futures_margin_rate, step=0.5, key="futures_margin_rate_input")
                    futures_margin_rate /= 100.0  # 转为小数
                    # 计算保证金金额（仅用于展示）
                    futures_margin = tool_notional * futures_margin_rate
                    st.caption(f"💡 当前保证金金额：**{futures_margin:.2f} 万元**（= {tool_notional} × {futures_margin_rate*100:.1f}%）")
                else:
                    futures_margin = st.number_input("保证金总额（万元）", min_value=0.0, value=tool_notional * DEFAULT_CONFIG['trade']['futures_margin_rate'], step=10.0, key="futures_margin_amount_input")
                    # 反算保证金比例（仅用于展示）
                    if tool_notional > 0:
                        futures_margin_rate = futures_margin / tool_notional
                        st.caption(f"💡 当前保证金比例：**{futures_margin_rate*100:.1f}%**（= {futures_margin} / {tool_notional}）")
                    else:
                        futures_margin_rate = DEFAULT_CONFIG['trade']['futures_margin_rate']
    
                st.caption("标的指数代码为有效对冲判定必填项")
                future_ul_code = st.text_input("标的指数代码", placeholder="如：000300.SH", key="future_ul_code")
                underlying_code = future_ul_code
                tool_code = future_ul_code
            
            # --- 4.互换类 ---
            elif tool_type in ["equity_swap", "interest_rate_swap"]:
                swap_type_display = {
                    "equity_swap": "权益互换",
                    "interest_rate_swap": "利率互换",
                }
                st.caption(f"当前工具：{swap_type_display.get(tool_type, tool_type)}")
                st.caption("互换对手方/标的代码为有效对冲判定必填项")
                swap_code = st.text_input(
                    "标的代码", 
                    placeholder="如：000300.SH", 
                    key="swap_code"
                )
                underlying_code = swap_code
                tool_code = swap_code
            
            # --- 5.期权类（场内/场外） ---
            elif tool_type in ["onsite_option", "otc_option"]:
                option_type = st.selectbox(
                    "期权类型",
                    ["看涨期权", "看跌期权"],
                    key="new_option_type"
                )
                option_premium = st.number_input(
                    "权利金收支（万元）",
                    value=tool_notional * DEFAULT_CONFIG['client']['default_option_premium_rate'],
                    min_value=0.0,
                    key="new_option_premium"
                )
                
                # Delta 输入（带符号校验）
                suggested_delta = DEFAULT_CONFIG['client']['atm_option_delta']
                if option_type == "看跌期权" and tool_direction == "买入":
                    suggested_delta = -suggested_delta
                elif option_type == "看涨期权" and tool_direction == "卖出":
                    suggested_delta = -suggested_delta
                
                option_delta = st.number_input(
                    "Delta（系数，如 0.50=50%）",
                    value=suggested_delta,
                    key="new_option_delta",
                    help="期权价格对标的资产价格的敏感度，非百分比。买入看涨/卖出看跌应为正，买入看跌/卖出看涨应为负。"
                )
                
                # Delta 符号校验
                expected_sign_map = {
                    ("买入", "看涨期权"): "正",
                    ("卖出", "看涨期权"): "负",
                    ("买入", "看跌期权"): "负",
                    ("卖出", "看跌期权"): "正",
                }
                expected = expected_sign_map.get((tool_direction, option_type), "未知")
                delta_valid, delta_warning_msg = validate_option_delta(tool_direction, option_type, option_delta)
                
                if delta_valid:
                    st.success(delta_warning_msg)
                else:
                    st.error(delta_warning_msg)
                st.caption(f"提示：{tool_direction}{option_type}的 Delta 期望符号为 **{expected}**")
                
                # 期权代码
                st.caption("期权代码为有效对冲判定必填项（用于获取Greeks）")
                option_code = st.text_input(
                    "期权代码", 
                    placeholder="如：90007054.SZ", 
                    key="new_option_code"
                )
                st.caption("标的代码用于判定标的一致/相关性")
                option_ul_code = st.text_input(
                    "标的代码", 
                    placeholder="如：000300.SH", 
                    key="option_ul_code"
                )
                tool_code = option_code
                underlying_code = option_ul_code
            
            # --- 6.场外背对背对冲 ---
            elif tool_type == "otc_hedge":
                otc_payment = st.number_input("向平盘方支付预付金（万元）", value=0.0, key="otc_payment")
                pass_through_fee = st.number_input("平盘成本（年化%）", value=2.0, step=0.1, key="pass_through_fee")
                st.caption("标的代码为有效对冲判定必填项")
                otc_underlying_code = st.text_input(
                    "标的代码", 
                    placeholder="如：000300.SH", 
                    key="otc_underlying_code"
                )
                underlying_code = otc_underlying_code
                tool_code = otc_underlying_code
            
            # --- 7.单一产品（私募基金）/集合及信托 ---
            elif tool_type in ["single_product(private_fund)", "collection_and_trust"]:
                product_type_display = {
                    "single_product(private_fund)": "私募基金（单一产品）",
                    "collection_and_trust": "集合及信托",
                }
                st.caption(f"当前工具：{product_type_display.get(tool_type, tool_type)}")
                subscription_amount = st.number_input(
                    "申购金额（万元）", 
                    value=tool_notional,
                    min_value=0.0,
                    key="subscription_amount"
                )
                st.caption("产品代码为有效对冲判定必填项")
                product_code = st.text_input(
                    "产品代码", 
                    placeholder="如：SD6346", 
                    key="product_code"
                )
                underlying_code = product_code
                tool_code = product_code
            
            # --- 8.大宗商品现货 ---
            elif tool_type == "bulk_commodity":
                st.caption("当前工具：大宗商品现货（含黄金）")
                st.caption("商品代码为有效对冲判定必填项")
                commodity_code = st.text_input(
                    "商品代码", 
                    placeholder="如：AU9999.SH", 
                    key="commodity_code"
                )
                underlying_code = commodity_code
                tool_code = commodity_code
            
            # --- 兜底 ---
            else:
                st.caption("请填写以下信息")
                other_code = st.text_input("工具代码", placeholder="请输入代码", key="other_code")
                tool_code = other_code
                underlying_code = other_code
        
        # ===== 提交按钮 =====
        if st.button("添加到对冲列表", key="add_hedge"):
            if not delta_valid:
                st.error(f"无法添加对冲工具：{delta_warning_msg}")
            else:
                hedge = {
                    "tool_type": tool_type,
                    "direction": direction,
                    "notional": tool_notional,
                    "tool_code": tool_code or "",
                    "underlying_type": underlying_type,
                    "underlying_name": stock_name or etf_name or "",
                    "underlying_code": underlying_code or "",
                    "underlying_market": "CN",  # 默认A股
                    "is_equity": tool_type in [
                        "index_component", "general_stock", "restricted_stock", "other_stock",
                        "index_fund", "other_equity_fund",
                        "stock_index_future", "equity_swap", "onsite_option", "otc_option"
                    ],
                    # 期货
                    "futures_margin": futures_margin,
                    "futures_margin_rate": futures_margin_rate,
                    # 期权
                    "option_type": "call" if option_type == "看涨期权" else "put" if option_type == "看跌期权" else None,
                    "total_premium_amount": option_premium,
                    "option_delta": option_delta,
                    # 场外背对背
                    "otc_payment": otc_payment,
                    "pass_through_fee": pass_through_fee,
                    # 私募基金
                    "subscription_amount": subscription_amount,
                }
                st.session_state['hedge_tools'].append(hedge)
                st.success("✅ 对冲工具已添加")
                st.rerun()
    
    # ===== 展示已有对冲工具 =====
    if st.session_state['hedge_tools']:
        # 反向映射显示
        REV_TOOL_TYPE = {
            "index_component": "指数成分股",
            "general_stock": "一般上市公司股票",
            "restricted_stock": "流动受限股票",
            "other_stock": "其他股票",
            "index_fund": "指数基金（含ETF）",
            "other_equity_fund": "其他权益类基金",
            "monetary_fund": "货币基金",
            "interest_rate_bond_index_fund": "利率债指数基金",
            "other_non_equity_fund": "其他非权益类基金",
            "stock_index_future": "股指期货",
            "treasury_future": "国债期货",
            "bulk_commodity_future": "大宗商品期货",
            "equity_swap": "权益互换",
            "interest_rate_swap": "利率互换",
            "onsite_option": "场内期权",
            "otc_option": "场外期权",
            "single_product(private_fund)": "单一产品（私募基金）",
            "collection_and_trust": "集合及信托",
            "bulk_commodity": "大宗商品现货（含黄金）",
        }
        REV_DIRECTION = {"long": "买入", "short": "卖出"}
        
        display_data = []
        for idx, t in enumerate(st.session_state['hedge_tools'], 1):
            display_data.append({
                "序号": idx,
                "工具类型": REV_TOOL_TYPE.get(t.get('tool_type', ''), t.get('tool_type', '')),
                "方向": REV_DIRECTION.get(t.get('direction', ''), t.get('direction', '')),
                "名义价值（万元）": t.get('notional', 0),
                "标的代码": t.get('underlying_code', '') or '-',
            })
        df = pd.DataFrame(display_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # 删除按钮
        col_del1, col_del2 = st.columns([3, 1])
        with col_del2:
            for idx in range(len(st.session_state['hedge_tools'])):
                if st.button(f"🗑️ 删除 #{idx+1}", key=f"del_{idx}"):
                    st.session_state['hedge_tools'].pop(idx)
                    st.rerun()
    else:
        st.info("尚无对冲工具，请添加")

with tab3:
    st.subheader("计算结果")
    if st.button("计算业务影响", type="primary"):
        cp = st.session_state.get('client_params')
        if not cp:
            st.error("请先在「模块A：场外合约端」填写业务信息")
        else:
            client = OtcContract(**cp)
            hedge_list = [HedgeTrade(**h) for h in st.session_state.get('hedge_tools', [])]
            result = analyze_contract(client, hedge_list)
            
            # ===== 第一层：现金流与资源消耗绝对值 =====
            st.markdown("### 第一层：现金流与资源消耗绝对值")
            col1, col2, col3 = st.columns(3)
            col1.metric("首日净现金流", f"{result['net_day1_cash']:,.2f} 万元")
            col2.metric("新增风险资本准备", f"{result['new_risk_reserve']:,.2f} 万元")
            col3.metric("新增未来30日现金净流出", f"{result['net_cof_change']:,.2f} 万元")
            
            # ===== 第二层：核心风控指标边际变动 =====
            st.markdown("### 第二层：核心风控指标边际变动")
            col1, col2, col3, col4 = st.columns(4)
            
            lcr_delta = result['lcr_change']
            col1.metric("LCR", f"{result['lcr_new']:.2%}",
                        delta=f"{lcr_delta:+.2%}",
                        delta_color="inverse" if lcr_delta < 0 else "normal")
            col1.caption(f"原值: {result['lcr_old']:.2%} ｜ ≥100%")
            
            nsfr_delta = result['nsfr_change']
            col2.metric("NSFR", f"{result['nsfr_new']:.2%}",
                        delta=f"{nsfr_delta:+.2%}",
                        delta_color="inverse" if nsfr_delta < 0 else "normal")
            col2.caption(f"原值: {result['nsfr_old']:.2%} ｜ ≥100%")
            
            lev_delta = result['leverage_change']
            col3.metric("资本杠杆率", f"{result['leverage_new']:.2%}",
                        delta=f"{lev_delta:+.2%}",
                        delta_color="inverse" if lev_delta < 0 else "normal")
            col3.caption(f"原值: {result['leverage_old']:.2%} ｜ ≥8%")
            
            rc_delta = result['risk_coverage_change']
            col4.metric("风险覆盖率", f"{result['risk_coverage_new']:.2%}",
                        delta=f"{rc_delta:+.2%}",
                        delta_color="inverse" if rc_delta < 0 else "normal")
            col4.caption(f"原值: {result['risk_coverage_old']:.2%} ｜ ≥100%")
            
            # ===== 第三层：动态性价比指标 =====
            st.markdown("### 第三层：动态性价比指标")
            col1, col2, col3 = st.columns(3)
            col1.metric("ROC 资本收益率", f"{result['roc']:.2f} 元/元",
                        help="预期创收 / 新增风险资本准备")
            col2.metric("RO-LCR 流动性创收率", f"{result['ro_lcr']:.2f} 元/元",
                        help="预期创收 / max(0, Δ现金净流出 - ΔHQLA)")
            col3.metric("RO-NSFR 稳定资金创收率", f"{result['ro_nsfr']:.2f} 元/元",
                        help="预期创收 / Δ所需稳定资金")
            
            # 对冲有效性 & 合规状态
            st.info(f"对冲有效性: {'✅ 有效对冲' if result['is_effective_hedge'][0] else '❌ 未达有效对冲'}")
            if not result['is_effective_hedge'][0]:
                st.caption(f"原因: {result['is_effective_hedge'][1]}")
            
            status_cols = st.columns(4)
            status_cols[0].write(f"LCR: {'✅ 安全' if result['lcr_status'] == 'safe' else '⚠️ 预警' if result['lcr_status'] == 'warning' else '🚨 危险'}")
            status_cols[1].write(f"NSFR: {'✅ 安全' if result['nsfr_status'] == 'safe' else '⚠️ 预警' if result['nsfr_status'] == 'warning' else '🚨 危险'}")
            status_cols[2].write(f"资本杠杆率: {'✅ 安全' if result['leverage_status'] == 'safe' else '⚠️ 预警' if result['leverage_status'] == 'warning' else '🚨 危险'}")
            status_cols[3].write(f"风险覆盖率: {'✅ 安全' if result['risk_coverage_status'] == 'safe' else '⚠️ 预警' if result['risk_coverage_status'] == 'warning' else '🚨 危险'}")
            
            with st.expander("查看明细"):
                st.json(result)

st.markdown("---")
st.caption("本系统依据《证券公司风险控制指标计算标准规定》构建，仅供参考。")