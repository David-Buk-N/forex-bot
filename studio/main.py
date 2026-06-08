#This ties everything together.

import MetaTrader5 as mt5
import yaml
import time
from core.mt5_interface import MT5Connection
from core.strategy import Strategy
from core.notifier import TelegramNotifier

def run_bot():
    # 1. Load Config
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    # 2. Connect to MT5
    if not mt5.initialize(login=config['mt5']['login'], password=config['mt5']['password'], server=config['mt5']['server']):
        print("MT5 Initialization Failed")
        return

    notifier = TelegramNotifier(config['telegram']['token'], config['telegram']['chat_id'])
    notifier.send_message("🚀 Bot Started")

    while True:
        try:
            for symbol in config['bot_settings']['symbols']:
                # Get Data
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
                df = pd.DataFrame(rates)
                
                # Check Strategy
                signal = Strategy.check_signals(df)
                
                if signal != "WAIT":
                    # Execute Trade Logic (simplified)
                    print(f"Executing {signal} for {symbol}")
                    notifier.send_message(f"🔔 Signal: {signal} on {symbol}")
                    # Here you would call mt5.order_send()
            
            time.sleep(60) # Wait for next candle
        except KeyboardInterrupt:
            break

    mt5.shutdown()

if __name__ == "__main__":
    run_bot()