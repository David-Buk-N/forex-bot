"""One-shot demo connectivity + signal diagnostic (no orders, no infinite loop).

Exercises the same classes main.py uses: MT5Connection, Strategy, RiskManager.
Safe to delete after testing.
"""
from __future__ import annotations

import logging

from main import load_config
from core.mt5_interface import MT5Connection
from core.strategy import Strategy
from core.risk_manager import RiskManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("demo_check")


def main() -> None:
    cfg = load_config("config.yaml")
    bs = cfg["bot_settings"]

    conn = MT5Connection(
        login=cfg["mt5"]["login"],
        password=cfg["mt5"]["password"],
        server=cfg["mt5"]["server"],
        path=cfg["mt5"].get("path"),
    )
    if not conn.connect():
        log.error("CONNECT FAILED — see error above.")
        return

    mode = conn.account_mode_name()
    print(f"\n=== ACCOUNT: {mode} | balance={conn.balance():.2f} ===")
    if mode == "REAL":
        print("!!! This is a REAL account. Stopping the diagnostic. !!!")
        conn.shutdown()
        return

    strat = Strategy(cfg.get("strategy"))
    risk = RiskManager(cfg["risk"]["risk_percent"], cfg["risk"].get("max_open_trades", 3))
    balance = conn.balance()

    for symbol in bs["symbols"]:
        print(f"\n--- {symbol} ({bs['timeframe']}) ---")
        df = conn.get_candles(symbol, bs["timeframe"], bars=max(strat.warmup + 50, 250))
        if df is None or len(df) < strat.warmup:
            print(f"  no/insufficient data (got {0 if df is None else len(df)}, "
                  f"need {strat.warmup}) — market closed or symbol unavailable?")
            continue

        prepared = strat.prepare(df)
        last = prepared.iloc[-1]
        print(f"  bars={len(df)}  last_closed={last['time']}  close={last['close']:.5f}")
        print(f"  ema_fast={last['ema_fast']:.5f} ema_slow={last['ema_slow']:.5f} "
              f"ema_trend={last['ema_trend']:.5f} rsi={last['rsi']:.1f} atr={last['atr']:.5f}")

        spec = conn.symbol_spec(symbol)
        if spec is None:
            print("  symbol_spec unavailable — can't size.")
        else:
            print(f"  spec: tick_value={spec.tick_value} tick_size={spec.tick_size} "
                  f"vol[min={spec.volume_min} step={spec.volume_step} max={spec.volume_max}]")

        sig = strat.check_signals(df)
        if sig is None:
            print("  signal: NONE on the latest closed candle.")
            continue

        lot = risk.calculate_lot_size(balance, sig.sl_distance, spec) if spec else None
        print(f"  >>> SIGNAL: {sig.action} | entry≈{sig.price:.5f} "
              f"sl={sig.sl:.5f} tp={sig.tp:.5f} lot={lot}")
        print(f"      reason: {sig.reason}")
        print(f"      [DRY-RUN] no order sent.")

    conn.shutdown()
    print("\n=== diagnostic complete (no orders sent) ===")


if __name__ == "__main__":
    main()
