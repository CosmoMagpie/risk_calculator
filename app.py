# ============================================================
# app.py - Streamlit 前端
# ============================================================
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from backend import ClientContract, HedgeTrade, analyze_contract, DEFAULT_CONFIG
from backend.services.ifind_client import (
    ifind_login,
    ifind_logout,
    set_ifind_credentials,
    clear_ifind_credentials,
    get_ifind_login_status,
    get_onsite_option_greeks,
)

# ========== 中英文映射字典 ==========
CN_CONTRACT_TYPE = {
    "场外期权": "call_option",    # 默认; tab1 中由 option_type 决定 call_option/put_option
}
CN_PRODUCT = {"场外期权": "option", "收益互换": "equity_swap", "收益凭证": "income_certificate"}

CN_DIRECTION = {"买入": "buy", "卖出": "short", "多头": "long", "空头": "short"}

# 对冲工具方向：后端 HedgeTrade 用 long/short，与合约端 buy/short 不同
CN_HEDGE_DIRECTION = {"买入": "long", "卖出": "short"}

CN_OPTION_TYPE = {"看涨期权": "call_option", "看跌期权": "put_option"}

CN_TOOL_TYPE = {
    "ETF现货": "etf",
    "个股": "stock",
    "场内期货": "futures",
    "期货": "futures",
    "场内期权": "onsite_option",
    "场外背对背对冲": "otc_hedge",
    "私募基金": "private_fund",
}

CN_STOCK_TYPE = {
    "指数成分股": "index_component",
    "一般上市公司股票": "general_stock",
    "流动受限股票": "restricted_stock",
    "其他股票": "other_stock",
}

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
        return False, "⚠️ **Delta 值不能为 0**，请填写有效的 Delta 金额。"
    
    # 定义期望的 Delta 符号映射
    expected_sign_map = {
        ("买入", "看涨期权"): "正",
        ("卖出", "看涨期权"): "负",
        ("买入", "看跌期权"): "负",
        ("卖出", "看跌期权"): "正",
    }
    expected = expected_sign_map.get((direction, option_type_str), "未知")
    
    is_positive = delta_value > 0
    if expected == "正" and not is_positive:
        return False, f"⚠️ **Delta 符号警告**：{direction}{option_type_str}的 Delta 应为 **正数**，当前为负数。请检查是否填错。"
    elif expected == "负" and is_positive:
        return False, f"⚠️ **Delta 符号警告**：{direction}{option_type_str}的 Delta 应为 **负数**，当前为正数。请检查是否填错。"
    else:
        return True, "✅ Delta 符号正确"

st.set_page_config(page_title="场外衍生品风控影响测算系统", layout="wide")
st.title("场外衍生品业务风控影响测算系统")
st.markdown("---")

# ========== 侧边栏 ==========
with st.sidebar:
    st.header("iFinD 数据终端登录")
    st.caption("有效对冲判定（标的相关性）与场内期权 Greeks 自动回填需要登录 iFinD")

    if "ifind_user_name" not in st.session_state:
        st.session_state["ifind_user_name"] = ""
    if "ifind_password" not in st.session_state:
        st.session_state["ifind_password"] = ""

    ifind_user = st.text_input(
        "iFinD 账号",
        value=st.session_state["ifind_user_name"],
        key="ifind_user_input",
    )
    ifind_pwd = st.text_input(
        "iFinD 密码",
        value=st.session_state["ifind_password"],
        key="ifind_pwd_input",
        type="password",
    )
    st.session_state["ifind_user_name"] = ifind_user
    st.session_state["ifind_password"] = ifind_pwd

    login_col, logout_col = st.columns(2)
    with login_col:
        if st.button("登录 iFinD", key="ifind_login_btn"):
            if ifind_user and ifind_pwd:
                set_ifind_credentials(ifind_user, ifind_pwd)
                ok = ifind_login(force=True)
                if ok:
                    st.success("iFinD 登录成功")
                else:
                    st.error("iFinD 登录失败，请检查账号密码及终端状态")
            else:
                st.warning("请先填写账号和密码")
    with logout_col:
        if st.button("登出 iFinD", key="ifind_logout_btn"):
            ifind_logout()
            clear_ifind_credentials()
            st.session_state["ifind_user_name"] = ""
            st.session_state["ifind_password"] = ""
            st.success("已登出并清空凭据")

    status = get_ifind_login_status()
    if status["logged_in"]:
        st.info(f"iFinD 状态：已登录 ({status['user_name']})")
    else:
        st.caption("iFinD 状态：未登录")

    st.divider()

    with st.expander("公司基准参数", expanded=False):
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
tab1, tab2, tab3 = st.tabs(["📝 模块A：场内合约端", "🔄 模块B：交易端（对冲工具）", "📈 结果展示"])

with tab1:
    st.subheader("场内合约端业务要素")
    col1, col2 = st.columns(2)
    
    with col1:
        contract_type = st.selectbox("业务类型", ["场外期权", "收益互换", "收益凭证"])
        direction = st.selectbox("交易方向", ["买入", "卖出"] if contract_type != "收益互换" else ["多头", "空头"])
        notional = st.number_input("名义本金/发行规模（万元）", min_value=0.0, value=1000.0, step=100.0)
        
        # 预期收益与期限
        st.caption("提示：预期年化收益率与合约期限应根据业务需求合理设置")
        expected_yield = st.number_input("预期年化收益率（%）", min_value=0.0, value=8.0, step=0.5) / 100.0

        st.caption("请设置合约期限")
        use_date_picker = st.checkbox(
            "手动选择到期日和起始日", 
            value=False,
            help="勾选后，可通过日期选择器精确设置起止日期；不勾选则直接输入天数"
        )
        if use_date_picker:
            col_date1, col_date2 = st.columns(2)
            with col_date1:
                begin_date = st.date_input("起始日", value=datetime.now().date(), key="begin_date")
            with col_date2:  # 到期日必须晚于起始日
                expiry_date = st.date_input("到期日", value=datetime.now().date() + timedelta(days=90), key="expiry_date", min_value=begin_date + timedelta(days=1))
            term_days = (expiry_date - begin_date).days
            # 显示计算出的期限
            if term_days > 0:
                st.info(f"📆 合约期限：**{term_days} 天**（约 {term_days/30:.1f} 个月）")
            else:
                st.warning("⚠️ 到期日必须晚于起始日，请重新选择")
        else:
            term_days = st.number_input(
                "合约期限（天）", 
                min_value=1, 
                value=90, 
                step=1,
                help="输入合约存续天数"
            )
            begin_date = None
            expiry_date = None
            
            # 显示天数对应的约几个月
            st.caption(f" 约 {term_days/30:.1f} 个月")
    
    with col2:
        # --- 默认值（所有分支均需初始化）---
        premium_rate = None
        margin_rate = None
        funds_raised = None
        stress_loss = None
        option_delta = None
        underlying_type = "index_component"

        # 期权类型（仅场外期权）
        client_option_type = None
        if "期权" in contract_type:
            client_option_type = st.selectbox("期权类型", ["看涨期权", "看跌期权"])
            premium_rate = st.number_input("权利金比例（%）", min_value=0.0, value=5.0, step=0.5)
            # ---- Delta 输入（带符号校验）----
                # 计算建议的 Delta 默认值（带正确符号）
            suggested_delta = DEFAULT_CONFIG['client']['atm_option_delta']
            if client_option_type == "看跌期权" and direction == "买入":
                suggested_delta = -suggested_delta
            elif client_option_type == "看涨期权" and direction == "卖出":
                suggested_delta = -suggested_delta
            # 买入看涨 / 卖出看跌 保持正数
            option_delta = st.number_input("Delta（系数，如 0.50=50%）", value=suggested_delta, key="client_option_delta", 
                                           help="期权价格对标的资产价格的敏感度，非百分比。买入看涨/卖出看跌应为正，买入看跌/卖出看涨应为负。如 50% Delta 请填入 0.50")
            # ========== Delta 符号校验 ==========
            delta_valid, delta_warning_msg = validate_option_delta(direction, client_option_type, option_delta)
            expected_sign_map = {
                ("买入", "看涨期权"): "正",
                ("卖出", "看涨期权"): "负",
                ("买入", "看跌期权"): "负",
                ("卖出", "看跌期权"): "正",
            }
            expected = expected_sign_map.get((direction, client_option_type), "未知")
            if delta_valid:
                st.success(delta_warning_msg)
            else:
                st.error(delta_warning_msg)

            st.caption(f"提示：{direction}{client_option_type}的 Delta 期望符号为 **{expected}**")
            if direction == "卖出": 
                st.caption("📌 压力损失 = 标的资产价格±20%的极端情况下，当前期权持仓的最大亏损")
                stress_loss = st.number_input("压力损失（万元）", value=notional * 0.1, step=10.0)
            
        
        elif contract_type == "收益互换":
            margin_rate = st.number_input("保证金/预付金比例（%）", min_value=0.0, max_value=100.0, value=10.0, step=0.5)
            # 标的资产属性仅用于收益互换的惩罚条件B（个股标的）
            is_individual_stock = st.checkbox(
                "标的资产为境内个股（非宽基/非指数成分股）",
                value=False,
                help="勾选后触发惩罚条件B：市场风险资本准备加倍。标的资产分类详情见模块B。"
            )
            underlying_type = "general_stock" if is_individual_stock else "index_component"
            delta_amount = None
            stress_loss = None
        
        else:  # 收益凭证
            funds_raised = st.number_input("募集资金总额（万元）", value=notional, step=100.0)
            delta_amount = None
            st.caption("浮动型收益凭证（内嵌期权结构）需填写压力损失；固定型请留空")
            stress_loss = st.number_input("压力损失（万元）", value=0.0, step=10.0,
                                          help="浮动型凭证在标的资产极端波动下的最大亏损。填0或留空表示固定型（风险准备=0）")
            if stress_loss == 0.0:
                stress_loss = None  # 0 → None = 固定型
    
    # ---- 标的资产信息（所有产品类型共用）----
    st.divider()
    st.caption("标的资产信息用于有效对冲判定：填写后系统将通过代码判定标的一致性；留空则按最保守方式估算")
    col_code1, col_code2 = st.columns(2)
    with col_code1:
        underlying_name = st.text_input("标的名称", placeholder="如：沪深300指数", key="client_ul_name")
    with col_code2:
        underlying_code = st.text_input("标的代码", placeholder="如：000300 或 000300.SH", key="client_ul_code")

    # ---- 场外卖出期权保证金（影响净资本扣减）----
    option_margin_amount = None
    option_margin_rate = None
    exercise_price = None
    contract_multiplier = None
    contract_size = None
    if "期权" in contract_type and direction == "卖出":
        st.divider()
        st.caption("场外卖出期权保证金（用于净资本扣减；不填则使用默认 20%）")
        col_margin1, col_margin2 = st.columns(2)
        with col_margin1:
            option_margin_amount = st.number_input(
                "保证金金额（万元）",
                value=0.0,
                step=10.0,
                key="client_option_margin_amount",
                help="直接填写保证金绝对金额，优先于比例",
            )
        with col_margin2:
            option_margin_rate = st.number_input(
                "保证金比例（%）",
                min_value=0.0,
                max_value=100.0,
                value=DEFAULT_CONFIG["client"]["option_margin_rate"] * 100,
                step=1.0,
                key="client_option_margin_rate",
            )
        if option_margin_amount == 0.0:
            option_margin_amount = None

        # 压力损失估算辅助字段（当前后端保留供扩展，非必填）
        with st.expander("压力损失估算参数（可选）", expanded=False):
            col_e1, col_e2, col_e3 = st.columns(3)
            with col_e1:
                exercise_price = st.number_input("行权价（元）", value=0.0, step=0.01, key="client_exercise_price")
            with col_e2:
                contract_multiplier = st.number_input("合约乘数（元/点）", value=0.0, step=1.0, key="client_contract_multiplier")
            with col_e3:
                contract_size = st.number_input("合约规模（份）", value=0.0, step=1.0, key="client_contract_size")
            if exercise_price == 0.0:
                exercise_price = None
            if contract_multiplier == 0.0:
                contract_multiplier = None
            if contract_size == 0.0:
                contract_size = None

    # 存储合约端参数（中文→英文映射）
    en_contract_type = (
        CN_OPTION_TYPE[client_option_type] if client_option_type
        else CN_PRODUCT[contract_type]
    )
    en_direction = CN_DIRECTION[direction]
    st.session_state['client_params'] = {
        "contract_type": en_contract_type,
        "direction": en_direction,
        "notional": notional,
        "underlying_type": underlying_type,
        "underlying_name": (underlying_name or "").strip(),
        "underlying_code": (underlying_code or "").strip(),
        "option_type": CN_OPTION_TYPE[client_option_type] if client_option_type else None,
        "premium_rate": premium_rate,
        "margin_rate": margin_rate,
        "funds_raised": funds_raised,
        "option_delta": option_delta,
        "stress_loss": stress_loss,
        "option_margin_amount": option_margin_amount,
        "option_margin_rate": option_margin_rate / 100.0 if option_margin_rate is not None else None,
        "exercise_price": exercise_price,
        "contract_multiplier": contract_multiplier,
        "contract_size": contract_size,
        "expected_yield": expected_yield,
        "begin_date": begin_date.isoformat() if begin_date else None,
        "expiry_date": expiry_date.isoformat() if expiry_date else None,
        "term_days": term_days if term_days > 0 else 0,
    }

with tab2:
    st.subheader("对冲工具列表")
    
    with st.expander("📋 标的资产分类"):
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
            tool_type = st.selectbox(
                "工具类型",
                ["ETF现货", "个股", "场内期货", "场内期权", "场外背对背对冲", "私募基金"],
                key="new_tool_type"
            )
            tool_direction = st.selectbox("方向", ["买入", "卖出"], key="new_tool_dir")
            st.caption("💡 对冲方向应与场外合约敞口相反。例如：客户卖出看涨期权（空头敞口），对冲工具应选「买入」")
            tool_notional = st.number_input("名义价值（万元）", min_value=0.0, value=500.0, key="new_tool_notional")
        
        with col2:
            cash_spent = futures_margin = option_premium = option_delta = otc_payment = subscription_amount = None
            pass_through_fee = None
            option_type = None
            delta_valid = True  # 非期权工具默认通过校验
            stock_type_value = None  # ETF/个股的标的资产分类，通过下方下拉框赋值
            etf_name = etf_code = stock_name = stock_code = future_ul_code = None
            option_code = option_ul_code = otc_underlying_code = None
            option_margin = option_margin_rate = option_strike_price = None
            futures_margin_rate = future_delta = future_type = None

            if tool_type == "ETF现货":
                cash_spent = st.number_input("资金消耗（万元）", value=tool_notional)
                stock_type_value = st.selectbox(
                    "标的资产分类",
                    ["指数成分股", "一般上市公司股票", "流动受限股票", "其他股票"],
                    key="etf_stock_type",
                    help="参见上方「标的资产分类」表格。宽基ETF选「指数成分股」RSF=10%；非宽基ETF选「一般上市公司股票」RSF=50%"
                )
                st.caption("ETF代码为有效对冲判定必填项；若不填，系统将无法判定标的一致/相关性，风险资本准备按最保守的单边敞口计提")
                etf_name = st.text_input("ETF名称")
                etf_code = st.text_input("ETF代码")

            
            elif tool_type == "个股":
                st.caption("提示：一次仅能添加一支股票，如用一揽子股票对冲，需分别添加")
                stock_type_value = st.selectbox("标的资产分类",
                ["指数成分股", "一般上市公司股票", "流动受限股票", "其他股票"],
                key="stock_stock_type")
                st.caption("股票代码为有效对冲判定必填项；若不填，系统将无法判定标的一致/相关性，风险资本准备按最保守的单边敞口计提")
                stock_name = st.text_input("股票名称")
                stock_code = st.text_input("股票代码")
            
            elif tool_type == "场内期货":
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    futures_margin = st.number_input("交易保证金（万元）", value=tool_notional * 0.12, min_value=0.0, key="new_futures_margin")
                with col_f2:
                    futures_margin_rate = st.number_input(
                        "保证金比例（%）",
                        min_value=0.0,
                        max_value=100.0,
                        value=DEFAULT_CONFIG["trade"]["futures_margin_rate"] * 100,
                        step=0.5,
                        key="new_futures_margin_rate",
                        help="未直接填写保证金金额时，按 名义价值 × 比例 计算",
                    )
                col_f3, col_f4 = st.columns(2)
                with col_f3:
                    future_delta = st.number_input(
                        "期货 Delta（默认 1.0）",
                        value=DEFAULT_CONFIG["trade"]["future_delta"],
                        step=0.05,
                        key="new_future_delta",
                        help="股指期货 Delta 通常≈1.0",
                    )
                with col_f4:
                    future_type = st.text_input("期货品种", value="IF", key="new_future_type", help="如 IF、IC、IM")
                st.caption("用于有效对冲判定。填写期货标的指数代码（如IF→000300.SH），留空则无法判定标的一致/相关性")
                future_ul_code = st.text_input("标的指数代码", placeholder="如：000300.SH", key="future_ul_code")

            elif tool_type == "场内期权":
                # ========== 期权专属字段 ==========
                option_type = st.selectbox(
                    "期权类型",
                    ["看涨期权", "看跌期权"],
                    key="new_option_type"
                )
                col_op1, col_op2 = st.columns(2)
                with col_op1:
                    option_premium = st.number_input(
                        "权利金收支（万元）",
                        value=tool_notional * DEFAULT_CONFIG['client']['option_premium_rate'],
                        key="new_option_premium"
                    )
                with col_op2:
                    option_strike_price = st.number_input(
                        "行权价（元）",
                        value=0.0,
                        step=0.01,
                        key="new_option_strike_price",
                        help="用于本地 Black-Scholes 估算 Greeks（iFinD 失败时回退）",
                    )
                    if option_strike_price == 0.0:
                        option_strike_price = None

                # ---- 通过 iFinD 自动获取 Delta ----
                st.caption("填写「场内期权代码」后可点击按钮从 iFinD 获取实时 Delta；获取失败可手动修改")
                option_code = st.text_input("场内期权代码", placeholder="如：10011855", key="new_option_code")
                option_ul_code = st.text_input("标的代码", placeholder="如：510050.SH", key="option_ul_code")

                if "fetched_option_delta" not in st.session_state:
                    st.session_state["fetched_option_delta"] = None
                if "fetched_option_code" not in st.session_state:
                    st.session_state["fetched_option_code"] = ""

                if st.button("从 iFinD 获取 Delta", key="fetch_delta_btn"):
                    if option_code and option_code.strip():
                        try:
                            fetched = get_onsite_option_greeks(option_code.strip(), "delta")
                            if fetched is not None:
                                # iFinD 返回的是期权合约本身的 Delta（看涨为正、看跌为负），
                                # 需根据头寸方向（买入=+1，卖出=-1）转换为「头寸 Delta」后回填。
                                position_direction = 1 if tool_direction == "买入" else -1
                                position_delta = position_direction * float(fetched)
                                st.session_state["fetched_option_delta"] = position_delta
                                st.session_state["fetched_option_code"] = option_code.strip()
                                st.success(f"iFinD 合约 Delta = {fetched:.4f}，已按「{tool_direction}」转换为头寸 Delta = {position_delta:.4f} 并回填")
                            else:
                                st.warning("iFinD 未返回有效 Delta，请检查代码或登录状态，并手动填写")
                        except Exception as e:
                            st.error(f"获取 Greeks 失败：{e}")
                    else:
                        st.warning("请先填写场内期权代码")

                # ---- Delta 输入（带符号校验）----
                # 如果刚获取了对应代码的 Delta，以 iFinD 值作为默认值；否则按方向估算符号
                if st.session_state["fetched_option_delta"] is not None and st.session_state["fetched_option_code"] == option_code:
                    suggested_delta = st.session_state["fetched_option_delta"]
                else:
                    suggested_delta = DEFAULT_CONFIG['client']['atm_option_delta']
                    if option_type == "看跌期权" and tool_direction == "买入":
                        suggested_delta = -suggested_delta
                    elif option_type == "看涨期权" and tool_direction == "卖出":
                        suggested_delta = -suggested_delta

                option_delta = st.number_input(
                    "Delta（系数，如 0.50=50%）",
                    value=suggested_delta,
                    key="new_option_delta",
                    help="期权价格对标的资产价格的敏感度，非百分比。买入看涨/卖出看跌应为正，买入看跌/卖出看涨应为负。如 50% Delta 请填入 0.50"
                )

                # 卖出场内期权保证金（影响净资本扣减）
                if tool_direction == "卖出":
                    col_om1, col_om2 = st.columns(2)
                    with col_om1:
                        option_margin = st.number_input(
                            "卖出保证金金额（万元）",
                            value=0.0,
                            step=10.0,
                            key="new_option_margin",
                            help="直接填写保证金绝对金额，优先于比例",
                        )
                    with col_om2:
                        option_margin_rate = st.number_input(
                            "卖出保证金比例（%）",
                            min_value=0.0,
                            max_value=100.0,
                            value=DEFAULT_CONFIG["trade"]["onsite_option_margin_rate"] * 100,
                            step=0.5,
                            key="new_option_margin_rate",
                        )
                    if option_margin == 0.0:
                        option_margin = None

                # ========== Delta 符号校验 ==========
                delta_valid, delta_warning_msg = validate_option_delta(tool_direction, option_type, option_delta)
                expected_sign_map = {
                    ("买入", "看涨期权"): "正",
                    ("卖出", "看涨期权"): "负",
                    ("买入", "看跌期权"): "负",
                    ("卖出", "看跌期权"): "正",
                }
                expected = expected_sign_map.get((tool_direction, option_type), "未知")
                if delta_valid:
                    st.success(delta_warning_msg)
                else:
                    st.error(delta_warning_msg)

                st.caption(f"提示：{tool_direction}{option_type}的 Delta 期望符号为 **{expected}**")

            elif tool_type == "场外背对背对冲":
                st.caption("表外项目余额按被对冲合约类型自动判断：期权/收益凭证类按 N×0.5%，互换类按 N×10%")
                otc_payment = st.number_input("向平盘方支付预付金（万元）", value=0.0, key="new_otc_payment")
                pass_through_fee = st.number_input("平盘成本（年化%）", value=2.0, step=0.1, key="new_otc_fee")
                st.caption("用于有效对冲判定，填写被对冲合约的标的代码")
                otc_underlying_code = st.text_input("标的代码", placeholder="如：000300.SH", key="otc_underlying_code")
            
            else:  # 私募基金
                subscription_amount = st.number_input("申购金额（万元）", value=tool_notional)
        
        if st.button("添加到对冲列表", key="add_hedge"):
            # 校验：Delta 符号是否正确
            if not delta_valid:
                st.error(f"❌ 无法添加对冲工具：{delta_warning_msg}")
            else:
                hedge = {
                    "tool_type": CN_TOOL_TYPE[tool_type],
                    "direction": CN_HEDGE_DIRECTION[tool_direction],
                    "notional": tool_notional,
                    "underlying_type": CN_STOCK_TYPE.get(stock_type_value, "index_component") if stock_type_value else None,
                    "underlying_name": (etf_name or stock_name or "").strip(),
                    "underlying_code": (etf_code or stock_code or future_ul_code or option_ul_code or otc_underlying_code or "").strip(),
                    "tool_code": (option_code or "").strip(),
                    "cash_spent": cash_spent,
                    "futures_margin": futures_margin,
                    "futures_margin_rate": futures_margin_rate / 100.0 if futures_margin_rate is not None else None,
                    "future_delta": future_delta,
                    "future_type": future_type,
                    "option_premium": option_premium,
                    "option_delta": option_delta,
                    "option_type": CN_OPTION_TYPE.get(option_type if tool_type == "场内期权" else None),
                    "option_strike_price": option_strike_price,
                    "option_margin": option_margin,
                    "option_margin_rate": option_margin_rate / 100.0 if option_margin_rate is not None else None,
                    "otc_payment": otc_payment,
                    "pass_through_fee": pass_through_fee,
                    "subscription_amount": subscription_amount,
                    "stock_type": CN_STOCK_TYPE.get(stock_type_value) if stock_type_value else None,
                }
                st.session_state['hedge_tools'].append(hedge)
                st.success("✅ 对冲工具已添加")
                st.rerun()
    
    # 展示已有对冲工具
    if st.session_state['hedge_tools']:
        # 反向映射：英文→中文，用于表格显示
        REV_TOOL_TYPE = {v: k for k, v in CN_TOOL_TYPE.items() if k != "期货"}
        REV_DIRECTION = {"buy": "买入", "short": "卖出", "long": "买入"}
        display_data = []
        for t in st.session_state['hedge_tools']:
            display_data.append({
                "工具类型": REV_TOOL_TYPE.get(t['tool_type'], t['tool_type']),
                "方向": REV_DIRECTION.get(t['direction'], t['direction']),
                "名义价值（万元）": t['notional'],
                "标的代码": t.get('underlying_code', '') or '',
            })
        df = pd.DataFrame(display_data)
        df.index = range(1, len(df) + 1)  # 1-based 序号
        st.dataframe(df)
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
            st.error("请先在「模块A：场内合约端」填写业务信息")
        else:
            # 将侧边栏修改后的公司基准参数同步到 DEFAULT_CONFIG（万元 → 元）
            firm_params = st.session_state.get('firm_params', {})
            for key, value in firm_params.items():
                if key == "classification_factor":
                    DEFAULT_CONFIG["firm"][key] = value
                elif isinstance(value, (int, float)):
                    DEFAULT_CONFIG["firm"][key] = value * 10000

            client = ClientContract(**cp)
            hedge_list = [HedgeTrade(**h) for h in st.session_state.get('hedge_tools', [])]
            result = analyze_contract(client, hedge_list)

            # 除0保护值（后端用 999 做哨兵）在界面显示为「不适用」
            def fmt_ratio(val):
                return "不适用" if abs(val - 999.0) < 1e-6 else f"{val:.2%}"

            def fmt_num(val):
                return "不适用" if abs(val - 999.0) < 1e-6 else f"{val:.2f} 元/元"

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
            col1.metric("LCR", fmt_ratio(result['lcr_new']),
                        delta=f"{lcr_delta:+.2%}",
                        delta_color="inverse" if lcr_delta < 0 else "normal")
            col1.caption(f"原值: {fmt_ratio(result['lcr_old'])} ｜ ≥100%")

            nsfr_delta = result['nsfr_change']
            col2.metric("NSFR", fmt_ratio(result['nsfr_new']),
                        delta=f"{nsfr_delta:+.2%}",
                        delta_color="inverse" if nsfr_delta < 0 else "normal")
            col2.caption(f"原值: {fmt_ratio(result['nsfr_old'])} ｜ ≥100%")

            lev_delta = result['leverage_change']
            col3.metric("资本杠杆率", fmt_ratio(result['leverage_new']),
                        delta=f"{lev_delta:+.2%}",
                        delta_color="inverse" if lev_delta < 0 else "normal")
            col3.caption(f"原值: {fmt_ratio(result['leverage_old'])} ｜ ≥8%")

            rc_delta = result['risk_coverage_change']
            col4.metric("风险覆盖率", fmt_ratio(result['risk_coverage_new']),
                        delta=f"{rc_delta:+.2%}",
                        delta_color="inverse" if rc_delta < 0 else "normal")
            col4.caption(f"原值: {fmt_ratio(result['risk_coverage_old'])} ｜ ≥100%")

            # ===== 第三层：动态性价比指标 =====
            st.markdown("### 第三层：动态性价比指标")
            col1, col2, col3 = st.columns(3)
            col1.metric("ROC 资本收益率", fmt_num(result['roc']),
                        help="预期创收 / 新增风险资本准备")
            col2.metric("RO-LCR 流动性创收率", fmt_num(result['ro_lcr']),
                        help="预期创收 / max(0, Δ现金净流出 - ΔHQLA)")
            col3.metric("RO-NSFR 稳定资金创收率", fmt_num(result['ro_nsfr']),
                        help="预期创收 / Δ所需稳定资金")

            # 对冲有效性 & 合规状态
            st.info(f"对冲有效性: {'✅ 有效对冲' if result['is_effective_hedge'][0] else '❌ 未达有效对冲'}")
            if not result['is_effective_hedge'][0]:
                st.caption(f"原因: {result['is_effective_hedge'][1]}")

            # 调试信息：展示实际传入的标的代码与 Delta，便于排查 TC01/TC02 类问题
            with st.expander("对冲判定详情（调试用）"):
                hedge_codes = [h.get_tool_underlying_code() for h in hedge_list]
                hedge_dirs = [h.get_tool_direction() for h in hedge_list]
                st.write(f"场外合约标的代码：{repr(client.get_otc_underlying_code())}")
                st.write(f"场外合约 Delta：{client.get_otc_delta_amount()}")
                st.write(f"对冲工具标的代码：{[repr(c) for c in hedge_codes]}")
                st.write(f"对冲工具方向：{hedge_dirs}")
                for idx, h in enumerate(hedge_list, 1):
                    st.write(f"对冲工具 #{idx} Delta：{h.get_hedge_delta_amount()}（类型={h.get_tool_type()}，方向={h.get_tool_direction()}，名义={h.get_tool_notional()}）")
                st.write(f"有效对冲判定：{'通过' if result['is_effective_hedge'][0] else '未通过'}")
                if not result['is_effective_hedge'][0]:
                    st.write(f"未通过原因：{result['is_effective_hedge'][1]}")

            status_cols = st.columns(4)
            status_cols[0].write(f"LCR: {'✅ 安全' if result['lcr_status'] == 'safe' else '⚠️ 预警' if result['lcr_status'] == 'warning' else '🚨 危险'}")
            status_cols[1].write(f"NSFR: {'✅ 安全' if result['nsfr_status'] == 'safe' else '⚠️ 预警' if result['nsfr_status'] == 'warning' else '🚨 危险'}")
            status_cols[2].write(f"资本杠杆率: {'✅ 安全' if result['leverage_status'] == 'safe' else '⚠️ 预警' if result['leverage_status'] == 'warning' else '🚨 危险'}")
            status_cols[3].write(f"风险覆盖率: {'✅ 安全' if result['risk_coverage_status'] == 'safe' else '⚠️ 预警' if result['risk_coverage_status'] == 'warning' else '🚨 危险'}")

            with st.expander("查看明细"):
                st.json(result)
