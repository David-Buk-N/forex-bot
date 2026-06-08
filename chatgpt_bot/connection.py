####Make sure:
#MT5 is installed
#You're logged into your broker account
#MT5 is open while the bot runs

import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 connection failed")
    quit()

print("Connected")