import MetaTrader5 as mt5

def buy(symbol, volume):

    tick = mt5.symbol_info_tick(symbol)

    request = {

        "action": mt5.TRADE_ACTION_DEAL,

        "symbol": symbol,

        "volume": volume,

        "type": mt5.ORDER_TYPE_BUY,

        "price": tick.ask,

        "deviation": 20,

        "magic": 123456,

        "comment": "ForexBot"
    }

    return mt5.order_send(request)