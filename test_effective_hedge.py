from backend.calculators.hedge_validator import is_effective_hedge
from backend.models.client_contract import OtcContract
from backend.models.hedge_trade import HedgeTrade

# ===== 测试代码 =====
otc = OtcContract(
    contract_type="option",
    direction="short",
    notional=1000000,
    underlying_type="fund",
    underlying_code="159716.SZ",
    underlying_market="CN",
    option_type="call",
    premium_rate=0.05,
    option_delta = -0.5
)

hedge_list = [HedgeTrade(
    tool_type="onsite_option",
    direction="long",
    notional=1000000,
    tool_code="90007054.SZ",
    underlying_type="fund",
    underlying_code="159706.SZ",
    underlying_market="CN",
    option_type="call",
)]

result = is_effective_hedge(otc, hedge_list)
print(result)  # 输出结果
