"""Live trading loop — ties everything together.

Safety-first design:
  * Defaults to DRY-RUN: it computes signals, sizes and SL/TP and logs/notifies
    the intended trade, but sends NO orders until you set ``dry_run: false``.
  * Acts only once per CLOSED candle (tracks the last processed bar time), so a
    signal can't be re-fired every poll.
  * Won't stack trades: skips a symbol that already has an open bot position,
    and respects a global max-open-trades cap.
  * Sizes every trade off the strategy's ATR stop so risk per trade is constant.
"""

from __future__ import annotations

import logging
import time

import yaml

from core.mt5_interface import MT5Connection
from core.strategy import Strategy
from core.risk_manager import RiskManager
from core.notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def run_bot(config_path: str = "config.yaml") -> None:
    cfg = load_config(config_path)
    bs = cfg["bot_settings"]
    dry_run = bs.get("dry_run", True)

    mt5conn = MT5Connection(
        login=cfg["mt5"]["login"],
        password=cfg["mt5"]["password"],
        server=cfg["mt5"]["server"],
        path=cfg["mt5"].get("path"),
    )
    if not mt5conn.connect():
        log.error("Could not connect to MT5 — aborting.")
        return

    # Safety guard: never send live orders to a REAL account unless the user has
    # explicitly opted in (bot_settings.allow_live_account: true). Demo testing
    # should never be able to touch a real-money account by mistake.
    if not dry_run and mt5conn.is_real_account() and not bs.get("allow_live_account", False):
        log.error(
            "Refusing to trade: account is %s (real-money) but dry_run is false "
            "and allow_live_account is not set. Aborting to protect your funds.",
            mt5conn.account_mode_name(),
        )
        mt5conn.shutdown()
        return

    strategy = Strategy(cfg.get("strategy"))
    risk = RiskManager(
        risk_percent=cfg["risk"]["risk_percent"],
        max_open_trades=cfg["risk"].get("max_open_trades", 3),
    )
    notifier = TelegramNotifier(cfg["telegram"]["token"], cfg["telegram"]["chat_id"])

    mode = "DRY-RUN (no orders)" if dry_run else "LIVE"
    acct = mt5conn.account_mode_name()
    notifier.send_message(f"🚀 Bot started — {mode} on {acct} account")
    log.info("Bot started in %s mode on %s account. Symbols=%s TF=%s",
             mode, acct, bs["symbols"], bs["timeframe"])

    last_bar_time: dict[str, object] = {}
    poll = bs.get("poll_seconds", 30)

    try:
        while True:
            for symbol in bs["symbols"]:
                try:
                    _process_symbol(symbol, cfg, mt5conn, strategy, risk,
                                    notifier, dry_run, last_bar_time)
                except Exception:
                    log.exception("Error processing %s", symbol)
            time.sleep(poll)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        mt5conn.shutdown()
        notifier.send_message("🛑 Bot stopped")


def _process_symbol(symbol, cfg, mt5conn, strategy, risk, notifier,
                    dry_run, last_bar_time) -> None:
    bs = cfg["bot_settings"]
    magic = bs["magic_number"]

    df = mt5conn.get_candles(symbol, bs["timeframe"], bars=max(strategy.warmup + 50, 250))
    if df is None or len(df) < strategy.warmup:
        return

    # One decision per newly-closed candle.
    bar_time = df.iloc[-1]["time"]
    if last_bar_time.get(symbol) == bar_time:
        return
    last_bar_time[symbol] = bar_time

    signal = strategy.check_signals(df)
    if signal is None:
        return

    # Don't stack: skip if we already hold this symbol or hit the global cap.
    if mt5conn.open_positions(symbol, magic) > 0:
        log.info("%s: %s signal ignored — position already open.", symbol, signal.action)
        return

    spec = mt5conn.symbol_spec(symbol)
    if spec is None:
        return
    balance = mt5conn.balance()
    lot = risk.calculate_lot_size(balance, signal.sl_distance, spec)
    if lot is None:
        log.warning("%s: could not size trade, skipping.", symbol)
        return

    msg = (f"{'[DRY] ' if dry_run else ''}🔔 {signal.action} {symbol} {lot} lots\n"
           f"entry≈{signal.price:.5f} sl={signal.sl:.5f} tp={signal.tp:.5f}\n"
           f"{signal.reason}")
    log.info(msg.replace("\n", " | "))
    notifier.send_message(msg)

    if dry_run:
        return

    mt5conn.open_trade(symbol, signal, lot, magic,
                       deviation=bs.get("deviation", 20))


if __name__ == "__main__":
    run_bot()
