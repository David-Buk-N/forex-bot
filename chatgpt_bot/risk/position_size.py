def calculate_lot_size(
        balance,
        risk_percent,
        stop_loss_pips,
        pip_value):

    risk_amount = (
        balance *
        risk_percent / 100
    )

    lot_size = (
        risk_amount /
        (stop_loss_pips * pip_value)
    )

    return round(lot_size, 2)

#Example:
#Balance = $1,000
#Risk = 1%
#SL = 20 pips
#Maximum loss = $10