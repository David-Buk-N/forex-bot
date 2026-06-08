def generate(df):

    candle = df.iloc[-1]

    if (
        candle["ema20"] > candle["ema50"]
        and candle["rsi"] > 55
    ):
        return "BUY"

    if (
        candle["ema20"] < candle["ema50"]
        and candle["rsi"] < 45
    ):
        return "SELL"

    return None