"""Event-driven backtester.

The original ``backtester.py`` had an empty loop and printed "Backtest
Complete" — it measured nothing. You cannot make a strategy "more accurate"
without a way to score it, so this is the centrepiece.

How it works (and why it's honest):
  * Indicators are computed once on the whole series. They're causal, so using
    them bar-by-bar introduces no look-ahead.
  * A signal detected on the close of bar ``i`` is entered at the OPEN of bar
    ``i+1`` — you can never act on information you didn't have yet.
  * Stops/targets are checked intrabar against each bar's high/low. If a bar
    could have hit both, we assume the STOP filled first (worst case).
  * Risk is modelled in R-multiples: every trade risks ``risk_percent`` of the
    current equity. This makes results instrument-agnostic and directly
    comparable across pairs.

Run it:
    python -m backtesting.backtester ../data/sample_EURUSD.csv
    python backtesting/backtester.py data/sample_EURUSD.csv --risk 1 --rr 2
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

# Allow running both as a module and as a bare script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.strategy import Strategy, Signal  # noqa: E402


@dataclass
class Trade:
    direction: str
    entry_time: pd.Timestamp
    entry: float
    sl: float
    tp: float
    exit_time: Optional[pd.Timestamp] = None
    exit: Optional[float] = None
    reason: str = ""          # "tp" | "sl" | "eod"
    r_multiple: float = 0.0   # profit/loss in units of initial risk
    pnl: float = 0.0          # money, given the risk model


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    start_equity: float = 10_000.0

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else self.start_equity

    def summary(self) -> dict:
        n = len(self.trades)
        if n == 0:
            return {"trades": 0}
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = -sum(t.pnl for t in losses)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        peak = self.start_equity
        max_dd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            max_dd = max(max_dd, (peak - eq) / peak)

        return {
            "trades": n,
            "win_rate": len(wins) / n,
            "wins": len(wins),
            "losses": len(losses),
            "profit_factor": profit_factor,
            "expectancy_r": sum(t.r_multiple for t in self.trades) / n,
            "avg_win_r": (sum(t.r_multiple for t in wins) / len(wins)) if wins else 0.0,
            "avg_loss_r": (sum(t.r_multiple for t in losses) / len(losses)) if losses else 0.0,
            "total_return_pct": (self.final_equity / self.start_equity - 1) * 100,
            "max_drawdown_pct": max_dd * 100,
            "final_equity": self.final_equity,
        }

    def report(self) -> str:
        s = self.summary()
        if s.get("trades", 0) == 0:
            return "No trades were taken. (Try a longer dataset or looser filters.)"
        pf = s["profit_factor"]
        pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
        return (
            "------------- Backtest Report -------------\n"
            f"Trades            : {s['trades']}  ({s['wins']}W / {s['losses']}L)\n"
            f"Win rate          : {s['win_rate']*100:.1f}%\n"
            f"Profit factor     : {pf_str}\n"
            f"Expectancy        : {s['expectancy_r']:+.3f} R per trade\n"
            f"Avg win / loss    : {s['avg_win_r']:+.2f} R / {s['avg_loss_r']:+.2f} R\n"
            f"Total return      : {s['total_return_pct']:+.2f}%\n"
            f"Max drawdown      : {s['max_drawdown_pct']:.2f}%\n"
            f"Start -> End equity: {self.start_equity:,.2f} -> {s['final_equity']:,.2f}\n"
            "-------------------------------------------"
        )


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Map common column spellings to open/high/low/close[/time]."""
    cols = {c.lower(): c for c in df.columns}
    rename = {}
    for want in ("open", "high", "low", "close"):
        if want in cols:
            rename[cols[want]] = want
    for tcol in ("time", "date", "datetime", "timestamp"):
        if tcol in cols:
            rename[cols[tcol]] = "time"
            break
    df = df.rename(columns=rename)
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
    else:
        df["time"] = pd.RangeIndex(len(df))
    return df.reset_index(drop=True)


def run_backtest(
    df: pd.DataFrame,
    strategy: Optional[Strategy] = None,
    start_equity: float = 10_000.0,
    risk_percent: float = 1.0,
    spread: float = 0.0,
) -> BacktestResult:
    """Simulate the strategy over ``df`` (OHLC). ``spread`` is in price units
    and is applied adversely on both entry and exit to approximate costs."""
    strategy = strategy or Strategy()
    df = _normalise(df)
    df = strategy.prepare(df)

    result = BacktestResult(start_equity=start_equity)
    equity = start_equity
    open_trade: Optional[Trade] = None
    half_spread = spread / 2.0

    for i in range(len(df) - 1):
        bar = df.iloc[i]

        # 1) Manage an open position against THIS bar's range.
        if open_trade is not None:
            hit = _check_exit(open_trade, bar, half_spread)
            if hit is not None:
                exit_price, reason = hit
                _close_trade(open_trade, bar["time"], exit_price, reason, equity, risk_percent)
                equity += open_trade.pnl
                result.equity_curve.append(equity)
                result.trades.append(open_trade)
                open_trade = None

        # 2) If flat, look for a new signal on the just-closed bar i and enter
        #    at bar i+1's open.
        if open_trade is None:
            sig: Optional[Signal] = strategy.signal_at(df, i)
            if sig is not None:
                next_open = float(df.iloc[i + 1]["open"])
                if sig.action == "BUY":
                    entry = next_open + half_spread
                    sl = entry - sig.sl_distance
                    tp = entry + sig.sl_distance * strategy.p["risk_reward"]
                else:
                    entry = next_open - half_spread
                    sl = entry + sig.sl_distance
                    tp = entry - sig.sl_distance * strategy.p["risk_reward"]
                open_trade = Trade(
                    direction=sig.action,
                    entry_time=df.iloc[i + 1]["time"],
                    entry=entry, sl=sl, tp=tp,
                )

    # Close any runner at the last bar's close.
    if open_trade is not None:
        last = df.iloc[-1]
        _close_trade(open_trade, last["time"], float(last["close"]), "eod",
                     equity, risk_percent)
        equity += open_trade.pnl
        result.equity_curve.append(equity)
        result.trades.append(open_trade)

    if not result.equity_curve:
        result.equity_curve.append(equity)
    return result


def _check_exit(trade: Trade, bar, half_spread: float):
    """Return (exit_price, reason) if SL/TP hit this bar, else None.
    Worst-case assumption: if both could trigger, the stop fills first."""
    high, low = float(bar["high"]), float(bar["low"])
    if trade.direction == "BUY":
        if low <= trade.sl:
            return trade.sl - half_spread, "sl"
        if high >= trade.tp:
            return trade.tp - half_spread, "tp"
    else:
        if high >= trade.sl:
            return trade.sl + half_spread, "sl"
        if low <= trade.tp:
            return trade.tp + half_spread, "tp"
    return None


def _close_trade(trade: Trade, t, exit_price: float, reason: str,
                 equity: float, risk_percent: float) -> None:
    risk_dist = abs(trade.entry - trade.sl)
    direction = 1 if trade.direction == "BUY" else -1
    r = ((exit_price - trade.entry) * direction / risk_dist) if risk_dist > 0 else 0.0
    risk_amount = equity * risk_percent / 100.0
    trade.exit_time = t
    trade.exit = exit_price
    trade.reason = reason
    trade.r_multiple = r
    trade.pnl = r * risk_amount


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backtest the studio strategy on an OHLC CSV.")
    ap.add_argument("csv", help="Path to OHLC CSV (columns: time,open,high,low,close)")
    ap.add_argument("--equity", type=float, default=10_000.0)
    ap.add_argument("--risk", type=float, default=1.0, help="Risk %% per trade")
    ap.add_argument("--rr", type=float, default=None, help="Override risk:reward")
    ap.add_argument("--spread", type=float, default=0.0, help="Spread in price units")
    args = ap.parse_args(argv)

    df = pd.read_csv(args.csv)
    params = {}
    if args.rr is not None:
        params["risk_reward"] = args.rr
    strat = Strategy(params)
    result = run_backtest(df, strat, start_equity=args.equity,
                          risk_percent=args.risk, spread=args.spread)
    print(f"\nData: {args.csv}  ({len(df)} candles)")
    print(result.report())


if __name__ == "__main__":
    main()
