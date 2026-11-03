"""Market data collector and cache."""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from loguru import logger

from src.data.exchange_client import ExchangeClient
from src.utils.config import AppConfig
from src.utils.helpers import annualized_funding, basis_pct, utc_now


@dataclass
class SymbolSnapshot:
    symbol: str
    funding_rate: float = 0.0
    next_funding_time: Optional[datetime] = None
    mark_price: float = 0.0
    index_price: float = 0.0
    spot_price: float = 0.0
    basis: float = 0.0
    projected_apr: float = 0.0
    timestamp: datetime = field(default_factory=utc_now)

    def is_positive_funding(self) -> bool:
        return self.funding_rate > 0


class MarketDataService:
    def __init__(self, client: ExchangeClient, config: AppConfig):
        self.client = client
        self.config = config
        self.snapshots: Dict[str, SymbolSnapshot] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("MarketDataService started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MarketDataService stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.refresh_all()
            except Exception as e:
                logger.error(f"Market data refresh error: {e}")
            await asyncio.sleep(self.config.data.funding_update_interval_sec)

    async def refresh_all(self) -> None:
        for symbol in self.config.strategy.symbols:
            try:
                await self.refresh_symbol(symbol)
            except Exception as e:
                logger.error(f"Failed to refresh {symbol}: {e}")

    async def refresh_symbol(self, symbol: str) -> SymbolSnapshot:
        fr = await self.client.fetch_funding_rate(symbol)
        funding_rate = float(fr.get("fundingRate") or fr.get("info", {}).get("lastFundingRate") or 0)
        next_ts = fr.get("fundingTimestamp") or fr.get("info", {}).get("nextFundingTime")
        next_funding = None
        if next_ts:
            next_funding = datetime.fromtimestamp(int(next_ts) / 1000, tz=timezone.utc)

        ticker = await self.client.fetch_ticker(symbol)
        mark_price = float(ticker.get("last") or ticker.get("info", {}).get("markPrice") or 0)
        index_price = float(ticker.get("info", {}).get("indexPrice") or mark_price)

        spot_symbol = symbol.split(":")[0] if ":" in symbol else symbol
        try:
            spot_ticker = await self.client.fetch_spot_ticker(spot_symbol)
            spot_price = float(spot_ticker.get("last") or 0)
        except Exception:
            spot_price = index_price
            logger.debug(f"Spot fetch failed for {spot_symbol}, using index price")

        basis = basis_pct(mark_price, spot_price)
        apr = annualized_funding(funding_rate)

        snap = SymbolSnapshot(
            symbol=symbol,
            funding_rate=funding_rate,
            next_funding_time=next_funding,
            mark_price=mark_price,
            index_price=index_price,
            spot_price=spot_price,
            basis=basis,
            projected_apr=apr,
            timestamp=utc_now(),
        )
        self.snapshots[symbol] = snap
        logger.debug(
            f"{symbol} | funding={funding_rate:.6f} ({apr*100:.1f}% APR) | "
            f"basis={basis*100:.3f}% | mark={mark_price:.2f}"
        )
        return snap

    def get(self, symbol: str) -> Optional[SymbolSnapshot]:
        return self.snapshots.get(symbol)

    def all_snapshots(self) -> List[SymbolSnapshot]:
        return list(self.snapshots.values())
