#Since MT5's Python API is for live trading, for backtesting you usually use Backtrader or a manual loop.

import pandas as pd
from core.strategy import Strategy

def run_backtest(csv_file):
    df = pd.read_csv(csv_file)
    balance = 10000
    positions = []
    
    # Simple loop simulation
    for i in range(50, len(df)):
        window = df.iloc[:i]
        signal = Strategy.check_signals(window)
        
        if signal == "BUY":
            # Logic for entry/exit simulation
            pass
            
    print("Backtest Complete")

# run_backtest("data/eurusd_h1.csv")