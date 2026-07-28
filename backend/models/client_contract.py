# ============================================================
# backend/models/client_contract.py - 模块A：场外衍生品合约数据模型
# ============================================================

import numpy as np          # 科学计算库，这里主要用于 np.nan（表示"非数字"）
import pandas as pd         # 数据分析库，这里用于价格序列的相关性计算（pd.Series）
import random               # 随机数库
from datetime import datetime, timedelta  # 日期时间处理
from typing import Dict, Any, Optional, List  # 类型注解工具
from dataclasses import dataclass, field       # 数据类装饰器，自动生成构造函数等
import math                 # 数学函数库

from ..config import DEFAULT_CONFIG


# ===================== 模块A：场外衍生品合约（OtcContract） =====================
# 【Python语法】@dataclass 是装饰器，放在 class 上一行，自动生成：
#   - __init__(self, ...)：构造函数，按字段顺序接收参数
#   - __repr__(self)：打印对象时的可读表示
#   省去了手写大量样板代码。字段后带 =None 或 =默认值 的是可选参数
#
# 【业务含义】OtcContract 代表股衍部与客户签订的一笔场外衍生品合约
#   支持的四种业务类型（contract_type）：
#     "call_option"   — 场外看涨期权
#     "put_option"    — 场外看跌期权
#     "equity_swap"   — 收益互换（客户与券商互换股票收益与固定收益）
#     "income_certificate" — 收益凭证（券商发行的结构化融资工具）
#   交易方向（direction）：
#     期权："buy"=买入 / "short"=卖出（券商视角）
#     互换："long"=多头 / "short"=空头（券商视角）
# ============================================================
@dataclass
class OtcContract:
    """对应模块A：场外衍生品业务要素"""

    # ===== 基础信息（所有合约类型通用） =====
    contract_type: str          # 合约类型字符串："call_option" | "put_option" | "equity_swap" | "income_certificate"
    direction: str              # 券商视角方向："buy"/"short"（期权）或 "long"/"short"（互换）
    notional: float             # 名义本金/发行规模（单位：万元）。对期权=名义本金，对收益凭证=发行规模

    # ===== 标的资产属性 =====
    underlying_type: str        # 标的资产分类，影响风险系数：index_component/general_stock/restricted_stock/other_stock
    underlying_name: Optional[str] = None  # 标的资产名称（如"中证1000"），可选
    underlying_code: Optional[str] = None  # 标的资产代码（如"000852"），可选，用于查价格算相关性

    # ===== 期权专有字段 =====
    # 【设计思路】不同合约类型用不同字段，未使用的字段保持 None
    #           这是"宽表"设计——所有字段放一起，用类型区分哪些字段有效
    option_type: Optional[str] = None        # 期权类型："call_option"=看涨 | "put_option"=看跌
    premium_rate: Optional[float] = None        # 权利金比例（%），如5表示5%，权利金 = 名义本金 × 权利金比例
    total_premium_amount: Optional[float] = None # 权利金总额（万元），直接指定总额时使用
    single_premium_amount: Optional[float] = None # 单笔期权费（万元），配合合约份数使用
    contract_multiplier: Optional[float] = None # 合约乘数（元/点），类似股指期权每点对应多少元
    contract_size: Optional[float] = None       # 合约份数（份）
    exercise_price: Optional[float] = None      # 行权价（元）
    option_delta: Optional[float] = None        # Delta值（%），如0.5=50%，用于计算Delta敞口
    option_margin_amount: Optional[float] = None # 场外卖出期权保证金绝对值（万元）
    option_margin_rate: Optional[float] = None   # 场外卖出期权保证金比例（%）
    stress_loss: Optional[float] = None         # 压力测试最大损失（万元），卖出场外期权专用

    # ===== 收益互换专有字段 =====
    margin_rate: Optional[float] = None         # 保证金比例（%），如10表示客户缴纳10%保证金
    margin_amount: Optional[float] = None       # 保证金绝对值（万元），与margin_rate二选一
    equity_swap_delta: Optional[float] = None          # 互换Delta值（%），通常为100%

    # ===== 收益凭证专有字段 =====
    funds_raised: Optional[float] = None        # 募集资金总额（万元），收益凭证的实际融资额
    income_certificate_delta: Optional[float] = None      # OC Delta值（%），收益凭证通常为0（无权益敞口）

    # ===== 通用字段：预期创收与期限 =====
    expected_yield: float = 0.08                # 预期年化收益率（小数），0.08=8%，用于计算预期创收
    expiry_date: Optional[str] = None           # 合约到期日（"YYYY-MM-DD"格式）
    begin_date: Optional[str] = None            # 合约起始日（"YYYY-MM-DD"格式）
    term_days: int = 90                         # 合约期限（天），默认90天≈3个月

    # ================================================================
    # 以下是一系列 getter 方法（getter = 获取属性值的访问器方法）
    # 【Python语法】def method(self) -> type: 中 self 代表实例自身，必须显式写出
    # 【设计思路】虽然 dataclass 可以直接 obj.field 访问字段，但组员写了这些 getter，
    #           可能是为了：①统一接口风格  ②后续方便在方法内加校验逻辑
    #           ③如果要对接框架（如 ORM），getter 模式更通用
    # ================================================================
    def get_otc_contract_type(self) -> str:
        """获取合约类型"""
        return self.contract_type

    def get_otc_contract_direction(self) -> str:
        """获取交易方向"""
        return self.direction

    def get_otc_contract_notional(self) -> float:
        """获取名义本金"""
        return self.notional

    def get_otc_underlying_type(self) -> str:
        """获取标的资产类型"""
        return self.underlying_type

    def get_otc_underlying_name(self) -> Optional[str]:
        """获取标的资产名称"""
        return self.underlying_name

    def get_otc_underlying_code(self) -> Optional[str]:
        """获取标的资产代码"""
        return self.underlying_code

    def get_option_type(self) -> Optional[str]:
        """获取期权类型"""
        return self.option_type

    def get_premium_rate(self) -> Optional[float]:
        """获取权利金比例"""
        return self.premium_rate

    def get_total_premium_amount(self) -> Optional[float]:
        """获取权利金总额"""
        return self.total_premium_amount

    def get_single_premium_amount(self) -> Optional[float]:
        """获取单笔期权费"""
        return self.single_premium_amount

    def get_contract_size(self) -> Optional[float]:
        """获取合约份数"""
        return self.contract_size

    def get_contract_multiplier(self) -> Optional[float]:
        """获取合约乘数"""
        return self.contract_multiplier

    def get_exercise_price(self) -> Optional[float]:
        """获取行权价"""
        return self.exercise_price

    def get_option_delta(self) -> Optional[float]:
        """获取期权Delta值"""
        return self.option_delta

    def get_stress_loss(self) -> Optional[float]:
        """获取压力测试最大损失"""
        return self.stress_loss

    def get_option_margin_amount(self) -> Optional[float]:
        """获取场外卖出期权保证金（万元）"""
        return self.option_margin_amount

    def get_option_margin_rate(self) -> Optional[float]:
        """获取场外卖出期权保证金比例（%）"""
        return self.option_margin_rate

    def get_margin_rate(self) -> Optional[float]:
        """获取互换保证金比例"""
        return self.margin_rate

    def get_margin_amount(self) -> Optional[float]:
        """获取互换保证金"""
        return self.margin_amount

    def get_equity_swap_delta(self) -> Optional[float]:
        """获取收益互换Delta值"""
        return self.equity_swap_delta

    def get_funds_raised(self) -> Optional[float]:
        """获取募集资金总额"""
        return self.funds_raised

    def get_income_certificate_delta(self) -> Optional[float]:
        """获取OC Delta值"""
        return self.income_certificate_delta

    def get_income_certificate_rate(self) -> Optional[float]:
        """获取收益凭证票面利率（%），约定 > 硬编码"""
        return DEFAULT_CONFIG["client"]["income_certificate_rate"]

    def get_expected_yield(self) -> float:
        """获取预期年化收益率"""
        return self.expected_yield

    def get_expiry_date(self) -> Optional[str]:
        """获取合约到期日"""
        return self.expiry_date

    def get_begin_date(self) -> Optional[str]:
        """获取合约起始日"""
        return self.begin_date

    def get_term_days(self) -> int:
        """获取合约期限（天）"""
        return self.term_days

    # ================================================================
    # 以下是核心业务逻辑方法（有别于上面的简单 getter，这些包含实际计算）
    # ================================================================

    def get_otc_cash_inflow(self) -> float:
        """
        计算场外合约首日现金净流入（万元，正值=现金流入券商，负值=流出）

        【业务场景】券商与客户签约后，首日发生的现金变动：
          - 卖出期权：券商收取权利金 → 正值（现金流入）
          - 买入期权：券商支付权利金 → 负值（现金流出）
          - 空头互换：券商收取客户保证金 → 正值
          - 多头互换：券商向客户支付保证金 → 负值
          - 收益凭证：券商募集资金 → 正值（融资入账）

        【Python语法】if/elif/else 条件分支；self.xxx 访问实例属性；
                       is not None 判空；三元表达式 X if 条件 else Y
        """
        # --- 期权：权利金计算有三级优先级 ---
        if (self.contract_type == "call_option" or self.contract_type == "put_option"):
            if self.total_premium_amount is not None:
                premium = self.total_premium_amount                    # 优先级1：直接指定总额
            elif self.single_premium_amount is not None and self.contract_size is not None:
                premium = self.single_premium_amount * self.contract_size  # 优先级2：单笔×份数
            elif self.premium_rate is not None:
                premium = self.notional * self.premium_rate / 100     # 优先级3：名义本金×比例
            else:
                premium = self.notional * DEFAULT_CONFIG["client"]["option_premium_rate"]  # 兜底：默认5%
            return premium if self.direction == "short" else -premium  # 卖出收权利金(+)，买入付权利金(-)

        # --- 收益互换：保证金流入/流出 ---
        elif self.contract_type == "equity_swap":
            if self.margin_rate is not None:
                # 保证金 = 名义本金 × 保证金比例
                return self.notional * self.margin_rate / 100 if self.direction == "short" else -self.notional* self.margin_rate / 100
            elif self.margin_amount is not None:
                return self.margin_amount if self.direction == "short" else -self.margin_amount
            # 兜底：默认10%保证金
            return self.notional * DEFAULT_CONFIG["client"]["swap_margin_rate"] if self.direction == "short" else -self.notional * DEFAULT_CONFIG["client"]["swap_margin_rate"]

        # --- 收益凭证：募集资金全部流入 ---
        elif self.contract_type == "income_certificate":
            return self.funds_raised if self.funds_raised is not None else self.notional

        else:
            print("Invalid contract type, please check the contract type.")
            return 0.0

    def get_expected_income(self) -> float:
        """
        预期年化创收（万元）

        【计算逻辑】创收 = 名义本金 × 预期年化收益率
        这是最简化的估算，实际创收还取决于期限、费率结构等
        """
        return self.notional * self.expected_yield

    def is_swap_margin_100_and_stock_as_underlying(self) -> bool:
        """
        判断收益互换保证金比例是否为100%且标的资产为境内个股

        【监管背景】根据规定，100%保证金的个股收益互换在风险计提上有特殊处理
        【Python语法】abs(x - y) < 0.001 是浮点数比较的惯用写法，
                       避免浮点精度问题（不用 == 直接比较）
        """
        if self.contract_type != "equity_swap":
            return False
        if "stock" not in self.underlying_type:  # 标的必须是个股
            return False
        if self.margin_rate is not None:
            return abs(self.margin_rate - 100.0) < 0.001  # 保证金比例≈100%
        if self.margin_amount is not None:
            ratio = self.margin_amount / self.notional     # 折算成比例
            return abs(ratio - 1.0) < 0.001
        # 兜底：检查默认值是否100%（实际默认10%，所以通常返回False）
        return abs(DEFAULT_CONFIG["client"]["swap_margin_rate"] - 100.0) < 0.001

    def get_otc_delta_amount(self) -> float:
        """
        获取场外合约Delta敞口金额（万元）

        【业务含义】Delta = 标的资产价格变动1元时，合约价值变动多少
           - Delta金额 = Delta系数 × 名义本金，反映权益方向性风险敞口
           - 券商视角：做多标的 = 正Delta，做空标的 = 负Delta

        【Python语法】is_long = 1 if ... else -1 是简洁的方向符号赋值
        """
        # 方向归一化：期权用 buy/short，互换/凭证用 long/short
        is_long = 1 if self.direction in ("long", "buy") else -1

        # --- 期权Delta ---
        if "option" in self.contract_type:
            is_call = 1 if self.option_type == "call_option" else -1  # 看涨=+1, 看跌=-1
            if self.option_delta is not None:
                return self.option_delta * self.notional * is_call * is_long
            # 默认使用平值期权Delta=0.5，乘以 call/put 和 long/short 方向
            return DEFAULT_CONFIG["client"]["atm_option_delta"] * self.notional * is_call * is_long

        # --- 互换Delta ---
        elif "swap" in self.contract_type:
            if self.equity_swap_delta is not None:
                return self.equity_swap_delta * self.notional * is_long
            return DEFAULT_CONFIG["client"]["equity_swap_delta"] * self.notional * is_long

        # --- 收益凭证Delta（默认0，固收产品无权益敞口）---
        elif "income_certificate" in self.contract_type:
            if self.income_certificate_delta is not None:
                return self.income_certificate_delta * self.notional * is_long
            return DEFAULT_CONFIG["client"]["income_certificate_delta"] * self.notional * is_long

        return 0.0
