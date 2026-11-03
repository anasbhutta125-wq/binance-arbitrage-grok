"""Risk management and circuit breakers + live liquidation monitoring."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Any
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
    last_liq_check: Optional[datetime] = None


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

    def liquidation_distance_pct(self, liquidation_price: float, mark_price: float, side: str) -> float:
        if liquidation_price <= 0 or mark_price <= 0:
            return 1.0
        if side == "short":
            return (liquidation_price - mark_price) / mark_price
        return (mark_price - liquidation_price) / mark_price

    async def check_open_positions_liquidation(self, positions: Dict[str, Any], client) -> List[str]:
        danger_symbols: List[str] = []
        if not positions:
            return danger_symbols
        try:
            live_positions = await client.fetch_positions(list(positions.keys()))
        except Exception as e:
            logger.error(f"Failed to fetch live positions for liq check: {e}")
            return danger_symbols

        for lp in live_positions:
            symbol = lp.get("symbol")
            if not symbol or symbol not in positions:
                continue
            contracts = float(lp.get("contracts") or 0)
            if abs(contracts) < 1e-8:
                continue
            entry_side = "short" if contracts < 0 else "long"
            mark = float(lp.get("markPrice") or lp.get("info", {}).get("markPrice") or 0)
            liq = float(lp.get("liquidationPrice") or lp.get("info", {}).get("liquidationPrice") or 0)
            if liq <= 0 or mark <= 0:
                continue
            dist = self.liquidation_distance_pct(liq, mark, entry_side)
            logger.debug(f"Liq check {symbol}: side={entry_side} mark={mark:.2f} liq={liq:.2f} distance={dist*100:.1f}%")
            if dist < self.config.risk.liquidation_buffer_pct:
                logger.critical(f"LIQUIDATION DANGER {symbol}: only {dist*100:.1f}% away (buffer {self.config.risk.liquidation_buffer_pct*100:.0f}%)")
                danger_symbols.append(symbol)

        self.state.last_liq_check = utc_now()
        return danger_symbols

    def _halt(self, reason: str) -> None:
        self.state.halted = True
        self.state.halt_reason = reason
        logger.critical(f"RISK HALT: {reason}")

    def resume(self) -> None:
        self.state.halted = False
        self.state.halt_reason = ""
        logger.warning("Risk halt manually cleared")
