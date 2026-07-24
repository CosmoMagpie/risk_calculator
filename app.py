# ============================================================
# app.py - Streamlit 前端
# ============================================================
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from backend import ClientContract, HedgeTrade, analyze_contract, DEFAULT_CONFIG

st.set_page_config(page_title="场外衍生品风控影响测算系统", layout="wide")
st.title("📊 场外衍生品业务风控影响测算系统")
st.markdown("---")

# ========== 侧边栏 ==========
with st.sidebar:
    st.header("⚙️ 公司基准参数")
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
tab1, tab2, tab3 = st.tabs(["📝 模块A：客户端", "🔄 模块B：交易端", "📈 结果展示"])

with tab1:
    st.subheader("客户端业务要素")
    col1, col2 = st.columns(2)
    
    with col1:
        contract_type = st.selectbox("业务类型", ["场外期权", "收益互换", "收益凭证"])
        direction = st.selectbox("交易方向", ["买入", "卖出"] if contract_type != "收益互换" else ["多头", "空头"])
        notional = st.number_input("名义本金/发行规模（万元）", min_value=0.0, value=1000.0, step=100.0)
        
        # 标的资产属性
        underlying_type_input = st.selectbox(
            "标的资产属性",
            ["指数成分股", "一般上市公司股票", "流动受限股票", "其他股票"],
            help="沪深300、中证500、上证180、深证100成分股或宽基ETF选「指数成分股」"
        )
        underlying_map = {
            "指数成分股": "index_component",
            "一般上市公司股票": "general_stock",
            "流动受限股票": "restricted_stock",
            "其他股票": "other_stock",
        }
        underlying_type = underlying_map[underlying_type_input]
        underlying_name = st.text_input("标的资产名称", value="沪深300")
        underlying_code = st.text_input("标的资产代码", value="000300")
        
        # 预期收益与期限
        st.caption("💡 提示：预期年化收益率与合约期限应根据业务需求合理设置")
        expected_yield = st.number_input("预期年化收益率（%）", min_value=0.0, value=8.0, step=0.5) / 100.0

        st.caption("📅 请设置合约期限")
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
        # 首日资金收付
        premium_rate = None
        margin_rate = None
        funds_raised = None
        stress_loss = None
        option_delta_for_client = None
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
            option_delta = st.number_input("Delta(%)", value=suggested_delta, key="client_option_delta", 
                                           help="Delta = 期权价格对标的资产价格的敏感度。买入看涨/卖出看跌应为正，买入看跌/卖出看涨应为负。")
            # ========== Delta 符号校验 ==========
            # 定义期望的 Delta 符号
            expected_sign_map = {
                ("买入", "看涨期权"): "正",   # 买入看涨 → Delta 应为正
                ("卖出", "看涨期权"): "负",   # 卖出看涨 → Delta 应为负
                ("买入", "看跌期权"): "负",   # 买入看跌 → Delta 应为负
                ("卖出", "看跌期权"): "正",   # 卖出看跌 → Delta 应为正
            }
            expected = expected_sign_map.get((direction, client_option_type), "未知")  # 找不到对应方向和类型的delta符号映射，显示未知
                
            # 检查 Delta 是否与期望一致
            if option_delta is not None and option_delta != 0:
                is_positive = option_delta > 0
                if expected == "正" and not is_positive:
                    delta_valid = False
                    delta_warning_msg = f"⚠️ **Delta 符号警告**：{direction}{client_option_type}的 Delta 应为 **正数**，当前为负数。请检查是否填错。"
                elif expected == "负" and is_positive:
                    delta_valid = False
                    delta_warning_msg = f"⚠️ **Delta 符号警告**：{direction}{client_option_type}的 Delta 应为 **负数**，当前为正数。请检查是否填错。"
                else:
                    delta_valid = True
                    delta_warning_msg = "✅ Delta 符号正确"
            else:
                delta_valid = False
                delta_warning_msg = "⚠️ **Delta 值不能为 0**，请填写有效的 Delta 金额。"
                
                # 显示校验结果
            if delta_valid:
                st.success(delta_warning_msg)
            else:
                st.error(delta_warning_msg)

            st.caption(f"💡 提示：{direction}{client_option_type}的 Delta 期望符号为 **{expected}**")
            if direction == "卖出": 
                st.caption("📌 压力损失 = 标的资产价格±20%的极端情况下，当前期权持仓的最大亏损")
                stress_loss = st.number_input("压力损失（万元）", value=notional * 0.1, step=10.0)
            
        
        elif contract_type == "收益互换":
            margin_rate = st.number_input("保证金/预付金比例（%）", min_value=0.0, max_value=100.0, value=10.0, step=0.5)
            delta_amount = None
            stress_loss = None
        
        else:  # 收益凭证
            funds_raised = st.number_input("募集资金总额（万元）", value=notional, step=100.0)
            delta_amount = None
            stress_loss = None
    
    # 存储客户端参数
    st.session_state['client_params'] = {
        "contract_type": contract_type,
        "direction": direction,
        "notional": notional,
        "underlying_type": underlying_type,
        "underlying_name": underlying_name,
        "underlying_code": underlying_code,
        "premium_rate": premium_rate,
        "margin_rate": margin_rate,
        "funds_raised": funds_raised,
        "option_delta": option_delta_for_client,
        "stress_loss": stress_loss,
        "expected_yield": expected_yield,
        "begin_date": begin_date.isoformat() if begin_date else None,
        "expiry_date": expiry_date.isoformat() if expiry_date else None,
        "term_days": term_days if term_days > 0 else 0,
    }

with tab2:
    st.subheader("对冲工具列表")
    if 'hedge_tools' not in st.session_state:
        st.session_state['hedge_tools'] = []
    
    with st.expander("➕ 新增对冲工具"):
        col1, col2 = st.columns(2)
        with col1:
            tool_type = st.selectbox(
                "工具类型",
                ["ETF现货", "个股", "期货", "场内期权", "场外背对背对冲", "私募基金"],
                key="new_tool_type"
            )
            tool_direction = st.selectbox("方向", ["买入", "卖出"], key="new_tool_dir")
            tool_notional = st.number_input("名义价值（万元）", min_value=0.0, value=500.0, key="new_tool_notional")
        
        with col2:
            cash_spent = futures_margin = option_premium = option_delta = otc_payment = subscription_amount = None
            pass_through_fee = None
            
            if tool_type == "ETF现货":
                cash_spent = st.number_input("资金消耗（万元）", value=tool_notional)
                st.caption("基金名称和代码均为选填，用于有效对冲判定，若不填则按照最保守方式估计风控指标")
                etf_name = st.text_input("ETF名称")
                etf_code = st.text_input("ETF代码")

            
            elif tool_type == "个股":
                st.caption("💡 提示：一次仅能添加一支股票，如用一揽子股票对冲，需分别添加")
                tool_type = st.selectbox("股票类型",
                ["指数成分股", "一般上市公司股票", "流动受限股票", "其他股票"],
                key="stock_type")
                st.caption("股票名称和代码均为选填，用于有效对冲判定，若不填则按照最保守方式估计风控指标")
                stock_name = st.text_input("股票名称")
                stock_code = st.text_input("股票代码")
            
            elif tool_type == "场内期货":
                futures_margin = st.number_input("交易保证金（万元）", value=tool_notional * 0.12, min_value = 0.00)
                future_delta = st.number_input("合约Delta（%）", value=0.0, step=0.1, max_value = 1.0)
            
            elif tool_type == "场内期权":
                # ========== 期权专属字段 ==========
                option_type = st.selectbox(
                    "期权类型", 
                    ["看涨期权", "看跌期权"], 
                    key="new_option_type"
                )
                option_premium = st.number_input(
                    "权利金收支（万元）", 
                    value=tool_notional * DEFAULT_CONFIG['client']['option_premium_rate'],
                    key="new_option_premium"
                )
                
                # ---- Delta 输入（带符号校验）----
                # 计算建议的 Delta 默认值（带正确符号）
                suggested_delta = DEFAULT_CONFIG['client']['atm_option_delta']
                if option_type == "看跌期权" and tool_direction == "买入":
                    suggested_delta = -suggested_delta
                elif option_type == "看涨期权" and tool_direction == "卖出":
                    suggested_delta = -suggested_delta
                # 买入看涨 / 卖出看跌 保持正数
                option_delta = st.number_input(
                    "Delta(%)", 
                    value=suggested_delta,
                    key="new_option_delta",
                    help="Delta = 期权价格对标的资产价格的敏感度。买入看涨/卖出看跌应为正，买入看跌/卖出看涨应为负。"
                )
                
                # ========== Delta 符号校验 ==========
                # 定义期望的 Delta 符号
                expected_sign_map = {
                    ("买入", "看涨期权"): "正",   # 买入看涨 → Delta 应为正
                    ("卖出", "看涨期权"): "负",   # 卖出看涨 → Delta 应为负
                    ("买入", "看跌期权"): "负",   # 买入看跌 → Delta 应为负
                    ("卖出", "看跌期权"): "正",   # 卖出看跌 → Delta 应为正
                }
                expected = expected_sign_map.get((tool_direction, option_type), "未知")  # 找不到对应方向和类型的delta符号映射，显示未知
                
                # 检查 Delta 是否与期望一致
                if option_delta is not None and option_delta != 0:
                    is_positive = option_delta > 0
                    if expected == "正" and not is_positive:
                        delta_valid = False
                        delta_warning_msg = f"⚠️ **Delta 符号警告**：{tool_direction}{option_type}的 Delta 应为 **正数**，当前为负数。请检查是否填错。"
                    elif expected == "负" and is_positive:
                        delta_valid = False
                        delta_warning_msg = f"⚠️ **Delta 符号警告**：{tool_direction}{option_type}的 Delta 应为 **负数**，当前为正数。请检查是否填错。"
                    else:
                        delta_valid = True
                        delta_warning_msg = "✅ Delta 符号正确"
                else:
                    delta_valid = False
                    delta_warning_msg = "⚠️ **Delta 值不能为 0**，请填写有效的 Delta 金额。"
                
                # 显示校验结果
                if delta_valid:
                    st.success(delta_warning_msg)
                else:
                    st.error(delta_warning_msg)

                st.caption(f"💡 提示：{tool_direction}{option_type}的 Delta 期望符号为 **{expected}**")
            
            elif tool_type == "场外背对背对冲":
                otc_payment = st.number_input("向平盘方支付预付金（万元）", value=0.0)
                pass_through_fee = st.number_input("平盘成本（年化%）", value=2.0, step=0.1)
            
            else:  # 私募基金
                subscription_amount = st.number_input("申购金额（万元）", value=tool_notional)
        
        if st.button("添加到对冲列表", key="add_hedge"):
            # 校验：Delta 符号是否正确
            if not delta_valid:
                st.error(f"❌ 无法添加对冲工具：{delta_warning_msg}")
            hedge = {
                "tool_type": tool_type,
                "direction": tool_direction,
                "notional": tool_notional,
                "cash_spent": cash_spent,
                "futures_margin": futures_margin,
                "option_premium": option_premium,
                "option_delta": option_delta,
                "otc_payment": otc_payment,
                "pass_through_fee": pass_through_fee,
                "subscription_amount": subscription_amount,
                "option_type": option_type if tool_type == "场内标准化期权" else None,
            }
            st.session_state['hedge_tools'].append(hedge)
            st.success("✅ 对冲工具已添加")
            st.rerun()
    
    # 展示已有对冲工具
    if st.session_state['hedge_tools']:
        df = pd.DataFrame(st.session_state['hedge_tools'])
        st.dataframe(df[['tool_type', 'direction', 'notional']])
        for i in range(len(st.session_state['hedge_tools']) - 1, -1, -1):
            if st.button(f"🗑️ 删除 #{i+1}", key=f"del_{i}"):
                st.session_state['hedge_tools'].pop(i)
                st.rerun()
    else:
        st.info("尚无对冲工具，请添加")

with tab3:
    st.subheader("📊 计算结果")
    if st.button("🚀 计算业务影响", type="primary"):
        cp = st.session_state.get('client_params')
        if not cp:
            st.error("请先在「模块A：客户端」填写业务信息")
        else:
            client = ClientContract(**cp)
            hedge_list = [HedgeTrade(**h) for h in st.session_state.get('hedge_tools', [])]
            result = analyze_contract(client, hedge_list)
            
            # ===== 第一层：资源绝对消耗 =====
            st.markdown("### 第一层：资源绝对消耗")
            col1, col2, col3 = st.columns(3)
            col1.metric("新增风险资本准备", f"{result['new_risk_reserve']:.2f} 万元")
            col2.metric("新增表内外资产总额", f"{result['new_assets']:.2f} 万元")
            col3.metric("新增未来30日现金净流出", f"{result['lcr_net_cof_change']:.2f} 万元")
            
            # ===== 第二层：全局指标变动 =====
            st.markdown("### 第二层：全局指标变动")
            col1, col2, col3 = st.columns(3)
            
            lcr_delta = result['lcr_change']
            col1.metric("LCR", f"{result['lcr_new']:.2%}",
                        delta=f"{lcr_delta:.2%}",
                        delta_color="inverse" if lcr_delta < 0 else "normal")
            col1.caption(f"原值: {result['lcr_old']:.2%} ｜ 预警线: 120%")
            
            nsfr_delta = result['nsfr_change']
            col2.metric("NSFR", f"{result['nsfr_new']:.2%}",
                        delta=f"{nsfr_delta:.2%}",
                        delta_color="inverse" if nsfr_delta < 0 else "normal")
            col2.caption(f"原值: {result['nsfr_old']:.2%} ｜ 预警线: 120%")
            
            rc_delta = result['risk_coverage_change']
            col3.metric("风险覆盖率", f"{result['risk_coverage_new']:.2%}",
                        delta=f"{rc_delta:.2%}",
                        delta_color="inverse" if rc_delta < 0 else "normal")
            col3.caption(f"原值: {result['risk_coverage_old']:.2%} ｜ 预警线: 120%")
            
            # ===== 第三层：性价比 =====
            st.markdown("### 第三层：性价比")
            col1, col2, col3 = st.columns(3)
            col1.metric("资本创收率", f"{result['ro_capital']:.2f} 元/元")
            col2.metric("杠杆利用率", f"{result['ro_assets']:.2f} 元/元")
            col3.metric("流动性创收率", f"{result['ro_lcr']:.2f} 元/元")
            
            # 对冲有效性 & 合规状态
            st.info(f"对冲有效性: {'✅ 有效对冲' if result['is_effective_hedge'] else '❌ 未达有效对冲'}")
            
            status_cols = st.columns(3)
            status_cols[0].write(f"LCR: {'✅ 安全' if result['lcr_status'] == 'safe' else '⚠️ 预警' if result['lcr_status'] == 'warning' else '🚨 危险'}")
            status_cols[1].write(f"NSFR: {'✅ 安全' if result['nsfr_status'] == 'safe' else '⚠️ 预警' if result['nsfr_status'] == 'warning' else '🚨 危险'}")
            status_cols[2].write(f"风险覆盖率: {'✅ 安全' if result['risk_coverage_status'] == 'safe' else '⚠️ 预警' if result['risk_coverage_status'] == 'warning' else '🚨 危险'}")
            
            with st.expander("📄 查看详细明细"):
                st.json(result)

st.markdown("---")
st.caption("本系统依据《证券公司风险控制指标计算标准规定》构建，仅供参考。")