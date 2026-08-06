# ============================================================
# app.py - Streamlit 前端
# ============================================================
import streamlit as st
import pandas as pd
import textwrap
from datetime import datetime, timedelta
from backend import ClientContract, HedgeTrade, analyze_contract, DEFAULT_CONFIG
from backend.services.ifind_client import (
    ifind_login,
    ifind_logout,
    set_ifind_credentials,
    clear_ifind_credentials,
    get_ifind_login_status,
    get_onsite_option_greeks,
    get_onsite_option_underlying_code,
)

# ========== 中英文映射字典 ==========
CN_CONTRACT_TYPE = {
    "场外期权": "call_option",    # 默认; tab1 中由 option_type 决定 call_option/put_option
}
CN_PRODUCT = {"场外期权": "option", "收益互换": "equity_swap", "收益凭证": "income_certificate"}

CN_DIRECTION = {"买入": "buy", "卖出": "short", "多头": "long", "空头": "short", "发行": "issue"}

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
        return False, "Delta 值不能为 0，请填写有效的 Delta 金额。"
    
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
        return False, f"Delta 符号警告：{direction}{option_type_str}的 Delta 应为 **正数**，当前为负数。请检查是否填错。"
    elif expected == "负" and is_positive:
        return False, f"Delta 符号警告：{direction}{option_type_str}的 Delta 应为 **负数**，当前为正数。请检查是否填错。"
    else:
        return True, "Delta 符号校验正确"

def render_status_badge(label, status):
    """生成具备 SVG 图标的合规状态徽章 HTML"""
    if status == "safe":
        svg = '<svg style="vertical-align: -2px; margin-right: 4px;" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>'
        return f'<div class="status-badge-safe">{svg}{label}: 安全</div>'
    elif status == "warning":
        svg = '<svg style="vertical-align: -2px; margin-right: 4px;" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>'
        return f'<div class="status-badge-warning">{svg}{label}: 预警</div>'
    else:
        svg = '<svg style="vertical-align: -2px; margin-right: 4px;" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>'
        return f'<div class="status-badge-danger">{svg}{label}: 危险</div>'


# ============================================================
# 模块B/C：对冲方案管理（多方案列表与对比）
# ============================================================

# 英文 → 中文反向映射，用于表格展示
REV_TOOL_TYPE = {v: k for k, v in CN_TOOL_TYPE.items() if k != "期货"}
REV_DIRECTION = {"buy": "买入", "short": "卖出", "long": "买入"}


def _fmt_ratio(val):
    """无经济含义的比率显示为“不适用”；兼容旧版 999 哨兵。"""
    return "不适用" if val is None or abs(val - 999.0) < 1e-6 else f"{val:.2%}"


def _fmt_num(val):
    return "不适用" if val is None or abs(val - 999.0) < 1e-6 else f"{val:.2f} 元/元"


def _hedge_tool_display_table(tools: list) -> pd.DataFrame:
    """将对冲工具字典列表转为用于展示的 DataFrame（1-based 序号）。"""
    display_data = []
    for t in tools:
        display_data.append({
            "工具类型": REV_TOOL_TYPE.get(t["tool_type"], t["tool_type"]),
            "方向": REV_DIRECTION.get(t["direction"], t["direction"]),
            "名义价值（万元）": t["notional"],
            "标的代码": t.get("underlying_code", "") or "",
        })
    df = pd.DataFrame(display_data)
    df.index = range(1, len(df) + 1)
    return df


def _remove_temp_tool(idx: int) -> None:
    """
    弹窗内删除工具的 on_click 回调：
    在点击触发的重跑之前从 dialog_temp_tools 移除指定工具，
    使弹窗（片段）重跑后列表即时刷新且弹窗保持打开。
    """
    tools = st.session_state.get("dialog_temp_tools")
    if tools is not None and 0 <= idx < len(tools):
        tools.pop(idx)


def render_tool_adder(target_list: list) -> None:
    """
    渲染「新增对冲工具」表单（沿用单方案版全部输入字段）。
    点击「添加到对冲列表」并通过 Delta 符号校验后，将工具追加到 target_list。
    """
    col1, col2 = st.columns(2)
    with col1:
        client_instrument = st.session_state.get("client_params", {}).get(
            "underlying_instrument"
        )
        client_contract_type = st.session_state.get("client_params", {}).get(
            "contract_type"
        )
        tool_options = ["ETF现货", "场内期货", "场内期权", "场外背对背对冲", "私募基金"]
        if (
            client_instrument == "etf"
            and client_contract_type in ("call_option", "put_option")
        ):
            tool_options.insert(1, "个股")
        tool_type = st.selectbox(
            "工具类型",
            tool_options,
            key="new_tool_type"
        )
        tool_direction = st.selectbox("方向", ["买入", "卖出"], key="new_tool_dir")
        st.caption("提示：对冲方向应与场外合约敞口相反。例如：客户卖出看涨期权（空头敞口），对冲工具应选「买入」")
        tool_notional = st.number_input("名义价值（万元）", min_value=0.0, value=500.0, key="new_tool_notional")

    with col2:
        cash_spent = futures_margin = option_premium = option_delta = otc_payment = subscription_amount = None
        pass_through_fee = None
        option_type = None
        delta_valid = True  # 非期权工具默认通过校验
        stock_type_value = None  # ETF/个股的标的资产分类，通过下方下拉框赋值
        etf_code = stock_code = future_ul_code = None
        option_code = option_ul_code = otc_underlying_code = None
        option_margin = option_margin_rate = None
        futures_margin_rate = future_delta = future_type = None
        is_broad_based_etf = False
        otc_hedge_contract_type = otc_stress_loss = None
        fund_structure = fund_lookthrough_risk_rate = asset_maturity_days = fund_delta = None

        if tool_type == "ETF现货":
            cash_spent = st.number_input("资金消耗（万元）", value=tool_notional)
            etf_class = st.selectbox("ETF分类", ["宽基股票指数ETF", "其他权益ETF"], key="etf_stock_type")
            is_broad_based_etf = etf_class == "宽基股票指数ETF"
            stock_type_value = "指数成分股" if is_broad_based_etf else "一般上市公司股票"
            st.caption("ETF代码为有效对冲判定必填项；若不填，系统将无法判定标的一致/相关性，风险资本准备按最保守的单边敞口计提")
            etf_code = st.text_input("ETF代码")

        elif tool_type == "个股":
            st.caption("仅适用于ETF标的场外期权。一次添加一只股票；股票篮子需逐只添加，系统按各头寸Delta权重合成篮子并检验一年相关性。")
            stock_type_value = st.selectbox("标的资产分类",
            ["指数成分股", "一般上市公司股票", "流动受限股票", "其他股票"],
            key="stock_stock_type")
            st.caption("股票代码为有效对冲判定必填项；若不填，系统将无法判定标的一致/相关性，风险资本准备按最保守的单边敞口计提")
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
            option_premium = st.number_input(
                "权利金收支（万元）",
                value=tool_notional * DEFAULT_CONFIG['client']['option_premium_rate'],
                key="new_option_premium"
            )

            # ---- 期权代码 → 标的代码自动判定（无需手动填写标的）----
            option_code = st.text_input("场内期权代码", placeholder="如：10011855.SH", key="new_option_code")
            ifind_ok = get_ifind_login_status().get("logged_in", False)
            if option_code and option_code.strip():
                # 仅在代码或 iFinD 登录状态变化时查询一次，避免每次交互重复请求；
                # 未登录时先不缓存失败结果，登录后重新输入同一代码会重新尝试
                if (
                    st.session_state.get("auto_ul_opt_code") != option_code.strip()
                    or st.session_state.get("auto_ul_login") != ifind_ok
                ):
                    st.session_state["auto_ul_opt_code"] = option_code.strip()
                    st.session_state["auto_ul_login"] = ifind_ok
                    st.session_state["auto_ul_result"] = get_onsite_option_underlying_code(
                        option_code.strip()
                    )
                auto_ul = st.session_state.get("auto_ul_result")
                if auto_ul:
                    option_ul_code = str(auto_ul)
                    st.caption(f"标的代码已自动获取：**{option_ul_code}**（由场内期权代码解析）")
                else:
                    st.caption("未能自动获取标的代码（iFinD 未登录或期权代码无效），请手动填写")
                    option_ul_code = st.text_input("标的代码", placeholder="如：510050.SH", key="option_ul_code")
            else:
                option_ul_code = st.text_input("标的代码", placeholder="如：510050.SH", key="option_ul_code")

            if "ifind_delta_msg" not in st.session_state:
                st.session_state["ifind_delta_msg"] = None

            col_btn1, col_btn2 = st.columns([1, 3])
            with col_btn1:
                if st.button("获取 Delta", key="fetch_delta_btn",
                             help="从 iFinD 获取该期权的实时 Delta 并自动填入下方输入框"):
                    if not option_code or not option_code.strip():
                        st.session_state["ifind_delta_msg"] = ("error", "请先填写场内期权代码")
                    elif not ifind_ok:
                        st.session_state["ifind_delta_msg"] = ("error",
                            "iFinD 未登录，请先在侧边栏登录 iFinD 终端")
                    else:
                        try:
                            fetched, err_msg = get_onsite_option_greeks(option_code.strip(), "delta")
                            if fetched is not None:
                                position_sign = 1 if tool_direction == "买入" else -1
                                position_delta = position_sign * float(fetched)
                                # 直接写入 number_input 的 key，触发界面刷新
                                st.session_state["new_option_delta"] = position_delta
                                st.session_state["ifind_delta_msg"] = ("success",
                                    f"合约 Delta = {fetched:.4f}, 头寸 Delta = {position_delta:.4f}，已填入下方输入框")
                            else:
                                st.session_state["ifind_delta_msg"] = ("error", err_msg)
                        except Exception as e:
                            st.session_state["ifind_delta_msg"] = ("error", f"获取异常：{e}")
            with col_btn2:
                if not ifind_ok:
                    st.caption("提示：请先在侧边栏登录 iFinD，再点击按钮获取 Delta")

            # 显示状态信息
            msg = st.session_state.get("ifind_delta_msg")
            if msg is not None:
                level, text = msg
                if level == "success":
                    st.success(text)
                elif level == "error":
                    st.error(text)
                else:
                    st.info(text)

            # ---- Delta 输入（带符号校验）----
            # 初始化默认值：仅在 session_state 中尚无此 key 时写入默认值
            if "new_option_delta" not in st.session_state:
                default_delta = DEFAULT_CONFIG['client']['atm_option_delta']
                if option_type == "看跌期权" and tool_direction == "买入":
                    default_delta = -default_delta
                elif option_type == "看涨期权" and tool_direction == "卖出":
                    default_delta = -default_delta
                st.session_state["new_option_delta"] = default_delta

            option_delta = st.number_input(
                "Delta（系数，如 0.50=50%）",
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
            hedge_contract_cn = st.selectbox("平盘合约类型", ["收益互换", "场外期权"])
            otc_hedge_contract_type = "equity_swap" if hedge_contract_cn == "收益互换" else "option"
            otc_payment = st.number_input("向平盘方支付预付金（万元）", value=0.0, key="new_otc_payment")
            pass_through_fee = st.number_input("平盘成本（年化%）", value=2.0, step=0.1, key="new_otc_fee")
            if otc_hedge_contract_type == "option":
                option_type = st.selectbox("平盘期权类型", ["看涨期权", "看跌期权"], key="otc_option_type")
                option_delta = st.number_input("平盘头寸Delta（带符号）", value=-0.5, step=0.05, key="otc_option_delta")
                if tool_direction == "卖出":
                    otc_stress_loss = st.number_input("平盘卖出期权±20%压力最大损失（万元）", value=tool_notional * 0.1)
            st.caption("用于有效对冲判定，填写被对冲合约的标的代码")
            otc_underlying_code = st.text_input("标的代码", placeholder="如：000300.SH", key="otc_underlying_code")

        else:  # 私募基金
            subscription_amount = st.number_input("申购金额（万元）", value=tool_notional)
            fund_structure_cn = st.selectbox("产品结构", ["一对一单一产品/SPV", "一对多集合产品"])
            fund_structure = "single_product" if fund_structure_cn.startswith("一对一") else "collective_product"
            asset_maturity_days = st.number_input("资产剩余期限（天；无法确定填0）", min_value=0, value=0, step=1)
            if asset_maturity_days == 0:
                asset_maturity_days = None
            if fund_structure == "single_product":
                lookthrough_pct = st.number_input("可穿透底层市场风险比例（%；未知填0）", min_value=0.0, max_value=100.0, value=0.0)
                fund_lookthrough_risk_rate = lookthrough_pct / 100 if lookthrough_pct > 0 else None
            fund_delta_value = st.number_input("经核验的组合Delta（系数；未知填0）", value=0.0, step=0.05)
            fund_delta = fund_delta_value if fund_delta_value != 0 else None

    if st.button("添加到对冲列表", key="add_hedge", type="primary"):
        # 校验：Delta 符号是否正确
        if not delta_valid:
            st.error(f"无法添加对冲工具：{delta_warning_msg}")
        else:
            hedge = {
                "tool_type": CN_TOOL_TYPE[tool_type],
                "direction": CN_HEDGE_DIRECTION[tool_direction],
                "notional": tool_notional,
                "underlying_type": CN_STOCK_TYPE.get(stock_type_value, "index_component") if stock_type_value else None,
                "underlying_market": "CN",
                "is_broad_based_etf": is_broad_based_etf,
                "underlying_name": None,
                "underlying_code": (etf_code or stock_code or future_ul_code or option_ul_code or otc_underlying_code or "").strip(),
                "tool_code": (option_code or "").strip(),
                "cash_spent": cash_spent,
                "futures_margin": futures_margin,
                "futures_margin_rate": futures_margin_rate / 100.0 if futures_margin_rate is not None else None,
                "future_delta": future_delta,
                "future_type": future_type,
                "option_premium": option_premium,
                "option_delta": option_delta,
                "option_type": CN_OPTION_TYPE.get(option_type),
                "option_margin": option_margin,
                "option_margin_rate": option_margin_rate / 100.0 if option_margin_rate is not None else None,
                "otc_payment": otc_payment,
                "pass_through_fee": pass_through_fee,
                "otc_hedge_contract_type": otc_hedge_contract_type,
                "otc_stress_loss": otc_stress_loss,
                "subscription_amount": subscription_amount,
                "fund_structure": fund_structure,
                "fund_lookthrough_risk_rate": fund_lookthrough_risk_rate,
                "asset_maturity_days": asset_maturity_days,
                "fund_delta": fund_delta,
                "stock_type": CN_STOCK_TYPE.get(stock_type_value) if stock_type_value else None,
            }
            target_list.append(hedge)
            st.success("对冲工具已成功添加")



@st.dialog("创建对冲方案", width="large")
def create_scheme_dialog():
    """弹窗创建新方案：填写方案名称并添加对冲工具。"""
    st.markdown("### 方案基本信息")
    scheme_name = st.text_input(
        "方案名称",
        placeholder="请输入方案名称，如：保守对冲方案",
        key="dialog_scheme_name",
        help="方案名称不能为空，且不能与已有方案重名",
    )

    if "dialog_temp_tools" not in st.session_state:
        st.session_state["dialog_temp_tools"] = []

    st.divider()

    with st.expander("新增对冲工具", expanded=True):
        render_tool_adder(st.session_state["dialog_temp_tools"])

    st.divider()

    st.markdown("### 当前方案工具列表")
    if st.session_state["dialog_temp_tools"]:
        st.dataframe(
            _hedge_tool_display_table(st.session_state["dialog_temp_tools"]),
            use_container_width=True,
        )
        for idx in range(len(st.session_state["dialog_temp_tools"])):
            st.button(
                f"删除 #{idx + 1}",
                key=f"dialog_del_tool_{idx}",
                on_click=_remove_temp_tool,
                args=(idx,),
            )
    else:
        st.info("暂未添加对冲工具")

    st.divider()

    col_confirm, col_cancel = st.columns([1, 1])
    with col_confirm:
        if st.button("确认创建方案", type="primary", key="dialog_confirm_scheme"):
            if not scheme_name or not scheme_name.strip():
                st.error("请输入方案名称")
            elif scheme_name in st.session_state["hedge_schemes"]:
                st.error(f"方案「{scheme_name}」已存在，请更换名称")
            else:
                st.session_state["hedge_schemes"][scheme_name] = list(st.session_state["dialog_temp_tools"])
                st.session_state["dialog_temp_tools"] = []
                st.success(f"已创建方案「{scheme_name}」")
                st.rerun()
    with col_cancel:
        if st.button("取消", key="dialog_cancel_scheme"):
            st.session_state["dialog_temp_tools"] = []
            st.rerun()


@st.dialog("编辑对冲方案", width="large")
def edit_scheme_dialog(scheme_name: str):
    """弹窗编辑已有方案：预载现有工具，支持增删并保存。"""
    st.markdown(f"### 编辑方案：{scheme_name}")

    if "dialog_temp_tools" not in st.session_state:
        st.session_state["dialog_temp_tools"] = []
    if st.session_state.get("dialog_edit_scheme") != scheme_name:
        # 首次进入编辑：把该方案现有工具载入临时列表
        st.session_state["dialog_temp_tools"] = list(st.session_state["hedge_schemes"].get(scheme_name, []))
        st.session_state["dialog_edit_scheme"] = scheme_name

    with st.expander("新增对冲工具", expanded=True):
        render_tool_adder(st.session_state["dialog_temp_tools"])

    st.divider()

    st.markdown("### 当前方案工具列表")
    if st.session_state["dialog_temp_tools"]:
        st.dataframe(
            _hedge_tool_display_table(st.session_state["dialog_temp_tools"]),
            use_container_width=True,
        )
        for idx in range(len(st.session_state["dialog_temp_tools"])):
            st.button(
                f"删除 #{idx + 1}",
                key=f"dialog_edit_del_tool_{idx}",
                on_click=_remove_temp_tool,
                args=(idx,),
            )
    else:
        st.info("该方案暂无对冲工具")

    st.divider()

    col_confirm, col_cancel = st.columns([1, 1])
    with col_confirm:
        if st.button("保存修改", type="primary", key="dialog_edit_confirm"):
            st.session_state["hedge_schemes"][scheme_name] = list(st.session_state["dialog_temp_tools"])
            st.session_state["dialog_temp_tools"] = []
            st.session_state["dialog_edit_scheme"] = None
            st.success(f"已保存方案「{scheme_name}」的修改")
            st.rerun()
    with col_cancel:
        if st.button("取消", key="dialog_edit_cancel"):
            st.session_state["dialog_temp_tools"] = []
            st.session_state["dialog_edit_scheme"] = None
            st.rerun()


@st.dialog("确认删除方案", width="small")
def confirm_delete_dialog(scheme_name: str):
    """确认删除方案的弹窗。"""
    st.warning(f"确定要删除方案「{scheme_name}」吗？")
    st.caption("此操作不可撤销，方案中的所有对冲工具将被一并删除。")

    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button("确认删除", type="primary", key="dialog_confirm_delete"):
            if scheme_name in st.session_state["hedge_schemes"]:
                del st.session_state["hedge_schemes"][scheme_name]
                st.success(f"已删除方案「{scheme_name}」")
                st.rerun()
    with col_cancel:
        if st.button("取消", key="dialog_cancel_delete"):
            st.rerun()


def render_single_scheme_result(scheme_name: str, result: dict, client, hedge_list: list) -> None:
    """单方案：完整三层指标展示（沿用原版结果页布局）。"""
    st.info(f"当前展示方案：**{scheme_name}**（对冲工具数：{len(hedge_list)} 个）")

    # ===== 第一层：现金流与资源消耗绝对值 =====
    with st.container(border=True):
        st.markdown("### 第一层：现金流与资源消耗绝对值")
        col1, col2, col3 = st.columns(3)
        col1.metric("首日净现金流", f"{result['net_day1_cash']:,.2f} 万元")
        col2.metric("新增风险资本准备", f"{result['new_risk_reserve']:,.2f} 万元")
        col3.metric("新增未来30日现金净流出", f"{result['net_cof_change']:,.2f} 万元")

    st.write("")

    # ===== 第二层：核心风控指标边际变动 =====
    with st.container(border=True):
        st.markdown("### 第二层：核心风控指标边际变动")
        col1, col2, col3, col4, col5 = st.columns(5)

        lcr_delta = result['lcr_change']
        col1.metric("流动性覆盖率（LCR）", _fmt_ratio(result['lcr_new']),
                    delta=f"{lcr_delta:+.2%}",
                    delta_color="inverse" if lcr_delta < 0 else "normal")
        col1.caption(f"原值: {_fmt_ratio(result['lcr_old'])} ｜ ≥100%")

        nsfr_delta = result['nsfr_change']
        col2.metric("净稳定资金比率（NSFR）", _fmt_ratio(result['nsfr_new']),
                    delta=f"{nsfr_delta:+.2%}",
                    delta_color="inverse" if nsfr_delta < 0 else "normal")
        col2.caption(f"原值: {_fmt_ratio(result['nsfr_old'])} ｜ ≥100%")

        lev_delta = result['leverage_change']
        col3.metric("资本杠杆率", _fmt_ratio(result['leverage_new']),
                    delta=f"{lev_delta:+.2%}",
                    delta_color="inverse" if lev_delta < 0 else "normal")
        col3.caption(f"原值: {_fmt_ratio(result['leverage_old'])} ｜ ≥8%")

        rc_delta = result['risk_coverage_change']
        col4.metric("风险覆盖率", _fmt_ratio(result['risk_coverage_new']),
                    delta=f"{rc_delta:+.2%}",
                    delta_color="inverse" if rc_delta < 0 else "normal")
        col4.caption(f"原值: {_fmt_ratio(result['risk_coverage_old'])} ｜ ≥100%")

        eq_delta = result['equity_scale_ratio_change']
        col5.metric("自营权益规模/净资本", _fmt_ratio(result['equity_scale_ratio_new']),
                    delta=f"{eq_delta:+.2%}", delta_color="inverse" if eq_delta > 0 else "normal")
        col5.caption(f"原值: {_fmt_ratio(result['equity_scale_ratio_old'])} ｜ ≤100%")

    st.write("")

    # ===== 第三层：动态性价比指标 =====
    with st.container(border=True):
        st.markdown("### 第三层：动态性价比指标")
        col1, col2, col3 = st.columns(3)
        col1.metric("ROC 资本收益率", _fmt_num(result['roc']),
                    help="预期创收 / 新增风险资本准备")
        col2.metric("RO-LCR 流动性创收率", _fmt_num(result['ro_lcr']),
                    help="预期创收 / max(0, Δ现金净流出 - ΔHQLA)")
        col3.metric("RO-NSFR 稳定资金创收率", _fmt_num(result['ro_nsfr']),
                    help="预期创收 / Δ所需稳定资金")

    st.write("")
    st.divider()

    # ===== 对冲有效性与业务合规判定 =====
    with st.container(border=True):
        st.subheader("对冲有效性与业务合规判定")
        st.info(f"对冲有效性: {'有效对冲' if result['is_effective_hedge'][0] else '未达有效对冲'}")
        if not result['is_effective_hedge'][0]:
            st.caption(f"未通过原因: {result['is_effective_hedge'][1]}")
        constraints = result["business_constraints"]
        for error in constraints["errors"]:
            st.error(f"业务范围错误：{error}")
        for warning in constraints["warnings"]:
            st.warning(warning)

    st.write("")

    # ===== 核心风控指标合规状态汇总 =====
    with st.container(border=True):
        st.subheader("核心风控指标状态汇总")
        status_cols = st.columns(5)
        status_cols[0].markdown(render_status_badge("流动性覆盖率", result['lcr_status']), unsafe_allow_html=True)
        status_cols[1].markdown(render_status_badge("净稳定资金比率", result['nsfr_status']), unsafe_allow_html=True)
        status_cols[2].markdown(render_status_badge("资本杠杆率", result['leverage_status']), unsafe_allow_html=True)
        status_cols[3].markdown(render_status_badge("风险覆盖率", result['risk_coverage_status']), unsafe_allow_html=True)
        status_cols[4].markdown(render_status_badge("自营权益规模", result['equity_scale_status']), unsafe_allow_html=True)

    st.write("")

    # ===== 详细明细与调试展开面板 =====
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        with st.expander("查看明细数据"):
            st.json(result)
    with col_exp2:
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


def render_multi_scheme_comparison(results: dict, client) -> None:
    """多方案：横向对比表格 + 性价比对比图 + 各方案明细。"""
    st.markdown("### 多方案对比")

    compare_data = []
    for name, item in results.items():
        result = item["result"]
        compare_data.append({
            "方案名称": name,
            "对冲工具数": len(item["hedge_list"]),
            "新增风险资本准备（万元）": f"{result['new_risk_reserve']:,.2f}",
            "首日净现金流（万元）": f"{result['net_day1_cash']:,.2f}",
            "新增表内外资产（万元）": f"{result['assets_change']:,.2f}",
            "新增30日净流出（万元）": f"{result['net_cof_change']:,.2f}",
            "LCR变动": f"{result['lcr_change']:+.2%}",
            "NSFR变动": f"{result['nsfr_change']:+.2%}",
            "资本杠杆率变动": f"{result['leverage_change']:+.2%}",
            "风险覆盖率变动": f"{result['risk_coverage_change']:+.2%}",
            "自营权益规模变动": f"{result['equity_scale_ratio_change']:+.2%}",
            "有效对冲": "是" if result["is_effective_hedge"][0] else "否",
            "未达有效对冲原因": result["is_effective_hedge"][1] if not result["is_effective_hedge"][0] else "-",
            "ROC（元/元）": _fmt_num(result["roc"]),
            "RO-LCR（元/元）": _fmt_num(result["ro_lcr"]),
            "RO-NSFR（元/元）": _fmt_num(result["ro_nsfr"]),
        })
    df_compare = pd.DataFrame(compare_data)
    df_compare.index = range(1, len(df_compare) + 1)
    st.dataframe(df_compare, use_container_width=True)

    # ===== 性价比对比柱状图（内置 st.bar_chart，无需额外图表依赖）=====
    st.markdown("#### 各方案性价比对比")
    chart_data = pd.DataFrame({
        "ROC 资本收益率": [item["result"]["roc"] if item["result"]["roc"] is not None else 0.0 for item in results.values()],
        "RO-LCR 流动性创收率": [item["result"]["ro_lcr"] if item["result"]["ro_lcr"] is not None else 0.0 for item in results.values()],
        "RO-NSFR 稳定资金创收率": [item["result"]["ro_nsfr"] if item["result"]["ro_nsfr"] is not None else 0.0 for item in results.values()],
    }, index=list(results.keys()))
    st.bar_chart(chart_data)

    # ===== 各方案详细明细 =====
    st.markdown("#### 各方案详细明细")
    for name, item in results.items():
        with st.expander(f"{name}（对冲工具数：{len(item['hedge_list'])}）"):
            st.json(item["result"])


st.set_page_config(page_title="场外衍生品风控影响测算系统", layout="wide")

# ========== 注入组件层美化 CSS（完全移除页面全局背景色覆盖，使用原生背景） ==========
st.markdown("""
<style>
/* 引入专业系统字体 */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* 全局字体 */
.stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* 标题样式 */
h1, h2, h3 {
    font-weight: 700 !important;
    letter-spacing: -0.01em;
}

/* Tab 选项卡样式 */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    padding: 4px;
}

.stTabs [data-baseweb="tab"] {
    height: 40px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.95rem;
    padding: 0 20px;
    transition: all 0.2s ease;
}

/* 按钮样式提升 */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.15s ease-in-out !important;
}

.stButton > button[kind="primary"] {
    background: #2563eb !important;
    border: none !important;
    color: #ffffff !important;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
    font-size: 1rem !important;
}

.stButton > button[kind="primary"]:hover {
    background: #1d4ed8 !important;
    box-shadow: 0 6px 16px rgba(37, 99, 235, 0.38) !important;
    transform: translateY(-1px);
}

/* 状态徽章 */
.status-badge-safe {
    background-color: rgba(34, 197, 94, 0.1);
    border: 1px solid rgba(34, 197, 94, 0.4);
    color: #166534;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: center;
    font-weight: 600;
    font-size: 0.92rem;
}

.status-badge-warning {
    background-color: rgba(245, 158, 11, 0.1);
    border: 1px solid rgba(245, 158, 11, 0.4);
    color: #92400e;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: center;
    font-weight: 600;
    font-size: 0.92rem;
}

.status-badge-danger {
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.4);
    color: #991b1b;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: center;
    font-weight: 600;
    font-size: 0.92rem;
}

[data-theme="dark"] .status-badge-safe {
    color: #4ade80;
}
[data-theme="dark"] .status-badge-warning {
    color: #fbbf24;
}
[data-theme="dark"] .status-badge-danger {
    color: #f87171;
}
</style>
""", unsafe_allow_html=True)

st.title("场外衍生品业务风控影响测算系统")
st.markdown("---")

# ========== 侧边栏 ==========
with st.sidebar:
    with st.container(border=True):
        st.header("iFinD 数据终端登录")
        st.caption("有效对冲判定（标的相关性）与场内期权 Greeks 自动回填需要登录 iFinD")

        if "ifind_user_name" not in st.session_state:
            st.session_state["ifind_user_name"] = ""
        if "ifind_password" not in st.session_state:
            st.session_state["ifind_password"] = ""

        status = get_ifind_login_status()
        if status["logged_in"]:
            st.info(f"iFinD 状态：已登录 ({status['user_name']})")
            if st.button("登出 iFinD", key="ifind_logout_btn", use_container_width=True):
                ifind_logout()
                clear_ifind_credentials()
                st.session_state["ifind_user_name"] = ""
                st.session_state["ifind_password"] = ""
                st.success("已登出并清空凭据")
                st.rerun()
        else:
            ifind_user = st.text_input(
                "iFinD 账号",
                value=st.session_state["ifind_user_name"],
                key="ifind_user_input",
                placeholder="请输入iFinD账号",
            )
            ifind_pwd = st.text_input(
                "iFinD 密码",
                value=st.session_state["ifind_password"],
                key="ifind_pwd_input",
                type="password",
                placeholder="请输入密码",
            )
            st.session_state["ifind_user_name"] = ifind_user
            st.session_state["ifind_password"] = ifind_pwd

            login_col, logout_col = st.columns(2)
            with login_col:
                if st.button("登录 iFinD", key="ifind_login_btn", use_container_width=True):
                    if ifind_user and ifind_pwd:
                        set_ifind_credentials(ifind_user, ifind_pwd)
                        ok = ifind_login(force=True)
                        if ok:
                            st.success("iFinD 登录成功")
                            st.rerun()
                        else:
                            st.error("iFinD 登录失败，请检查账号密码及终端状态")
                    else:
                        st.warning("请先填写账号和密码")
            with logout_col:
                if st.button("登出 iFinD", key="ifind_logout_btn", use_container_width=True):
                    ifind_logout()
                    clear_ifind_credentials()
                    st.session_state["ifind_user_name"] = ""
                    st.session_state["ifind_password"] = ""
                    st.success("已登出并清空凭据")
                    st.rerun()

            st.caption("iFinD 状态：未登录")

    st.divider()

    with st.expander("公司基准参数", expanded=False):
        st.session_state['firm_params'] = {
            "HQLA_base": st.number_input("当前HQLA总额（万元）", value=DEFAULT_CONFIG["firm"]["HQLA_base"]/10000, step=10000.00),
            "HQLA_equity_raw_base": st.number_input("其中：指数成份股/宽基ETF折算前可计入额（万元）", value=DEFAULT_CONFIG["firm"]["HQLA_equity_raw_base"]/10000, step=1000.00),
            "LCR_outflow_base": st.number_input("当前LCR未来30日毛流出（万元）", value=DEFAULT_CONFIG["firm"]["LCR_outflow_base"]/10000, step=10000.00),
            "LCR_inflow_base": st.number_input("当前LCR未来30日毛流入（万元）", value=DEFAULT_CONFIG["firm"]["LCR_inflow_base"]/10000, step=10000.00),
            "ASF_base": st.number_input("当前ASF总额（万元）", value=DEFAULT_CONFIG["firm"]["ASF_base"]/10000, step=10000.00),
            "RSF_base": st.number_input("当前RSF总额（万元）", value=DEFAULT_CONFIG["firm"]["RSF_base"]/10000, step=10000.00),
            "net_capital_base": st.number_input("当前净资本（万元）", value=DEFAULT_CONFIG["firm"]["net_capital_base"]/10000, step=10000.00),
            "core_net_capital_base": st.number_input("当前核心净资本（万元）", value=DEFAULT_CONFIG["firm"]["core_net_capital_base"]/10000, step=10000.00),
            "total_risk_reserve_base": st.number_input("当前风险资本准备（万元）", value=DEFAULT_CONFIG["firm"]["total_risk_reserve_base"]/10000, step=10000.00),
            "self_operated_equity_scale_base": st.number_input("当前自营权益类证券及衍生品规模（万元）", value=DEFAULT_CONFIG["firm"]["self_operated_equity_scale_base"]/10000, step=10000.00),
            "on_off_balance_total_asset_base": st.number_input("当前表内外资产总额（万元）", value=DEFAULT_CONFIG["firm"]["on_off_balance_total_asset_base"]/10000, step=10000.00),
            "classification_factor": st.selectbox(
                "风险资本准备分类调整系数",
                [0.4, 0.6, 0.8, 0.9, 1.0, 2.0],
                index=4,
                format_func=lambda x: {
                    0.4: "连续三年A类且AA级以上（0.4）",
                    0.6: "连续三年A类（0.6）",
                    0.8: "A类（0.8）",
                    0.9: "B类（0.9）",
                    1.0: "C类（1.0）",
                    2.0: "D类（2.0）",
                }[x],
            ),
            "asset_adjustment_factor": st.selectbox(
                "表内外资产总额分类调整系数",
                [0.7, 0.9, 1.0],
                index=2,
                format_func=lambda x: {
                    0.7: "连续三年A类且AA级以上（0.7）",
                    0.9: "连续三年A类（0.9）",
                    1.0: "其他（1.0）",
                }[x],
            ),
            "asf_rating_factor": st.selectbox(
                "6-12个月不可提前偿还负债ASF折算率",
                [0.20, 0.10, 0.00],
                index=2,
            ),
            "operational_risk_recognition_weight": st.selectbox("预计收入进入三年均值的权重", [0.0, 1/3, 2/3, 1.0], index=0, format_func=lambda x: {0.0:"当前快照（0）",1/3:"进入1个年度（1/3）",2/3:"进入2个年度（2/3）",1.0:"稳定期（1）"}[x]),
        }

# ========== 主区域 ==========
tab1, tab2, tab3 = st.tabs(["模块A：客户端场外合约", "模块B：交易端（对冲工具）", "模块C：计算结果与测算展示"])

with tab1:
    st.subheader("客户端场外合约业务要素")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        
        with col1:
            contract_type = st.selectbox("业务类型", ["场外期权", "收益互换", "收益凭证"])
            direction_options = ["多头", "空头"] if contract_type == "收益互换" else ["发行"] if contract_type == "收益凭证" else ["买入", "卖出"]
            direction = st.selectbox("交易方向", direction_options)
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
                    st.info(f"合约期限：**{term_days} 天**（约 {term_days/30:.1f} 个月）")
                else:
                    st.warning("到期日必须晚于起始日，请重新选择")
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
            underlying_instrument = "index"
            has_embedded_option = False
            embedded_option_notional = None

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
                    st.caption("提示：压力损失 = 标的资产价格±20%的极端情况下，当前期权持仓的最大亏损")
                    stress_loss = st.number_input("压力损失（万元）", value=notional * 0.1, step=10.0)


            elif contract_type == "收益互换":
                margin_rate = st.number_input("保证金/预付金比例（%）", min_value=0.0, max_value=100.0, value=10.0, step=0.5)
                delta_amount = None
                stress_loss = None

            else:  # 收益凭证
                funds_raised = st.number_input("募集资金总额（万元）", value=notional, step=100.0)
                delta_amount = None
                certificate_structure = st.selectbox("凭证结构", ["固定收益凭证", "含内嵌权益期权"])
                has_embedded_option = certificate_structure == "含内嵌权益期权"
                if has_embedded_option:
                    embedded_option_notional = st.number_input("内嵌期权实际名义金额（万元）", value=notional, step=100.0)
                    stress_loss = st.number_input("内嵌期权±20%压力最大损失（万元）", value=notional * 0.1, step=10.0)

    # ---- 标的资产信息（所有产品类型共用）----
    with st.container(border=True):
        st.caption("标的资产代码用于有效对冲判定：填写后系统将通过代码判定标的一致性；留空则按最保守方式估算")
        underlying_code = st.text_input("标的代码", placeholder="如：000300.SH", key="client_ul_code")
        if contract_type != "收益凭证" or has_embedded_option:
            instrument_cn = st.selectbox("标的形态", ["境内指数", "境内ETF", "境内个股"])
            underlying_instrument = {"境内指数": "index", "境内ETF": "etf", "境内个股": "stock"}[instrument_cn]
            underlying_type = "general_stock" if underlying_instrument == "stock" else "index_component"

    # ---- 场外期权压力损失估算辅助字段 ----
    option_margin_amount = None
    option_margin_rate = None
    exercise_price = None
    contract_multiplier = None
    contract_size = None
    if "期权" in contract_type and direction == "卖出":
        st.caption("场外保证金不能直接按交易所期货（期权）保证金100%扣减净资本；需另行确认会计科目。")
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
        "underlying_instrument": underlying_instrument,
        "underlying_market": "CN",
        "underlying_name": None,
        "underlying_code": (underlying_code or "").strip(),
        "option_type": CN_OPTION_TYPE[client_option_type] if client_option_type else None,
        "premium_rate": premium_rate,
        "margin_rate": margin_rate,
        "funds_raised": funds_raised,
        "has_embedded_option": has_embedded_option,
        "embedded_option_notional": embedded_option_notional,
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
    st.subheader("对冲方案管理")

    with st.expander("标的资产分类与扣减规则"):
        st.markdown(textwrap.dedent("""
        | 资产分类 | 市场风险资本准备 | NSFR RSF | HQLA折算率 |
        |---|---|---|---|
        | **宽基股票指数ETF** | 指数基金5% | 10% | 50%（另受HQLA 15%上限约束） |
        | **其他权益ETF** | 其他权益类基金10% | 20% | 0% |
        | **指数成份股** | 8% | 30% | 50%（另受HQLA 15%上限约束） |
        | **一般/受限/其他股票** | 25%/50%/80% | 50%/100%/100% | 0% |
        """))
        st.caption("个股现货仅可用于ETF标的场外期权，并须按股票篮子整体相关性与组合Delta验证有效对冲；用于对冲权益互换的证券不计入HQLA。")

    if "hedge_schemes" not in st.session_state:
        st.session_state["hedge_schemes"] = {}

    col_add, col_hint = st.columns([1, 5])
    with col_add:
        if st.button("新建方案", type="primary", key="add_scheme_btn"):
            st.session_state["dialog_temp_tools"] = []
            create_scheme_dialog()

    st.divider()

    if not st.session_state["hedge_schemes"]:
        st.info("暂无对冲方案，点击「新建方案」创建第一个方案")
    else:
        for scheme_name, tools in st.session_state["hedge_schemes"].items():
            with st.container(border=True):
                st.markdown(f"#### {scheme_name}")
                st.caption(f"对冲工具：{len(tools)} 个")
                if tools:
                    st.dataframe(_hedge_tool_display_table(tools), use_container_width=True)
                else:
                    st.caption("（该方案暂无对冲工具）")
                col_b1, col_b2, _ = st.columns([1, 1, 6])
                with col_b1:
                    if st.button("编辑", key=f"edit_{scheme_name}"):
                        edit_scheme_dialog(scheme_name)
                with col_b2:
                    if st.button("删除", key=f"del_{scheme_name}"):
                        confirm_delete_dialog(scheme_name)

with tab3:
    st.subheader("计算结果")
    cp = st.session_state.get('client_params')
    if not cp:
        st.error("请先在「模块A：客户端场外合约」填写业务信息")
    else:
        scheme_names = list(st.session_state.get('hedge_schemes', {}).keys())
        if not scheme_names:
            st.info("请先在「模块B：对冲方案」中创建方案")
        else:
            selected_schemes = st.multiselect(
                "选择要计算的对冲方案",
                scheme_names,
                help="可多选，系统将平行展示各方案的计算结果",
            )
            if not selected_schemes:
                st.info("请至少选择一个方案")
            else:
                if st.button("计算业务影响", type="primary", use_container_width=True):
                    # 将侧边栏修改后的公司基准参数同步到 DEFAULT_CONFIG（万元 → 元）
                    firm_params = st.session_state.get('firm_params', {})
                    for key, value in firm_params.items():
                        if key in ("classification_factor", "asset_adjustment_factor", "asf_rating_factor", "operational_risk_recognition_weight"):
                            DEFAULT_CONFIG["firm"][key] = value
                        elif isinstance(value, (int, float)):
                            DEFAULT_CONFIG["firm"][key] = value * 10000

                    client = ClientContract(**cp)
                    results = {}
                    for name in selected_schemes:
                        tools = st.session_state["hedge_schemes"].get(name, [])
                        hedge_list = [HedgeTrade(**h) for h in tools]
                        result = analyze_contract(client, hedge_list)
                        results[name] = {"result": result, "hedge_list": hedge_list}

                    if len(results) == 1:
                        # 单方案：完整三层指标展示（沿用原版布局）
                        name, item = next(iter(results.items()))
                        render_single_scheme_result(name, item["result"], client, item["hedge_list"])
                    else:
                        # 多方案：横向对比表格 + 性价比对比图 + 各方案明细
                        render_multi_scheme_comparison(results, client)
