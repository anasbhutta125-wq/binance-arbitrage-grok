"""Core funding rate arbitrage strategy logic."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
from loguru import logger

from src.data.market_data import MarketDataService, SymbolSnapshot
from src.utils.config import AppConfig
from src.utils.helpers import utc_now


class Side(str, Enum):
    LONG_SPOT_SHORT_PERP = "long_spot_short_perp"
    SHORT_SPOT_LONG_PERP = "short_spot_long_perp"


class SignalAction(str, Enum):
    ENTER = "enter"
    EXIT = "exit"
    REBALANCE = "rebalance"
    HOLD = "hold"
    NONE = "none"


@dataclass
class Signal:
    symbol: str
    action: SignalAction
    side: Optional[Side] = None
    size_usdt: float = 0.0
    reason: str = ""
    snapshot: Optional[SymbolSnapshot] = None
    timestamp: datetime = field(default_factory=utc_now)


@dataclass
class OpenPosition:
    symbol: str
    side: Side
    entry_time: datetime
    size_usdt: float
    entry_funding_rate: float
    entry_basis: float
    spot_qty: float = 0.0
    perp_qty: float = 0.0
    realized_funding: float = 0.0
    last_rebalance: datetime = field(default_factory=utc_now)


class FundingArbStrategy:
    def __init__(self, config: AppConfig, market_data: MarketDataService):
        self.config = config
        self.market_data = market_data
        self.positions: Dict[str, OpenPosition] = {}

    def generate_signals(self) -> List[Signal]:
        signals: List[Signal] = []
        for symbol in self.config.strategy.symbols:
            snap = self.market_data.get(symbol)
            if not snap:
                continue
            signal = self._evaluate_symbol(symbol, snap)
            if signal.action != SignalAction.NONE:
                signals.append(signal)
        return signals

    def _evaluate_symbol(self, symbol: str, snap: SymbolSnapshot) -> Signal:
        pos = self.positions.get(symbol)
        if pos:
            return self._manage_open_position(pos, snap)
        return self._check_entry(symbol, snap)

    def _check_entry(self, symbol: str, snap: SymbolSnapshot) -> Signal:
        cfg = self.config.strategy
        if len(self.positions) >= self.config.risk.max_open_positions:
            return Signal(symbol, SignalAction.NONE, reason="max positions reached")
        if abs(snap.basis) > cfg.max_basis_pct:
            return Signal(symbol, SignalAction.NONE, reason=f"basis too wide ({snap.basis*100:.3f}%)")
        if snap.projected_apr >= cfg.min_funding_apr and snap.funding_rate > 0:
            size = min(cfg.position_size_usdt, self._remaining_capacity())
            if size < 10:
                return Signal(symbol, SignalAction.NONE, reason="insufficient capacity")
            return Signal(symbol=symbol, action=SignalAction.ENTER, side=Side.LONG_SPOT_SHORT_PERP, size_usdt=size, reason=f"positive funding APR {snap.projected_apr*100:.1f}%", snapshot=snap)
        if snap.projected_apr <= -cfg.min_funding_apr and snap.funding_rate < 0:
            size = min(cfg.position_size_usdt, self._remaining_capacity())
            if size < 10:
                return Signal(symbol, SignalAction.NONE, reason="insufficient capacity")
            return Signal(symbol=symbol, action=SignalAction.ENTER, side=Side.SHORT_SPOT_LONG_PERP, size_usdt=size, reason=f"negative funding APR {snap.projected_apr*100:.1f}%", snapshot=snap)
        return Signal(symbol, SignalAction.NONE, reason="funding below threshold")

    def _manage_open_position(self, pos: OpenPosition, snap: SymbolSnapshot) -> Signal:
        cfg = self.config.strategy
        hold_hours = (utc_now() - pos.entry_time).total_seconds() / 3600
        if hold_hours < cfg.min_hold_hours:
            return Signal(pos.symbol, SignalAction.HOLD, reason="min hold time")
        if pos.side == Side.LONG_SPOT_SHORT_PERP:
            if snap.projected_apr < cfg.exit_funding_apr or snap.funding_rate <= 0:
                return Signal(pos.symbol, SignalAction.EXIT, side=pos.side, reason=f"funding faded to {snap.projected_apr*100:.1f}% APR", snapshot=snap)
        else:
            if snap.projected_apr > -cfg.exit_funding_apr or snap.funding_rate >= 0:
                return Signal(pos.symbol, SignalAction.EXIT, side=pos.side, reason="negative funding faded", snapshot=snap)
        return Signal(pos.symbol, SignalAction.HOLD, reason="position healthy")

    def _remaining_capacity(self) -> float:
        used = sum(p.size_usdt for p in self.positions.values())
        return max(0.0, self.config.strategy.max_total_exposure_usdt - used)

    def register_position(self, pos: OpenPosition) -> None:
        self.positions[pos.symbol] = pos
        logger.info(f"Position registered: {pos.symbol} {pos.side.value} {pos.size_usdt} USDT")

    def remove_position(self, symbol: str) -> None:
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"Position removed: {symbol}")

    def get_position(self, symbol: str) -> Optional[OpenPosition]:
        return self.positions.get(symbol)
