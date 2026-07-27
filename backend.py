# ============================================================
# backend.py - 后端核心逻辑
# ============================================================
#
# 【项目背景】
#   基于中国证监会《证券公司风险控制指标计算标准规定》，对股衍部（股票衍生品部）
#   的全部业务进行风险指标测算。核心目标是：在满足监管指标合规的前提下，找到
#   业务规模、资金使用、创收之间的较优平衡点。
#
# 【监管框架涉及的三大核心指标】
#   1. 风险覆盖率（净资本 / 各项风险资本准备之和） ≥ 100%（预警120%）
#   2. 流动性覆盖率 LCR（优质流动性资产 / 未来30日现金净流出） ≥ 100%（预警120%）
#   3. 净稳定资金率 NSFR（可用稳定资金 ASF / 所需稳定资金 RSF） ≥ 100%（预警120%）
#
# 【代码架构：两大业务模块 + 一组计算引擎】
#   模块A - OtcContract（客户端）：场外衍生品合约，包括场外期权、收益互换、收益凭证
#   模块B - HedgeTrade（交易端）：用于对冲客户端风险的工具，包括ETF、股票、期货、期权等
#   计算引擎 - 一系列函数：输入 OtcContract + HedgeTrade → 输出各项风险指标变化
#
# 【Python 语法要点速览】
#   - import X as Y：导入库并起别名，如 numpy→np，方便后续简短调用
#   - from X import Y：从库中只导入特定功能，避免加载整个库
#   - typing 模块：提供类型注解工具（Dict/List/Optional等），仅用于代码提示，不影响运行
#   - dataclass：装饰器，自动为类生成 __init__/__repr__ 等方法，减少样板代码
#   - Optional[X]：表示该变量可以是 X 类型，也可以是 None（空值）
#   - -> 返回值类型注解：函数箭头后标注返回值类型，如 -> float 表示返回浮点数
# ============================================================

# ---------- 第三方库导入 ----------
import numpy as np          # 科学计算库，这里主要用于 np.nan（表示"非数字"）
import pandas as pd         # 数据分析库，这里用于价格序列的相关性计算（pd.Series）
import random               # 随机数库
from datetime import datetime, timedelta  # 日期时间处理
from typing import Dict, Any, Optional, List  # 类型注解工具
from dataclasses import dataclass, field       # 数据类装饰器，自动生成构造函数等
import math                 # 数学函数库

from iFinDPy import *       # 同花顺 iFinD 数据接口


# ===================== 默认参数配置 =====================
# 【Python语法】字典（dict）：用 {key: value} 存储键值对，通过 DEFAULT_CONFIG["client"]["swap_margin_rate"] 访问
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
        "otc_option_premium_rate": 0.03,    # 场外期权（背对背平盘）默认权利金比例 3%
        "atm_option_delta": 0.5,            # 场内外期权默认Delta值（平值期权≈0.5）
        "onsite_option_stress_loss": 0.0,   # 卖出压力测试最大损失（万元），默认0=未设置
    },

    # ---------- firm：公司当前基准数据（用于计算增量影响） ----------
    # 【设计思路】模型不计算绝对值，而是计算"增量"——即新业务对现有指标的影响
    #           先存储公司当前的各项基数，再叠加新业务变动，最后对比前后差异
    "firm": {
        "classification_factor": 1.0,           # 证监会对券商的分类评价系数（AAA=0.4, AA=0.6, A=0.8, B=0.9, C=1.0, D=2.0）
        "HQLA_base": 11_881_000_000,            # 当前优质流动性资产总额（元）—— LCR分子
        "LCR_COF_base": 7_977_000_000,          # 当前未来30日现金净流出（元）—— LCR分母
        "ASF_base": 30_532_000_000,             # 当前可用稳定资金总额（元）—— NSFR分子
        "RSF_base": 21_644_000_000,             # 当前所需稳定资金总额（元）—— NSFR分母
        "net_capital_base": 16_496_000_000,     # 当前净资本（元）—— 风险覆盖率分子
        "total_risk_reserve_base": 740_000_000, # 当前各项风险资本准备之和（元）—— 风险覆盖率分母
        "on_off_balance_total_asset_base": 300_000_000_000,  # 表内外资产总额（元）
    }
}  # 数据来自之前业务的excel表格


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
        """获取收益凭证票面利率（%）"""
        return self.income_certificate_rate

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
        is_long = 1 if self.direction == "long" else -1  # 多头=+1, 空头=-1

        # --- 期权Delta ---
        if "option" in self.contract_type:
            is_call = 1 if self.option_type == "call_option" else -1  # 看涨=+1, 看跌=-1
            if self.option_delta is not None:
                return self.option_delta * self.notional
            # 默认使用平值期权Delta=0.5，乘以 call/put 和 long/short 方向
            return DEFAULT_CONFIG["client"]["atm_option_delta"] * self.notional * is_call * is_long

        # --- 互换Delta ---
        elif "swap" in self.contract_type:
            if self.equity_swap_delta is not None:
                return self.equity_swap_delta * self.notional
            return DEFAULT_CONFIG["client"]["equity_swap_delta"] * self.notional * is_long

        # --- 收益凭证Delta（默认0，固收产品无权益敞口）---
        elif "income_certificate" in self.contract_type:
            if self.income_certificate_delta is not None:
                return self.income_certificate_delta * self.notional
            return DEFAULT_CONFIG["client"]["income_certificate_delta"] * self.notional * is_long

        return 0.0


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


# ===================== 核心计算函数 =====================
# 【整体数据流】
#   OtcContract + [HedgeTrade, ...]
#     → ifind_login() + get_underlying_price_series() + calculate_correlation_between_price_series()
#       + get_onsite_option_greeks() → is_effective_hedge()
#     → calc_market_risk_reserve() + calc_credit_risk_reserve() → calc_total_risk_reserve()
#     → calc_lcr_impact() + calc_nsfr_impact()
#     → analyze_contract() → 最终指标字典
# ============================================================

# =============== iFinD 数据接口函数 ===============

def ifind_login():
    """
    登录同花顺 iFinD 数据终端

    【用途】在使用 THS_HQ、THS_DS 等接口获取实时数据前，必须先调用此函数完成身份认证
    Returns:
        bool: 登录成功返回 True，失败返回 False
    """
    thsLogin = THS_iFinDLogin('glzq703','96998XuY')
    print(thsLogin)
    if thsLogin in {0, -201}:
        print('登录成功')
        return True
    else:
        print('登录失败')
        return False


def get_underlying_price_series(underlying_code: str,
                         price_type: str = "close",
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> Dict[str, List[float]]:
    """
    获取产品底层过去一年的价格数据（通过同花顺 iFinD API）

    Args:
        underlying_code: 同花顺代码，如 'AAPL.O', '000300.SH'
        start_date: 开始日期 'YYYY-MM-DD'，默认一年前
        end_date: 结束日期 'YYYY-MM-DD'，默认今天
        price_type: 价格类型，如 'close', 'open', 'high', 'low', 'pre_close'
    Returns:
        Dict[str, List[float]]: {"代码": [价格列表]}，若获取失败返回空列表
    """
    if not ifind_login():
        print("登录失败")
        return {underlying_code: []}
    # 获取当前日期与提前一年起始日期
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    try:
        # 调用 THS_HQ 获取行情数据
        result = THS_HQ(underlying_code, price_type, 'fill:omit', start_date, end_date)
        if result is None:
            print("THS_DS 返回 None")
            return {underlying_code: []}
        if hasattr(result, 'errorcode') and result.errorcode != 0:
            print(f"获取数据失败，错误码: {result.errorcode}, 错误信息: {result.errmsg}")
            return {underlying_code: []}
        data = pd.DataFrame(result.data)
        THS_iFinDLogout()
        if data.empty:
            print("获取数据为空")
            return {underlying_code: []}
        return {underlying_code: data[price_type].tolist()}

    except Exception as e:
        print(f"获取底层价格数据失败: {e}")
        return {underlying_code: []}


def calculate_correlation_between_price_series(otc_code: str, otc_prices: Dict[str, List[float]],
    hedge_code: str, hedge_prices: Dict[str, List[float]]) -> float:
    """
    计算两个标的价格序列的皮尔逊相关系数（Pearson correlation）

    【用途】当客户端标的与对冲工具标的代码不同时（如用中证500期货对冲沪深300期权），
           通过历史价格相关性判断是否可视为"同一标的"

    Args:
        otc_code: 场外合约代码
        otc_prices: 场外合约价格字典
        hedge_code: 对冲工具代码
        hedge_prices: 对冲工具价格字典
    Returns:
        float: 相关系数（-1到1），数据不足返回 np.nan
    """
    # 提取价格序列
    otc_series = pd.Series(otc_prices.get(otc_code, []))
    hedge_series = pd.Series(hedge_prices.get(hedge_code, []))
    if len(otc_series) < 2 or len(hedge_series) < 2:
        return np.nan  # 数据不足2个点，无法计算相关，返回 NaN（Not a Number）

    # 对齐长度：取两者较短的
    min_len = min(len(otc_series), len(hedge_series))
    otc_aligned = otc_series.iloc[:min_len]
    hedge_aligned = hedge_series.iloc[:min_len]
    corr = otc_aligned.corr(hedge_aligned)
    return corr if corr is not None else np.nan


def get_onsite_option_greeks(option_code: str, greek_letter: str = 'delta') -> Optional[float]:
    """
    获取场内期权希腊字母值（通过同花顺 iFinD API）

    Args:
        option_code: 期权代码
        greek_letter: 希腊字母，如 'delta', 'gamma', 'vega', 'theta', 'rho'
    Returns:
        float: 期权当日希腊字母值，若当天交易未结束，返回前一交易日值；获取失败返回 None
    """
    if not ifind_login():
        print("登录失败")
        return None
    # 5大常用希腊字母映射字典
    map_dict = {'delta': 'ths_delta_option','gamma': 'ths_gamma_option','vega': 'ths_vega_option','theta': 'ths_theta_option','rho': 'ths_rho_option'}
    greek_wanted = map_dict.get(greek_letter, None)
    # 当前日期和上一交易日的保守自然日（-14天）
    current_date = datetime.now().strftime('%Y-%m-%d')
    conservative_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    if greek_wanted is None:
        print(f"未找到{greek_letter}对应的greeks值")
        return None

    try:
        greeklist = THS_DS(option_code, greek_wanted,'100','Days:Tradedays,Fill:Blank', conservative_date, current_date)
        if greeklist is None:
            print("THS_DS 返回 None")
            return None
        if hasattr(greeklist, 'errorcode') and greeklist.errorcode != 0:
            print(f"获取数据失败，错误码: {greeklist.errorcode}, 错误信息: {greeklist.errmsg}")
            return None
        data = pd.DataFrame(greeklist.data)
        THS_iFinDLogout()
        if data.empty:
            print("获取数据为空")
            return None
        greek_value_list = data[greek_wanted].tolist()
        if np.isnan(greek_value_list[-1]):
            greek_value = greek_value_list[-2]
        else:
            greek_value = greek_value_list[-1]
        return greek_value

    except Exception as e:
        print(f"获取期权greeks值失败: {e}")
        return None


# =============== 对冲有效性判断 ===============

def is_effective_hedge(otc: OtcContract, hedge_list: List[HedgeTrade], price_type: str = "close") -> List[bool, Optional[str]]:
    """
    判断场外合约与对冲工具组合是否构成"有效对冲"

    【监管背景】根据《证券公司风险控制指标计算标准规定》，有效对冲的头寸
               在计算市场风险资本准备时可以享受95%的减免（只计提5%）

    Args:
        otc: 场外合约对象
        hedge_list: 对冲工具列表
        price_type: 标的价格类型，如 'close', 'open', 'high', 'low', 'pre_close'
    Returns:
        [bool, str]: [是否构成有效对冲, 失败原因（成功时为None）]

    【两个条件必须同时满足】
      条件1：标的相同 OR 价格相关性 ≥ 95%
      条件2：多头Delta的绝对值与空头Delta的绝对值比例在 80%-125% 之间
            （即对冲覆盖率在80%以上，且不超过125%，避免过度对冲）
    """
    # ========== 条件1.1：判断标的物是否相同 ==========
    otc_underlying_code = otc.get_otc_underlying_code()
    if otc_underlying_code is None:
        return [False, "未填写场外合约标的代码，默认不满足有效对冲条件"]
    hedge_tool_underlying_codes = [h.get_tool_underlying_code() for h in hedge_list if h.get_tool_underlying_code() is not None]
    if not hedge_tool_underlying_codes:
        return [False, "未填写对冲工具标的代码，默认不满足有效对冲条件"]

    # 子条件1.1：任一工具的标的代码与场外合约相同即为"同一标的"
    underlying_is_same = any(otc_underlying_code == h_code for h_code in hedge_tool_underlying_codes)

    # ========== 条件1.2：判断标的物过去一年价格相关性 ≥ 95% ==========
    correlation_met = True
    if not underlying_is_same:
        otc_price_data = get_underlying_price_series(otc_underlying_code, price_type) # 产品底层过去一年价格
        if not otc_price_data.get(otc_underlying_code, []):
            return [False, f"获取{otc.get_otc_contract_type()}产品标的：{otc.get_otc_underlying_code()}价格数据失败"]
        for hedge_tool_underlying_code in hedge_tool_underlying_codes:
            hedge_price_data = get_underlying_price_series(hedge_tool_underlying_code, price_type) # 获取对冲工具底层过去一年的价格
            if not hedge_price_data.get(hedge_tool_underlying_code, []):
                return [False, f"获取对冲工具标的: {hedge_tool_underlying_code}价格数据失败"]
            # 计算相关系数
            corr = calculate_correlation_between_price_series(otc_underlying_code, otc_price_data, hedge_tool_underlying_code, hedge_price_data)
            if np.isnan(corr) or corr < 0.95:  # 阈值：95%相关性
                correlation_met = False
                break
        condition1 = underlying_is_same or correlation_met
        if not condition1:
            return [False, "标的代码不匹配或标的物过去一年价格相关性未达到95%"]

    # ========== 条件2：计算Delta值比例 ==========
    # 将场外合约与所有对冲工具的(direction, delta_amount)汇总到同一列表
    all_positions = []
    otc_delta_amount = otc.get_otc_delta_amount()
    otc_direction = otc.get_otc_contract_direction()
    if otc_delta_amount is not None:
        all_positions.append((otc_direction, otc_delta_amount))
    else:
        return [False, "未填写场外合约Delta金额，默认不满足有效对冲条件"]
    for hedge in hedge_list:
        hedge_direction = hedge.get_tool_direction()
        # 场内期权优先从 iFinD API 获取实时 Delta
        if hedge.get_tool_type() == "onsite_option":
            hedge_delta = get_onsite_option_greeks(hedge.get_tool_code(), "delta")
        else:
            hedge_delta = hedge.get_hedge_delta_amount()
        if hedge_delta is not None:
            all_positions.append((hedge_direction, hedge_delta))
        else:
            return [False, "未填写对冲工具Delta金额，或未成功获取相应期权delta值，请检查，否则默认不满足有效对冲条件"]
    if not all_positions:
        return [False, "未找到有效的Delta头寸数据"]

    # 分别统计多头和空头的Delta绝对值总和
    long_delta = sum(abs(delta) for dir_, delta in all_positions if dir_ == "long")
    short_delta = sum(abs(delta) for dir_, delta in all_positions if dir_ == "short")
    if long_delta == 0 or short_delta == 0:
        return [False, "多头Delta绝对值或空头Delta绝对值为0，默认不满足有效对冲条件"]
    ratio = min(long_delta, short_delta) / max(long_delta, short_delta)  # 始终 ≤ 1
    if ratio < 0.80:  # 对冲覆盖不足80%
        return [False, "多头Delta绝对值与空头Delta绝对值比例不在80%-125%之间"]

    return [True, None]


# =============== 风险资本准备计算 ===============

def calc_market_risk_reserve(otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool) -> float:
    """
    计算市场风险资本准备（万元）

    【监管背景】这是风险覆盖率指标的分母组成部分。
               根据《证券公司风险控制指标计算标准规定》，不同资产类别有不同计提比例。

    【注意】当前函数有多处使用了不存在的key（如 RATES["buy_option"]、RATES["futures_swap"]），
           在实际运行时会抛出 KeyError。这是未完成代码的标志。
           原意应该是用 RATES 中定义的具体类型key。
    """
    # 各类资产的市场风险计提比例（根据证监会规定）
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

    reserve = 0.0

    # --- 场外合约风险敞口 ---
    # ⚠️ 注意：此处的 contract_type 判断用了 "option"/"swap"/"income_note"，
    #    但 OtcContract 中实际用的是 "call_option"/"put_option"/"equity_swap"/"income_certificate"
    #    这些判断可能无法正确匹配。使用前需确认字符串一致性。
    if otc.contract_type == "option":
        if otc.direction == "buy":
            premium = otc.notional * (otc.premium_rate or DEFAULT_CONFIG["client"]["option_premium_rate"]) / 100
            reserve += premium * RATES["buy_option"]  # ⚠️ BUG: "buy_option" 不在 RATES 中
        else:  # 卖出期权
            if otc.stress_loss is not None:
                # 卖出场外期权：虚拟本金 = max(压力损失×5, 名义本金×0.5%)
                virtual = max(otc.stress_loss * 5, otc.notional * 0.005)
                reserve += virtual * RATES["futures_swap"]  # ⚠️ BUG: "futures_swap" 不在 RATES 中
            elif otc.delta_amount is not None:
                # 卖出场内期权：Delta金额 × 15% × 风险系数
                # ⚠️ BUG: otc 没有 delta_amount 属性，应该是 otc.get_otc_delta_amount()
                reserve += otc.delta_amount * 0.15 * RATES["futures_swap"]
            else:
                # 默认按名义本金估算
                reserve += otc.notional * 0.30 * RATES["futures_swap"]

    elif otc.contract_type == "swap":
        exposure = otc.notional * 0.10  # 互换风险敞口 = 名义本金 × 10%
        reserve += exposure * RATES["futures_swap"]  # ⚠️ BUG: key不存在
        if otc.margin_rate is not None and otc.margin_rate < 100:
            reserve *= 2  # 非全额保证金互换，风险准备翻倍（监管要求）

    elif otc.contract_type == "income_note":
        if otc.expected_yield > 0.05:
            # 收益凭证预期收益率 > 5% 才有市场风险
            reserve += otc.notional * 0.05 * RATES["futures_swap"]  # ⚠️ BUG: key不存在

    # 有效对冲减免：对冲有效 → 风险准备打5%折扣（减免95%）
    if is_hedge_effective and hedge_list:
        reserve *= 0.05

    return reserve


def calc_credit_risk_reserve(otc: OtcContract) -> float:
    """
    计算信用风险资本准备（万元）

    【监管背景】对于非全额保证金的收益互换，客户可能违约不补保证金，
               因此需要计提信用风险资本准备。

    当前仅对标的为"general_stock"的非全额保证金互换计提5%
    """
    if otc.contract_type == "swap" and otc.margin_rate is not None and otc.margin_rate < 100:
        if otc.underlying_type == "general_stock":
            return otc.notional * 0.05
    return 0.0


def calc_total_risk_reserve(otc: OtcContract, hedge_list: List[HedgeTrade], is_hedge_effective: bool) -> float:
    """
    计算各项风险资本准备合计（万元）

    【组成】市场风险 + 信用风险 + 操作风险（待实现）+ 特定风险（待实现）
    【分类评价系数】证监会根据券商评级调整最终风险准备，评级越高系数越低
      AAA=0.4, AA=0.6, A=0.8, BBB=0.9, BB=1.0, B=1.0, C=1.0, D=2.0
    """
    total = (
        calc_market_risk_reserve(otc, hedge_list, is_hedge_effective)
        + calc_credit_risk_reserve(otc)
        # + calc_operational_risk_reserve()  # 操作风险资本准备（未实现）
        # + calc_specific_risk_reserve()     # 特定风险资本准备（未实现）
    )
    total *= DEFAULT_CONFIG["firm"]["classification_factor"]  # 乘以证监会分类评价系数
    return total


# =============== LCR / NSFR 影响计算 ===============

def calc_lcr_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    计算对 LCR（流动性覆盖率）的影响

    【LCR = HQLA / 未来30日现金净流出 ≥ 100%】
      HQLA = High Quality Liquid Assets（优质流动性资产）
      COF  = Cash Outflow（现金净流出）

    【本函数的简化处理】
      1. 场外合约现金流入直接增加HQLA
      2. 对冲端现金流出直接减少HQLA
      3. 仅30日内到期的合约才计入COF（压力情景下的现金流出）
      4. 未完整处理CIF(Cash Inflow)抵扣（因监管对CIF抵扣有上限限制）
    """
    hqla_change = 0.0  # HQLA变动量
    cof_change = 0.0   # 未来30日现金净流出变动量

    # 场外合约现金变动 → HQLA
    otc_cash = otc.get_otc_cash_inflow()
    hqla_change += otc_cash

    # 对冲端现金变动 → HQLA（注意负号：流出减少HQLA，流入增加HQLA）
    for hedge in hedge_list:
        trade_cash = hedge.get_trade_cash_outflow()
        hqla_change -= trade_cash  # 对冲端流出=券商花钱=HQLA减少

    # 30日内到期现金流 → 计入COF
    if otc.term_days <= 30:
        if otc.contract_type == "income_note":
            # 收益凭证30日内到期：需偿还募集资金
            cof_change += otc.funds_raised or otc.notional  # X or Y：取第一个非None/非零值
        elif otc.contract_type == "swap":
            # 互换30日内到期：需返还客户保证金
            cof_change += otc.notional * (otc.margin_rate or 10) / 100

    return {
        "hqla_change": hqla_change,
        "net_cof_change": cof_change,  # 简化，未处理CIF抵扣
    }


def calc_nsfr_impact(otc: OtcContract, hedge_list: List[HedgeTrade]) -> Dict[str, float]:
    """
    计算对 NSFR（净稳定资金率）的影响

    【NSFR = 可用稳定资金(ASF) / 所需稳定资金(RSF) ≥ 100%】
      ASF = Available Stable Funding（负债端，期限越长越稳定）
      RSF = Required Stable Funding（资产端，流动性越差需要越多稳定资金）

    【监管规则要点】
      - 期限≥1年的负债可按较高比例计入ASF
      - 各类资产按流动性不同有不同RSF系数（如股票50%，私募20%）
    """
    asf_change = 0.0
    rsf_change = 0.0

    # --- 可用稳定资金（ASF）变动 ---
    # 收益凭证：期限>=1年 → 100%计入ASF（属于稳定的长期负债）
    if otc.contract_type == "income_note" and otc.term_days >= 365:
        asf_change += otc.funds_raised or otc.notional

    # 互换保证金：期限>=1年 → 按50%计入ASF
    if otc.contract_type == "swap" and otc.term_days >= 365:
        asf_change += otc.notional * (otc.margin_rate or 10) / 100 * 0.5

    # --- 所需稳定资金（RSF）变动 ---
    if otc.contract_type == "option":
        if otc.direction == "buy":
            # 买入期权：权利金部分需要稳定资金
            premium = otc.notional * (otc.premium_rate or 5) / 100
            rsf_change += premium
        else:
            # 卖出期权：名义本金的30%需要稳定资金
            rsf_change += otc.notional * 0.30

    elif otc.contract_type == "swap":
        # 互换：名义本金的1%
        rsf_change += otc.notional * 0.01

    # 对冲端 RSF 计提
    for hedge in hedge_list:
        if hedge.tool_type == "etf" or hedge.tool_type == "stock_basket":
            rsf_change += hedge.notional * 0.50  # ETF/股票：50%
        elif hedge.tool_type == "private_fund":
            rsf_change += (hedge.subscription_amount or 0) * 0.20  # 私募基金：20%
        elif hedge.tool_type == "otc_hedge":
            rsf_change += hedge.notional * 0.01  # 场外背对背：1%

    return {"asf_change": asf_change, "rsf_change": rsf_change}


# =============== 主分析函数 ===============

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


# ================================================================
# 以下为测试代码（原型验证用，不是正式功能的一部分）
# 【用途】测试 is_effective_hedge 和 get_underlying_price_series 函数
# 【场景】券商卖出一笔中证1000看跌期权（名义本金10亿），做多5000万场内期权对冲
# 【预期】由于标的代码相同（000852），应返回 True
# ================================================================
if __name__ == "__main__":
    otc = OtcContract(
        contract_type="put_option",
        direction="short",
        notional=100000,
        underlying_type="Index",
        underlying_name="中证1000",
        underlying_code="000852"
    )
    hedge_list = [
        HedgeTrade(
            tool_type="onsite_option",
            direction="long",
            notional=50000,
            underlying_type="Index",
            underlying_name="中证1000",
            underlying_code="000852",
            option_delta=0.95
        )
    ]
    is_effective = is_effective_hedge(otc, hedge_list)
    print(is_effective)

    d = get_underlying_price_series('000852.SH', 'close')
    print(d)
