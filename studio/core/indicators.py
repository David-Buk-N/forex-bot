"""Technical indicators implemented in pure pandas.

Why pure pandas instead of ``ta`` / ``pandas_ta``?
  * Zero extra dependencies (only pandas is required), so the strategy and
    backtester run anywhere.
  * ``pandas_ta`` is currently broken on Python 3.13 (it imports the removed
    ``numpy.NaN``), which is exactly the interpreter this project runs on.

All functions are *causal*: the value at bar ``i`` only uses bars ``<= i``.
That property is what makes the backtester free of look-ahead bias.
"""

from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    """Exponential moving average (Wilder-style smoothing factor 2/(n+1))."""
    return series.ewm(span=length, adjust=False).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing is an EMA with alpha = 1/length.
    avg_gain = gain.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()

    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss == 0 the RSI is 100 by definition.
    out = out.where(avg_loss != 0, 100.0)
    return out


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Average True Range (Wilder's smoothing) in price units."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
