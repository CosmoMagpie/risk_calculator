# ============================================================
# backend/models/hedge_trade.py - 模块B：交易端对冲工具数据模型
# ============================================================

from typing import Optional
from dataclasses import dataclass

from ..config import DEFAULT_CONFIG


# ===================== 模块B：交易端对冲工具 =====================
# 【业务含义】HedgeTrade 代表交易台为了对冲客户端风险而进行的单笔交易
#   当券商与客户做了一笔衍生品交易（OtcContract）后，会在市场上建立反向头寸
#   来对冲掉方向性风险，HedgeTrade 就是这个反向头寸。
#
#   支持的六种对冲工具（tool_type）：
#     "etf"        — ETF现货（如买入50ETF对冲卖出看跌期权的风险）
#     "stock"      — 个股现货
#     "futures"    — 股指期货（如做空IF对冲Delta敞口）
#     "onsite_option" — 场内期权（交易所标准期权）
#     "otc_hedge"  — 场外背对背对冲（找另一家机构做反向交易平盘）
#     "private_fund"  — 私募基金（结构化对冲方案的一部分）
# ============================================================
@dataclass
class HedgeTrade:
    """对应模块B：对冲工具"""

    # ===== 基础字段（所有对冲工具通用） =====
    tool_type: str              # 工具类型字符串："etf" | "stock" | "futures" | "onsite_option" | "otc_hedge" | "private_fund"
    direction: str              # 交易方向："long"=做多（买入） | "short"=做空（卖出）
    notional: float             # 名义价值/对冲总金额（万元）
    tool_code: Optional[str] = None  # 对冲工具 iFinD 代码（用于查价格、获取Greeks）

    # ===== 标的资产属性 =====
    underlying_type: Optional[str] = None  # 底层资产类型（如 index_component），ETF/股票时即为tool_type本身
    underlying_name: Optional[str] = None  # 对冲工具底层资产名称
    underlying_code: Optional[str] = None  # 对冲工具底层资产代码（用于查价格、算相关性）

    # ===== ETF现货字段 =====
    cash_spent: Optional[float] = None     # ETF买入实际花费现金（万元），未指定时默认=名义金额

    # ===== 股票现货字段 =====
    stock_type: Optional[str] = None       # 股票类型：index_component | general_stock | restricted_stock | other_stock

    # ===== 期货字段 =====
    futures_margin: Optional[float] = None      # 股指期货保证金绝对值（万元）
    futures_margin_rate: Optional[float] = None  # 股指期货保证金比例（%），如12%
    future_type: Optional[str] = None           # 期货类型（如 "IF"=沪深300, "IC"=中证500）
    future_delta: Optional[float] = None        # 期货Delta值（%），股指期货通常≈100%

    # ===== 场内期权字段 =====
    option_premium: Optional[float] = None   # 场内期权权利金（万元），买入期权支付的权利金
    option_type: Optional[str] = None        # 期权类型："call_option"=看涨 | "put_option"=看跌
    option_strike_price: Optional[float] = None  # 期权执行价（元）
    option_start_date: Optional[str] = None      # 期权起始日（"YYYY-MM-DD"）
    option_expiry_date: Optional[str] = None     # 期权到期日（"YYYY-MM-DD"）
    option_delta: Optional[float] = None         # Delta值（%）
    option_margin: Optional[float] = None        # 期权保证金金额（万元），卖出期权时需要缴纳保证金
    option_margin_rate: Optional[float] = None   # 期权保证金比例（%）

    # ===== 场外背对背对冲字段 =====
    # 【业务场景】券商与客户做了一笔场外期权后，找另一家金融机构做一笔完全反向的交易
    #           来转移风险，这称为"背对背平盘"（back-to-back hedging）
    otc_payment: Optional[float] = None         # 向平盘方支付的预付金/保证金（万元）
    pass_through_fee: Optional[float] = None    # 平盘成本（年化%），即支付给平盘方的费率

    # ===== 私募基金字段 =====
    subscription_amount: Optional[float] = None # 私募基金申购金额（万元）

    # ================================================================
    # getter 方法与核心业务逻辑
    # ================================================================

    def get_trade_cash_outflow(self) -> float:
        """
        计算交易端首日现金净流出（万元，正值=现金从券商流出）

        【与 OtcContract.get_otc_cash_inflow 对应】
          客户端流入 + 交易端流出 = 净现金流，二者正负号定义相反：
          客户端：正值=流入券商（收钱）
          交易端：正值=流出券商（花钱）

        【各类工具的现金计算逻辑】
          ETF/股票：做多=全款买入(流出)，做空=融券卖出(流入)
          期货：只占用保证金（双向都流出），不分多空
          场内期权：买入付权利金(流出)，卖出收权利金(流入)
          场外背对背：预付金 + 年化平盘成本按期限折算
          私募基金：申购金额直接流出
        """
        # --- ETF：做多全款买入，做空获得现金 ---
        if self.tool_type == "etf":
            if self.cash_spent is not None:
                return self.cash_spent if self.direction == "long" else -self.cash_spent
            else:
                return self.notional if self.direction == "long" else -self.notional

        # --- 股票：同上 ---
        elif self.tool_type == "stock":
            return self.notional if self.direction == "long" else -self.notional

        # --- 期货：保证金占用（不分多空方向，都需缴纳保证金）---
        elif self.tool_type == "futures":
            if self.futures_margin is not None:
                return self.futures_margin  # 直接给定保证金金额
            rate = self.futures_margin_rate if self.futures_margin_rate is not None else DEFAULT_CONFIG["trade"]["futures_margin_rate"]
            return self.notional * rate    # 名义价值 × 保证金比例

        # --- 场内期权：买入付权利金(+) / 卖出收权利金(-) ---
        elif self.tool_type == "onsite_option":
            if self.option_premium is not None:
                return self.option_premium if self.direction == "long" else -self.option_premium
            premium = self.notional * DEFAULT_CONFIG["trade"]["onsite_option_premium_rate"]  # 默认2%
            return premium if self.direction == "long" else -premium

        # --- 场外背对背对冲：预付金 + 平盘成本 ---
        elif self.tool_type == "otc_hedge":
            total = self.otc_payment if self.otc_payment is not None else 0.0
            if self.pass_through_fee is not None:
                # 平盘成本 = 名义本金 × 平盘成本率 × (期限/365)，默认90天
                total += self.notional * self.pass_through_fee / 100 * (90 / 365)
            return total

        # --- 私募基金：申购金额流出 ---
        elif self.tool_type == "private_fund":
            return self.subscription_amount if self.subscription_amount is not None else 0.0

        return 0.0

    def get_tool_type(self) -> str:
        """获取对冲工具类型"""
        return self.tool_type

    def get_tool_notional(self) -> float:
        """获取对冲工具名义价值（万元）"""
        return self.notional

    def get_tool_direction(self) -> str:
        """获取对冲工具方向"""
        return self.direction

    def get_tool_code(self) -> str:
        """获取对冲工具 iFinD 代码"""
        return self.tool_code

    def get_tool_stock_type(self) -> Optional[str]:
        """获取对冲工具股票类型"""
        return self.stock_type if self.stock_type is not None else None

    def get_tool_underlying_name(self) -> str:
        """获取对冲工具底层资产名称"""
        return self.underlying_name

    def get_tool_underlying_code(self) -> str:
        """获取对冲工具底层资产代码"""
        return self.underlying_code

    def get_cash_spent(self) -> Optional[float]:
        """获取ETF买入实际花费现金（万元）"""
        return self.cash_spent

    def get_futures_margin(self) -> Optional[float]:
        """获取期货保证金金额（万元）"""
        return self.futures_margin

    def get_futures_margin_rate(self) -> Optional[float]:
        """获取期货保证金比例（%）"""
        return self.futures_margin_rate
    
    def get_option_premium(self) -> Optional[float]:
        """获取期权权利金（万元）"""
        return self.option_premium

    def get_option_type(self) -> Optional[str]:
        """获取期权类型"""
        return self.option_type

    def get_option_strike_price(self) -> Optional[float]:
        """获取期权执行价（元）"""
        return self.option_strike_price

    def get_option_start_date(self) -> Optional[str]:
        """获取期权起始日（"YYYY-MM-DD"）"""
        return self.option_start_date

    def get_option_expiry_date(self) -> Optional[str]:
        """获取期权到期日（"YYYY-MM-DD"）"""
        return self.option_expiry_date

    def get_option_delta(self) -> Optional[float]:
        """获取期权Delta值（%）"""
        return self.option_delta

    def get_option_margin(self) -> Optional[float]:
        """获取期权保证金金额（万元）"""
        return self.option_margin

    def get_option_margin_rate(self) -> Optional[float]:
        """获取期权保证金比例（%）"""
        return self.option_margin_rate

    def get_otc_payment(self) -> Optional[float]:
        """获取场外背对背对冲预付金（万元）"""
        return self.otc_payment

    def get_pass_through_fee(self) -> Optional[float]:
        """获取场外背对背对冲平盘成本（年化%）"""
        return self.pass_through_fee

    def get_subscription_amount(self) -> Optional[float]:
        """获取私募基金申购金额（万元）"""
        return self.subscription_amount
    
    def get_hedge_delta_amount(self) -> Optional[float]:
        """
        获取对冲工具的Delta敞口金额（万元）

        【设计思路】与 OtcContract.get_otc_delta_amount 镜像对应
          客户端Delta + 对冲端Delta → 判断是否构成有效对冲
        """
        is_long = 1 if self.direction == "long" else -1

        # --- 场内期权Delta ---
        if self.tool_type == "onsite_option":
            is_call = 1 if self.option_type == "call_option" else -1
            if self.option_delta is not None:
                return self.option_delta * self.notional
            # ⚠️ 注意："onsite_option_delta" key 在 DEFAULT_CONFIG["trade"] 中不存在，实际key是 "atm_option_delta"
            return DEFAULT_CONFIG["trade"]["onsite_option_delta"] * self.notional * is_call * is_long

        # --- 期货Delta ---
        elif "futures" in self.tool_type:
            if self.future_delta is not None:
                return self.future_delta * self.notional
            return DEFAULT_CONFIG["trade"]["future_delta"] * self.notional * is_long

        # --- ETF/股票：Delta直接等于名义价值 ---
        elif self.tool_type == "etf" or self.tool_type == "stock":
            return self.notional if self.direction == "long" else -self.notional

        return None
