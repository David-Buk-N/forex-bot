from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

df["ema20"] = EMAIndicator(
    df["close"],
    window=20
).ema_indicator()

df["ema50"] = EMAIndicator(
    df["close"],
    window=50
).ema_indicator()

df["rsi"] = RSIIndicator(
    df["close"],
    window=14
).rsi()