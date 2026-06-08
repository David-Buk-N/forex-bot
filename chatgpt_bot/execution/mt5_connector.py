import MetaTrader5 as mt5

def connect():

    if not mt5.initialize():
        raise Exception("MT5 connection failed")

    print("Connected to MT5")