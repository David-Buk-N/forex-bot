#Risk manager file

class RiskManager:
    def __init__(self, risk_per_trade=0.01):
        self.risk_per_trade = risk_per_trade

    def calculate_lot_size(self, balance, stop_loss_pips, symbol):
        # Basic calculation: Risking 1% of balance
        # In a real bot, you'd calculate based on symbol tick value
        amount_to_risk = balance * self.risk_per_trade
        # Placeholder logic for lot size
        lot_size = amount_to_risk / (stop_loss_pips * 10) 
        return round(max(0.01, lot_size), 2)