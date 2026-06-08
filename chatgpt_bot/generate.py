last = df.iloc[-1]

buy_signal = (
    last["ema20"] > last["ema50"]
    and last["rsi"] > 55
)

sell_signal = (
    last["ema20"] < last["ema50"]
    and last["rsi"] < 45
)