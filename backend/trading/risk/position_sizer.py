"""
Kelly Criterion position sizer.

References:
  - Edward O. Thorp, "Beat the Dealer" / "The Mathematics of Gambling"
  - Optimal f (Ralph Vince) as alternative

Owner 2026-11-14: these helpers stay in the repo (lab / explicit opt-in).
The default worker and harness auto-buy path does not call them to set qty.
Set ``CGAB_AUTO_KELLY_SIZER=1`` to restore ``min(qty_kelly, qty_risk)``.
That flag does not enable live trading.
"""
from __future__ import annotations

import os


def kelly_fraction(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    kelly_fraction_scale: float = 0.5,
    max_fraction: float = 0.25,
) -> float:
    """
    Full-Kelly formula: f* = (p*b - q) / b
      p = win_rate
      q = 1 - win_rate
      b = avg_win_pct / avg_loss_pct  (win/loss ratio)

    We use Half-Kelly (scale=0.5) by default — industry standard to reduce
    variance while keeping ~75% of the theoretical growth rate.

    Args:
        win_rate:            Historical win rate  0.0–1.0
        avg_win_pct:         Average winning trade size as decimal (e.g. 0.08 = 8%)
        avg_loss_pct:        Average losing trade size as decimal (e.g. 0.04 = 4%)
        kelly_fraction_scale: Fraction of full Kelly to use (0.5 = half-Kelly)
        max_fraction:        Hard cap on position size as fraction of portfolio

    Returns:
        Recommended position size as a fraction of portfolio (0.0–max_fraction)
    """
    if avg_loss_pct <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0.0

    b = avg_win_pct / avg_loss_pct          # win/loss ratio
    q = 1.0 - win_rate
    f_star = (win_rate * b - q) / b         # full Kelly

    # Scale down (half-Kelly default) and clamp
    f_scaled = f_star * kelly_fraction_scale
    return float(max(0.0, min(f_scaled, max_fraction)))


def position_size_dollars(
    portfolio_value: float,
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    kelly_fraction_scale: float = 0.5,
    max_fraction: float = 0.25,
) -> float:
    """Return the recommended dollar allocation for a single position."""
    fraction = kelly_fraction(
        win_rate, avg_win_pct, avg_loss_pct,
        kelly_fraction_scale, max_fraction,
    )
    return portfolio_value * fraction


def shares_to_buy(
    portfolio_value: float,
    current_price: float,
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    kelly_fraction_scale: float = 0.5,
    max_fraction: float = 0.25,
    min_shares: int = 1,
) -> int:
    """Return whole number of shares to buy, floored to min_shares."""
    if current_price <= 0:
        return 0
    dollars = position_size_dollars(
        portfolio_value, win_rate, avg_win_pct, avg_loss_pct,
        kelly_fraction_scale, max_fraction,
    )
    shares = int(dollars / current_price)
    return max(shares, min_shares) if dollars > 0 else 0


def auto_kelly_sizer_enabled() -> bool:
    """True only when the auto path is explicitly opted back into Kelly.

    Default is off. Owner closed Kelly (and half-Kelly) for live position
    sizing on the worker / harness auto-buy path. The functions above remain.
    """
    raw = os.getenv("CGAB_AUTO_KELLY_SIZER", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def quantity_after_kelly_gate(qty_risk: int, qty_kelly: int, *, use_kelly: bool) -> int:
    """Combine 1R size with the retained Kelly size.

    Default (``use_kelly=False``): return the risk-unit quantity. Kelly is
    not a ``min()`` input. Opt-in keeps the previous ``min(kelly, risk)``
    and still returns 0 when either leg is 0.
    """
    try:
        risk = int(qty_risk)
        kelly = int(qty_kelly)
    except (TypeError, ValueError):
        return 0
    if not use_kelly:
        return max(0, risk)
    if kelly > 0 and risk > 0:
        return min(kelly, risk)
    return 0


def cap_shares_to_notional(shares: float, price: float, max_notional: float) -> int:
    """Floor share count so price * qty never exceeds the order notional cap."""
    try:
        qty = int(shares)
        px = float(price)
        cap = float(max_notional)
    except (TypeError, ValueError):
        return 0
    if qty <= 0 or px <= 0 or cap <= 0:
        return 0
    return max(0, min(qty, int(cap // px)))
