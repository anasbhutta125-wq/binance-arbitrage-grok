"""Risk management and circuit breakers."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, Optional
from loguru import logger

from src.utils.config import AppConfig
from src.utils.helpers import utc_now


@dataclass
class RiskState:
    daily_pnl: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    last_reset_day: date = field(default_factory=lambda: utc_now().date())
    halted: bool = False
    halt_reason: str = ""


class RiskManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self.state = RiskState()

    def update_equity(self, equity: float) -> None:
        today = utc_now().date()
        if today != self.state.last_reset_day:
            self.state.daily_pnl = 0.0
            self.state.last_reset_day = today
            logger.info("Daily PnL reset")

        self.state.current_equity = equity
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity

    def record_pnl(self, pnl: float) -> None:
        self.state.daily_pnl += pnl

    def check_can_trade(self) -> tuple[bool, str]:
        if self.state.halted:
            return False, f"Trading halted: {self.state.halt_reason}"

        if self.state.daily_pnl <= -abs(self.config.risk.max_daily_loss_usdt):
            self._halt(f"Daily loss limit hit ({self.state.daily_pnl:.2f} USDT)")
            return False, self.state.halt_reason

        if self.state.peak_equity > 0:
            dd = (self.state.peak_equity - self.state.current_equity) / self.state.peak_equity
            if dd >= self.config.risk.max_drawdown_pct:
                self._halt(f"Max drawdown hit ({dd*100:.2f}%)")
                return False, self.state.halt_reason

        return True, "OK"

    def check_liquidation_distance(self, liquidation_price: float, mark_price: float, side: str) -> bool:
        if liquidation_price <= 0 or mark_price <= 0:
            return False
        if side == "short":
            distance = (liquidation_price - mark_price) / mark_price
        else:
            distance = (mark_price - liquidation_price) / mark_price
        return distance < self.config.risk.liquidation_buffer_pct

    def _halt(self, reason: str) -> None:
        self.state.halted = True
        self.state.halt_reason = reason
        logger.critical(f"RISK HALT: {reason}")

    def resume(self) -> None:
        self.state.halted = False
        self.state.halt_reason = ""
        logger.warning("Risk halt manually cleared")
