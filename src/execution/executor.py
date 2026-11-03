"""Order execution and position management."""

from __future__ import annotations
import asyncio
from typing import Optional
from loguru import logger

from src.data.exchange_client import ExchangeClient
from src.data.market_data import MarketDataService
from src.strategy.funding_arb import (
    FundingArbStrategy, Signal, SignalAction, Side, OpenPosition
)
from src.risk.risk_manager import RiskManager
from src.utils.config import AppConfig
from src.utils.helpers import utc_now


class Executor:
    def __init__(self, client: ExchangeClient, market_data: MarketDataService, strategy: FundingArbStrategy, risk: RiskManager, config: AppConfig):
        self.client = client
        self.market_data = market_data
        self.strategy = strategy
        self.risk = risk
        self.config = config
        self.dry_run = config.runtime.dry_run

    async def process_signal(self, signal: Signal) -> None:
        can_trade, reason = self.risk.check_can_trade()
        if not can_trade and signal.action in (SignalAction.ENTER, SignalAction.REBALANCE):
            logger.warning(f"Blocked by risk: {reason}")
            return

        if signal.action == SignalAction.ENTER:
            await self._enter(signal)
        elif signal.action == SignalAction.EXIT:
            await self._exit(signal)
        elif signal.action == SignalAction.REBALANCE:
            await self._rebalance(signal)

    async def _enter(self, signal: Signal) -> None:
        symbol = signal.symbol
        size_usdt = signal.size_usdt
        snap = signal.snapshot
        if not snap:
            logger.error("No snapshot for entry")
            return

        logger.info(f"{'[DRY] ' if self.dry_run else ''}ENTER {symbol} | {signal.side.value} | size={size_usdt:.2f} USDT | {signal.reason}")

        if self.dry_run:
            pos = OpenPosition(symbol=symbol, side=signal.side, entry_time=utc_now(), size_usdt=size_usdt, entry_funding_rate=snap.funding_rate, entry_basis=snap.basis, spot_qty=size_usdt / snap.spot_price, perp_qty=size_usdt / snap.mark_price)
            self.strategy.register_position(pos)
            return

        try:
            await self.client.set_leverage(symbol, int(self.config.strategy.max_leverage))
            qty = self.client.amount_to_precision(symbol, size_usdt / snap.mark_price)

            if signal.side == Side.LONG_SPOT_SHORT_PERP:
                spot_symbol = symbol.split(":")[0]
                await self._place_order(spot_symbol, "buy", qty, account="spot")
                await self._place_order(symbol, "sell", qty, account="future")
            else:
                logger.warning("Negative funding path requires margin short – implement carefully")
                return

            pos = OpenPosition(symbol=symbol, side=signal.side, entry_time=utc_now(), size_usdt=size_usdt, entry_funding_rate=snap.funding_rate, entry_basis=snap.basis, spot_qty=qty, perp_qty=qty)
            self.strategy.register_position(pos)
        except Exception as e:
            logger.exception(f"Entry failed for {symbol}: {e}")
            if self.config.risk.emergency_flatten_on_error:
                await self._emergency_flatten(symbol)

    async def _exit(self, signal: Signal) -> None:
        symbol = signal.symbol
        pos = self.strategy.get_position(symbol)
        if not pos:
            return

        logger.info(f"{'[DRY] ' if self.dry_run else ''}EXIT {symbol} | {signal.reason}")

        if self.dry_run:
            self.strategy.remove_position(symbol)
            return

        try:
            if pos.side == Side.LONG_SPOT_SHORT_PERP:
                await self._place_order(symbol, "buy", pos.perp_qty, account="future")
                spot_symbol = symbol.split(":")[0]
                await self._place_order(spot_symbol, "sell", pos.spot_qty, account="spot")
            self.strategy.remove_position(symbol)
        except Exception as e:
            logger.exception(f"Exit failed for {symbol}: {e}")

    async def _rebalance(self, signal: Signal) -> None:
        logger.info(f"Rebalance requested for {signal.symbol}")

    async def _place_order(self, symbol: str, side: str, amount: float, account: str = "future", price: Optional[float] = None) -> dict:
        cfg = self.config.execution
        params = {}
        if cfg.post_only and cfg.order_type == "limit":
            params["postOnly"] = True
        for attempt in range(1, cfg.retry_attempts + 1):
            try:
                order = await self.client.create_order(symbol=symbol, side=side, amount=amount, price=price, order_type=cfg.order_type, params=params, account_type=account)
                logger.info(f"Order placed: {side} {amount} {symbol} ({account})")
                return order
            except Exception as e:
                logger.warning(f"Order attempt {attempt} failed: {e}")
                if attempt == cfg.retry_attempts:
                    raise
                await asyncio.sleep(cfg.retry_delay_sec)

    async def _emergency_flatten(self, symbol: str) -> None:
        logger.critical(f"EMERGENCY FLATTEN {symbol}")
        try:
            orders = await self.client.fetch_open_orders(symbol)
            for o in orders:
                await self.client.cancel_order(o["id"], symbol)
        except Exception as e:
            logger.error(f"Emergency cancel failed: {e}")
