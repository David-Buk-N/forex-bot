# Forex Bot (studio)

MetaTrader 5 trading bot with a confirmation-based strategy, ATR risk
management, a real backtester, and Telegram alerts.

## Layout

```
studio/
├── main.py                 # Live loop (dry-run by default — sends no orders)
├── config.yaml             # Credentials, symbols, strategy & risk params
├── requirements.txt
│
├── core/
│   ├── indicators.py       # EMA / RSI / ATR in pure pandas (no ta/pandas_ta)
│   ├── strategy.py         # Trend + trigger + momentum confirmation, ATR SL/TP
│   ├── risk_manager.py     # Tick-value-based position sizing
│   ├── mt5_interface.py    # Connection, closed-candle data, order execution
│   └── notifier.py         # Telegram alerts
│
├── backtesting/
│   └── backtester.py       # Event-driven backtest with win-rate/PF/drawdown
│
├── tools/
│   └── export_data.py      # Pull candles from MT5, or generate sample data
│
└── data/                   # CSVs for backtesting (created on demand)
```

## Strategy

A trade is taken only when **three** independent checks agree, which cuts the
false signals a bare EMA crossover produces in ranging markets:

1. **Trend** — price on the correct side of EMA200 (don't fight the trend).
2. **Trigger** — a fresh EMA fast/slow cross on the just-closed candle.
3. **Momentum** — RSI confirms direction and isn't at an exhausted extreme.

Stops and targets are **ATR-based** (volatility-adaptive), and every decision is
made on a **closed** candle to avoid repainting.

## Quick start

```bash
pip install -r requirements.txt

# 1) Try the strategy with no broker/account needed:
python tools/export_data.py sample --out data/sample_EURUSD.csv --bars 6000
python backtesting/backtester.py data/sample_EURUSD.csv --risk 1 --rr 2

# 2) Backtest on real data exported from MT5:
python tools/export_data.py export EURUSD M15 5000 --out data/EURUSD_M15.csv
python backtesting/backtester.py data/EURUSD_M15.csv

# 3) Live: edit config.yaml (credentials + symbols). It starts in DRY-RUN.
#    Set bot_settings.dry_run: false only after you're happy with backtests.
python main.py
```

## Safety notes

- **Dry-run is the default.** `main.py` logs and Telegram-notifies the trade it
  *would* place but sends no orders until you set `dry_run: false`.
- Test on a **demo account** first. Backtest results are not guarantees.
- Don't commit real credentials — keep `config.yaml` out of version control
  (e.g. add it to `.gitignore` and commit a `config.example.yaml` instead).
```
