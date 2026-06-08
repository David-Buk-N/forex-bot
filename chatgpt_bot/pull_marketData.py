import pandas as pd
import MetaTrader5 as mt5

symbol = "EURUSD"

rates = mt5.copy_rates_from_pos(
    symbol,
    mt5.TIMEFRAME_M5,
    0,
    500
)

df = pd.DataFrame(rates)