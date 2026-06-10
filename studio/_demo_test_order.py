"""Controlled live-execution test on the DEMO account.

Sends ONE small EURUSD order through the bot's own MT5Connection.open_trade()
(with real ATR-based SL/TP), confirms it appears as an open position with SL/TP
attached, then CLOSES it. Proves the live order path works end to end.

Safe to delete after testing. Refuses to run on a REAL account.
"""
from __future__ import annotations

import logging

from main import load_config
from core.mt5_interface import MT5Connection
from core.strategy import Strategy, Signal
from core.risk_manager import RiskManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("test_order")

SYMBOL = "EURUSD"


def close_position(conn, pos) -> None:
    mt5 = conn.mt5
    tick = mt5.symbol_info_tick(pos.symbol)
    is_buy = pos.type == mt5.ORDER_TYPE_BUY
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "position": pos.ticket,
        "price": tick.bid if is_buy else tick.ask,
        "deviation": 20,
        "magic": pos.magic,
        "comment": "ForexBot-close-test",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": conn.filling_mode(pos.symbol),
    }
    res = mt5.order_send(req)
    ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
    log.info("Close %s: retcode=%s", "OK" if ok else "FAILED",
             getattr(res, "retcode", "no result"))


def main() -> None:
    cfg = load_config("config.yaml")
    bs = cfg["bot_settings"]
    magic = bs["magic_number"]

    conn = MT5Connection(cfg["mt5"]["login"], cfg["mt5"]["password"],
                         cfg["mt5"]["server"], cfg["mt5"].get("path"))
    if not conn.connect():
        return
    if conn.is_real_account():
        log.error("REAL account — refusing to send a test order.")
        conn.shutdown()
        return
    if not conn.mt5.terminal_info().trade_allowed:
        log.error("AutoTrading is OFF in the terminal (trade_allowed=False). "
                  "Click the green 'Algo Trading' button in MT5, then re-run. Aborting.")
        conn.shutdown()
        return

    strat = Strategy(cfg.get("strategy"))
    risk = RiskManager(cfg["risk"]["risk_percent"], cfg["risk"].get("max_open_trades", 3))

    # Build a realistic BUY signal from current price + live ATR.
    df = conn.get_candles(SYMBOL, bs["timeframe"], bars=max(strat.warmup + 50, 250))
    atr = float(strat.prepare(df).iloc[-1]["atr"])
    tick = conn.mt5.symbol_info_tick(SYMBOL)
    price = tick.ask
    sl_dist = atr * strat.p["atr_sl_mult"]
    sig = Signal(action="BUY", price=price,
                 sl=price - sl_dist, tp=price + sl_dist * strat.p["risk_reward"],
                 atr=atr, reason="MANUAL EXECUTION TEST (not a strategy signal)")

    spec = conn.symbol_spec(SYMBOL)
    lot = risk.calculate_lot_size(conn.balance(), sig.sl_distance, spec)
    print(f"\n=== TEST ORDER: BUY {SYMBOL} {lot} lots | "
          f"entry~{price:.5f} sl={sig.sl:.5f} tp={sig.tp:.5f} (atr={atr:.5f}) ===")

    before = conn.open_positions(SYMBOL, magic)
    result = conn.open_trade(SYMBOL, sig, lot, magic, deviation=bs.get("deviation", 20))
    rc = getattr(result, "retcode", None)
    print(f"order_send retcode={rc} (DONE={conn.mt5.TRADE_RETCODE_DONE})")
    if rc != conn.mt5.TRADE_RETCODE_DONE:
        print(f"  comment: {getattr(result, 'comment', '?')}")
        conn.shutdown()
        return

    # Confirm it actually opened with SL/TP attached.
    positions = [p for p in (conn.mt5.positions_get(symbol=SYMBOL) or []) if p.magic == magic]
    print(f"open positions for {SYMBOL} (magic {magic}): {before} -> {len(positions)}")
    for p in positions:
        print(f"  ticket={p.ticket} type={'BUY' if p.type==0 else 'SELL'} "
              f"vol={p.volume} open={p.price_open:.5f} sl={p.sl:.5f} tp={p.tp:.5f} "
              f"profit={p.profit:.2f}")

    # Close it so we don't leave a stray position behind.
    print("\n--- closing the test position ---")
    for p in positions:
        close_position(conn, p)
    remaining = [p for p in (conn.mt5.positions_get(symbol=SYMBOL) or []) if p.magic == magic]
    print(f"remaining open (magic {magic}): {len(remaining)}")

    print("\n=== execution test complete ===")
    conn.shutdown()


if __name__ == "__main__":
    main()
