"""All MetaTrader 5 I/O: connection, market data, orders, positions.

Keeping every MT5 call behind this class means the rest of the bot (strategy,
risk, backtester) has zero hard dependency on MetaTrader5 and stays unit-test /
backtest friendly. ``import MetaTrader5`` is therefore done lazily inside the
methods that need it, so the package imports fine on machines without it.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from .risk_manager import SymbolSpec
from .strategy import Signal

log = logging.getLogger(__name__)

# String -> MT5 timeframe constant. Resolved lazily so we don't import MT5 at
# module load time.
_TIMEFRAME_NAMES = {
    "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1",
}


class MT5Connection:
    def __init__(self, login: int, password: str, server: str, path: Optional[str] = None):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self._mt5 = None  # set on connect()
        self._trade_mode = None  # account trade mode, captured on connect()

    # -- lifecycle -----------------------------------------------------------
    def connect(self) -> bool:
        import MetaTrader5 as mt5  # lazy import

        self._mt5 = mt5
        kwargs = {"login": self.login, "password": self.password, "server": self.server}
        if self.path:
            kwargs["path"] = self.path
        if not mt5.initialize(**kwargs):
            log.error("MT5 initialize() failed: %s", mt5.last_error())
            return False
        info = mt5.account_info()
        if info is None:
            log.error("MT5 connected but account_info() is None: %s", mt5.last_error())
            return False
        self._trade_mode = info.trade_mode
        log.info("Connected to MT5 account %s on %s (%s, balance=%.2f %s)",
                 info.login, info.server, self.account_mode_name(),
                 info.balance, info.currency)
        return True

    def account_mode_name(self) -> str:
        """Human-readable account type: DEMO / CONTEST / REAL / UNKNOWN."""
        mt5 = self.mt5
        return {
            mt5.ACCOUNT_TRADE_MODE_DEMO: "DEMO",
            mt5.ACCOUNT_TRADE_MODE_CONTEST: "CONTEST",
            mt5.ACCOUNT_TRADE_MODE_REAL: "REAL",
        }.get(self._trade_mode, "UNKNOWN")

    def is_real_account(self) -> bool:
        """True only when MT5 reports a live (real-money) account."""
        return self._trade_mode == self.mt5.ACCOUNT_TRADE_MODE_REAL

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    @property
    def mt5(self):
        if self._mt5 is None:
            raise RuntimeError("MT5 not connected — call connect() first.")
        return self._mt5

    # -- account / symbols ---------------------------------------------------
    def timeframe(self, name: str):
        key = name.replace("TIMEFRAME_", "").upper()
        if key not in _TIMEFRAME_NAMES:
            raise ValueError(f"Unknown timeframe '{name}'")
        return getattr(self.mt5, f"TIMEFRAME_{key}")

    def balance(self) -> float:
        return float(self.mt5.account_info().balance)

    def symbol_spec(self, symbol: str) -> Optional[SymbolSpec]:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            log.error("symbol_info(%s) returned None", symbol)
            return None
        if not info.visible:
            self.mt5.symbol_select(symbol, True)
            info = self.mt5.symbol_info(symbol)
        return SymbolSpec.from_mt5(info)

    # -- market data ---------------------------------------------------------
    def get_candles(self, symbol: str, timeframe: str, bars: int,
                    drop_forming: bool = True) -> Optional[pd.DataFrame]:
        """Return OHLC candles. The last bar from MT5 is the still-forming one;
        we drop it by default so the strategy only ever sees CLOSED candles."""
        tf = self.timeframe(timeframe)
        # Fetch one extra so we still have ``bars`` closed candles after dropping.
        rates = self.mt5.copy_rates_from_pos(symbol, tf, 0, bars + 1)
        if rates is None or len(rates) == 0:
            log.error("No rates for %s: %s", symbol, self.mt5.last_error())
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        if drop_forming and len(df) > 1:
            df = df.iloc[:-1]
        return df.reset_index(drop=True)

    # -- positions / orders --------------------------------------------------
    def open_positions(self, symbol: str, magic: int) -> int:
        positions = self.mt5.positions_get(symbol=symbol)
        if positions is None:
            return 0
        return sum(1 for p in positions if p.magic == magic)

    # Bitmask values for symbol_info.filling_mode (not exposed as module
    # constants by the MetaTrader5 package): FOK=1, IOC=2.
    _FILL_FOK = 1
    _FILL_IOC = 2

    def filling_mode(self, symbol: str) -> int:
        """Return an ORDER_FILLING_* the symbol actually supports.

        Brokers differ: many symbols accept only FOK and reject IOC (retcode
        10030 "Unsupported filling mode"). We inspect ``symbol_info.filling_mode``
        and prefer FOK, then IOC, falling back to RETURN.
        """
        mt5 = self.mt5
        info = mt5.symbol_info(symbol)
        allowed = getattr(info, "filling_mode", 0) if info else 0
        if allowed & self._FILL_FOK:
            return mt5.ORDER_FILLING_FOK
        if allowed & self._FILL_IOC:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def open_trade(self, symbol: str, signal: Signal, lot: float, magic: int,
                   deviation: int = 20, comment: str = "ForexBot"):
        """Send a market order with attached SL/TP. Returns the MT5 result."""
        mt5 = self.mt5
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            log.error("No tick for %s", symbol)
            return None

        if signal.action == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": order_type,
            "price": price,
            "sl": float(signal.sl),
            "tp": float(signal.tp),
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self.filling_mode(symbol),
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error("order_send failed for %s: %s", symbol,
                      getattr(result, "retcode", "no result"))
        else:
            log.info("Opened %s %s %.2f lots @ %.5f (sl=%.5f tp=%.5f)",
                     signal.action, symbol, lot, price, signal.sl, signal.tp)
        return result
