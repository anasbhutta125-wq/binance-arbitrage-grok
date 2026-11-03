"""Small utility helpers."""

from datetime import datetime, timezone
from typing import Optional
import math


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def annualized_funding(rate: float, interval_hours: float = 8.0) -> float:
    """Convert a single funding rate into approximate APR.
    
    Binance funding is usually every 8 hours → 3 payments per day.
    """
    payments_per_year = (365 * 24) / interval_hours
    return rate * payments_per_year


def net_apr_after_fees(
    funding_rate: float,
    interval_hours: float = 8.0,
    round_trip_fee_pct: float = 0.0016,
    expected_hold_hours: float = 24.0,
    borrow_apr: float = 0.0,
) -> float:
    """
    Estimate net annualized return after trading fees (and optional borrow cost).
    """
    gross_apr = annualized_funding(funding_rate, interval_hours)
    if expected_hold_hours <= 0:
        expected_hold_hours = 24.0
    holds_per_year = (365 * 24) / expected_hold_hours
    fee_drag_apr = round_trip_fee_pct * holds_per_year
    net = gross_apr - fee_drag_apr - borrow_apr
    return net


def basis_pct(perp_price: float, spot_price: float) -> float:
    if spot_price <= 0:
        return 0.0
    return (perp_price - spot_price) / spot_price


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default


def round_step(value: float, step: float) -> float:
    """Round down to exchange step size."""
    if step <= 0:
        return value
    precision = max(0, -int(math.floor(math.log10(step))))
    return math.floor(value / step) * step


def format_usdt(value: float) -> str:
    return f"{value:,.2f} USDT"
