"""Get historical candles to a CSV the backtester can read.

Two modes:

  Export from MT5 (needs the terminal installed + logged in):
      python tools/export_data.py export EURUSD M15 5000 --out data/EURUSD_M15.csv

  Generate synthetic data (works anywhere, no MT5 needed) so you can try the
  backtester immediately:
      python tools/export_data.py sample --out data/sample_EURUSD.csv --bars 6000
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd


def export_from_mt5(symbol: str, timeframe: str, bars: int, out: str) -> None:
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    tf = getattr(mt5, f"TIMEFRAME_{timeframe.replace('TIMEFRAME_', '').upper()}")
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
    mt5.shutdown()
    if rates is None or len(rates) == 0:
        raise SystemExit("No data returned from MT5.")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    _write(df[["time", "open", "high", "low", "close"]], out)


def make_sample(bars: int = 6000, start_price: float = 1.10, seed: int = 7) -> pd.DataFrame:
    """Synthetic OHLC with regime-switching drift so there are real trends to
    catch as well as choppy stretches to be filtered out."""
    rng = np.random.default_rng(seed)
    vol = 0.0006  # per-bar volatility, ~M15 EURUSD-ish

    # Regime-switching drift: alternating trend/range blocks.
    drift = np.zeros(bars)
    i = 0
    while i < bars:
        block = rng.integers(80, 300)
        regime = rng.choice([-1, 0, 1], p=[0.35, 0.30, 0.35])
        drift[i:i + block] = regime * vol * 0.18
        i += block

    rets = drift + rng.normal(0, vol, bars)
    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.empty(bars)
    open_[0] = start_price
    open_[1:] = close[:-1]

    # Build a plausible high/low envelope around each bar.
    wick = np.abs(rng.normal(0, vol, bars)) + vol * 0.5
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick

    times = pd.date_range("2023-01-01", periods=bars, freq="15min")
    return pd.DataFrame({
        "time": times,
        "open": np.round(open_, 5),
        "high": np.round(high, 5),
        "low": np.round(low, 5),
        "close": np.round(close, 5),
    })


def _write(df: pd.DataFrame, out: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} candles -> {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="Export real candles from MT5")
    e.add_argument("symbol")
    e.add_argument("timeframe")
    e.add_argument("bars", type=int)
    e.add_argument("--out", default="data/export.csv")

    s = sub.add_parser("sample", help="Generate synthetic candles")
    s.add_argument("--out", default="data/sample_EURUSD.csv")
    s.add_argument("--bars", type=int, default=6000)
    s.add_argument("--seed", type=int, default=7)

    args = ap.parse_args(argv)
    if args.cmd == "export":
        export_from_mt5(args.symbol, args.timeframe, args.bars, args.out)
    else:
        _write(make_sample(bars=args.bars, seed=args.seed), args.out)


if __name__ == "__main__":
    main()
