"""Signal logic.

The original strategy was a bare EMA(9/21) crossover, which whipsaws badly in
ranging markets. This version stacks three independent confirmations so a trade
is only taken when trend, momentum and a fresh trigger all agree:

  1. Trend filter   - price must be on the correct side of a long EMA
                      (EMA200 by default). Don't fight the dominant trend.
  2. Trigger        - a fresh EMA fast/slow cross on the *just-closed* candle.
  3. Momentum       - RSI must confirm direction (and not be at an exhausted
                      extreme, which is where reversals punish breakouts).

Stops and targets are volatility-based (ATR), so they adapt to each pair and
market condition instead of a fixed pip count. Every decision is made on a
*closed* candle to avoid repainting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import indicators


@dataclass(frozen=True)
class Signal:
    action: str        # "BUY" or "SELL"
    price: float       # close of the signal (closed) candle
    sl: float          # stop-loss price
    tp: float          # take-profit price
    atr: float         # ATR at signal time (price units)
    reason: str        # human-readable explanation

    @property
    def sl_distance(self) -> float:
        return abs(self.price - self.sl)


# Sensible defaults; every value is overridable from config.yaml -> strategy:
DEFAULTS = {
    "ema_fast": 9,
    "ema_slow": 21,
    "ema_trend": 200,
    "rsi_period": 14,
    "rsi_buy": 50.0,        # momentum must be bullish for a long
    "rsi_sell": 50.0,       # momentum must be bearish for a short
    "rsi_overbought": 75.0,  # don't buy into exhaustion
    "rsi_oversold": 25.0,    # don't sell into exhaustion
    "atr_period": 14,
    "atr_sl_mult": 1.5,      # stop = entry -/+ 1.5 * ATR
    "risk_reward": 2.0,      # target = 2x the stop distance
}


class Strategy:
    def __init__(self, params: Optional[dict] = None):
        self.p = {**DEFAULTS, **(params or {})}

    # -- data prep -----------------------------------------------------------
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach indicator columns. Vectorised, so it's cheap to call once."""
        df = df.copy()
        df["ema_fast"] = indicators.ema(df["close"], self.p["ema_fast"])
        df["ema_slow"] = indicators.ema(df["close"], self.p["ema_slow"])
        df["ema_trend"] = indicators.ema(df["close"], self.p["ema_trend"])
        df["rsi"] = indicators.rsi(df["close"], self.p["rsi_period"])
        df["atr"] = indicators.atr(
            df["high"], df["low"], df["close"], self.p["atr_period"]
        )
        return df

    # -- minimum bars needed before any signal is valid ----------------------
    @property
    def warmup(self) -> int:
        return max(
            self.p["ema_trend"],
            self.p["ema_slow"],
            self.p["rsi_period"],
            self.p["atr_period"],
        ) + 2

    # -- core decision at a single (closed) bar ------------------------------
    def signal_at(self, df: pd.DataFrame, i: int) -> Optional[Signal]:
        """Evaluate bar ``i`` (which must be a CLOSED candle).

        Requires ``df`` to already contain indicator columns (see ``prepare``).
        Returns a ``Signal`` or ``None``.
        """
        if i < self.warmup or i < 1:
            return None

        cur = df.iloc[i]
        prev = df.iloc[i - 1]

        # Bail out if any indicator is still warming up (NaN).
        needed = ("ema_fast", "ema_slow", "ema_trend", "rsi", "atr")
        if cur[list(needed)].isna().any() or prev[["ema_fast", "ema_slow"]].isna().any():
            return None

        atr_val = float(cur["atr"])
        if atr_val <= 0:
            return None

        price = float(cur["close"])
        cross_up = prev["ema_fast"] <= prev["ema_slow"] and cur["ema_fast"] > cur["ema_slow"]
        cross_dn = prev["ema_fast"] >= prev["ema_slow"] and cur["ema_fast"] < cur["ema_slow"]

        sl_dist = atr_val * self.p["atr_sl_mult"]
        rr = self.p["risk_reward"]

        # ---- LONG ----------------------------------------------------------
        if cross_up:
            uptrend = price > cur["ema_trend"]
            momentum_ok = self.p["rsi_buy"] < cur["rsi"] < self.p["rsi_overbought"]
            if uptrend and momentum_ok:
                return Signal(
                    action="BUY",
                    price=price,
                    sl=price - sl_dist,
                    tp=price + sl_dist * rr,
                    atr=atr_val,
                    reason=(
                        f"EMA{self.p['ema_fast']}>{self.p['ema_slow']} cross up, "
                        f"price>EMA{self.p['ema_trend']}, RSI={cur['rsi']:.1f}"
                    ),
                )

        # ---- SHORT ---------------------------------------------------------
        if cross_dn:
            downtrend = price < cur["ema_trend"]
            momentum_ok = self.p["rsi_oversold"] < cur["rsi"] < self.p["rsi_sell"]
            if downtrend and momentum_ok:
                return Signal(
                    action="SELL",
                    price=price,
                    sl=price + sl_dist,
                    tp=price - sl_dist * rr,
                    atr=atr_val,
                    reason=(
                        f"EMA{self.p['ema_fast']}<{self.p['ema_slow']} cross down, "
                        f"price<EMA{self.p['ema_trend']}, RSI={cur['rsi']:.1f}"
                    ),
                )

        return None

    # -- convenience for the live loop: decide on the last closed bar --------
    def check_signals(self, df: pd.DataFrame) -> Optional[Signal]:
        """Prepare indicators and evaluate the most recent (closed) candle.

        ``df`` should contain only CLOSED candles (the live loop drops the
        forming bar before calling this).
        """
        if len(df) < self.warmup:
            return None
        prepared = self.prepare(df)
        return self.signal_at(prepared, len(prepared) - 1)
