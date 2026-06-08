#Strategy module
#This is where you define your "buy/sell" logic

import pandas as pd
import pandas_ta as ta

class Strategy:
    @staticmethod
    def check_signals(df):
        # Example: Simple EMA Cross
        df['ema_fast'] = ta.ema(df['close'], length=9)
        df['ema_slow'] = ta.ema(df['close'], length=21)
        
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        if prev_row['ema_fast'] < prev_row['ema_slow'] and last_row['ema_fast'] > last_row['ema_slow']:
            return "BUY"
        elif prev_row['ema_fast'] > prev_row['ema_slow'] and last_row['ema_fast'] < last_row['ema_slow']:
            return "SELL"
        return "WAIT"