import MetaTrader5 as mt5
import pandas as pd

def get_candles(symbol, timeframe, bars):

    rates = mt5.copy_rates_from_pos(
        symbol,
        timeframe,
        0,
        bars
    )

    return pd.DataFrame(rates)