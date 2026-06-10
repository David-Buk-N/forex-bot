"""Position sizing.

The old version did ``amount_to_risk / (stop_loss_pips * 10)`` which only
happens to be roughly right for a 5-digit EUR-quoted pair and is wrong for
gold, JPY pairs, indices, etc. Correct sizing converts the money you're willing
to lose into a lot size using the instrument's *money value per price unit*,
which MT5 exposes via ``trade_tick_value`` / ``trade_tick_size``.

    loss per lot  = (sl_distance_price / tick_size) * tick_value
    lot           = risk_amount / loss_per_lot

The result is then snapped to the broker's volume step and clamped to
[volume_min, volume_max].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SymbolSpec:
    """The subset of MT5 ``symbol_info`` we need for sizing.

    Build it from a live symbol with ``SymbolSpec.from_mt5(info)``.
    """
    tick_value: float   # account-currency value of one tick, per 1.0 lot
    tick_size: float    # smallest price increment
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01

    @classmethod
    def from_mt5(cls, info) -> "SymbolSpec":
        return cls(
            tick_value=info.trade_tick_value,
            tick_size=info.trade_tick_size,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
        )


class RiskManager:
    def __init__(self, risk_percent: float = 1.0, max_open_trades: int = 3):
        # risk_percent is a percentage, e.g. 1.0 means risk 1% of balance.
        self.risk_percent = risk_percent
        self.max_open_trades = max_open_trades

    def risk_amount(self, balance: float) -> float:
        return balance * self.risk_percent / 100.0

    def calculate_lot_size(
        self,
        balance: float,
        sl_distance_price: float,
        spec: SymbolSpec,
    ) -> Optional[float]:
        """Lot size that risks ``risk_percent`` of balance if the stop is hit.

        Returns ``None`` when inputs are unusable (so callers can skip the
        trade rather than send a bogus order).
        """
        if sl_distance_price <= 0 or spec.tick_size <= 0 or spec.tick_value <= 0:
            return None

        loss_per_lot = (sl_distance_price / spec.tick_size) * spec.tick_value
        if loss_per_lot <= 0:
            return None

        raw_lot = self.risk_amount(balance) / loss_per_lot
        lot = self._round_to_step(raw_lot, spec.volume_step)
        lot = max(spec.volume_min, min(lot, spec.volume_max))

        # If even the smallest allowed lot risks materially more than intended,
        # let the caller decide — but we still return volume_min so a trade is
        # possible on tiny accounts.
        return lot

    @staticmethod
    def _round_to_step(value: float, step: float) -> float:
        if step <= 0:
            return round(value, 2)
        steps = round(value / step)
        return round(steps * step, 8)
