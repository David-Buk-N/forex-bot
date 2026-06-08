mt5_forex_bot/
│
├── main.py                 # Entry point: Runs the trading loop
├── config.yaml             # Secret keys, MT5 credentials, and pair settings
├── requirements.txt        # Python dependencies
│
├── core/
│   ├── mt5_interface.py    # Handles connection, data fetching, and order execution
│   ├── strategy.py         # Signal logic (e.g., EMA Cross, RSI)
│   ├── risk_manager.py     # Position sizing and SL/TP calculations
│   └── notifier.py         # Telegram bot integration
│
├── backtesting/
│   └── backtester.py       # Script to test strategy on historical CSV data
│
├── logs/                   # Folder for daily log files
│   └── trading_log.log
│
└── data/                   # Storage for downloaded historical data

pip install MetaTrader5
pip install pandas
pip install ta
pip install requests