# ============================================================
# backend/__init__.py - 包统一导出，对外接口保持不变
# ============================================================
# 通过别名机制，将 OtcContract 导出为 ClientContract，
# 保持 app.py 中 `from backend import ClientContract` 无需改动。

from .config import DEFAULT_CONFIG, IFIND_DEFAULT_LOGIN
from .models.client_contract import OtcContract as ClientContract
from .models.hedge_trade import HedgeTrade
from .analyzer import analyze_contract

__all__ = [
    "ClientContract",
    "HedgeTrade",
    "analyze_contract",
    "DEFAULT_CONFIG",
    "IFIND_DEFAULT_LOGIN",
]
