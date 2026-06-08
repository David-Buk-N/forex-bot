from execution.mt5_connector import connect
from data.market_data import get_candles
from data.indicators import calculate
from strategy.ema_rsi import generate

connect()

while True:

    df = get_candles(
        "EURUSD",
        5,
        500
    )

    df = calculate(df)

    signal = generate(df)

    if signal:

        print(signal)

    time.sleep(300)