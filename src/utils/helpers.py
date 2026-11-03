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
