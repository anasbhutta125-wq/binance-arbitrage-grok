"""Order execution and position management."""

from __future__ import annotations
import asyncio
from typing import Optional, Any
from loguru import logger

from src.data.exchange_client import ExchangeClient
from src.data.market_data import MarketDataService
from src.strategy.funding_arb import (
    FundingArbStrategy, Signal, SignalAction, Side, OpenPosition
)
from src.risk.risk_manager import RiskManager
from src.utils.config import AppConfig
from src.utils.helpers import utc_now
from src.utils.persistence import PositionStore


class Executor:
    def __init__(
        self,
        client: ExchangeClient,
        market_data: MarketDataService,
        strategy: FundingArbStrategy,
        risk: RiskManager,
        config: AppConfig,
        store: Optional[PositionStore] = None,
    ):
        self.client = client
        self.market_data = market_data
        self.strategy = strategy
        self.risk = risk
        self.config = config
        self.store = store
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

        logger.info(
            f"{'[DRY] ' if self.dry_run else ''}ENTER {symbol} | "
            f"{signal.side.value} | size={size_usdt:.2f} USDT | {signal.reason}"
        )

        if self.dry_run:
            pos = OpenPosition(
                symbol=symbol,
                side=signal.side,
                entry_time=utc_now(),
                size_usdt=size_usdt,
                entry_funding_rate=snap.funding_rate,
                entry_basis=snap.basis,
                spot_qty=size_usdt / snap.spot_price if snap.spot_price else 0,
                perp_qty=size_usdt / snap.mark_price if snap.mark_price else 0,
            )
            self.strategy.register_position(pos)
            if self.store:
                await self.store.save_position(pos)
                await self.store.log_trade(
                    symbol, "ENTER", signal.side.value, size_usdt,
                    snap.funding_rate, snap.basis, signal.reason, dry_run=True
                )
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

            pos = OpenPosition(
                symbol=symbol,
                side=signal.side,
                entry_time=utc_now(),
                size_usdt=size_usdt,
                entry_funding_rate=snap.funding_rate,
                entry_basis=snap.basis,
                spot_qty=qty,
                perp_qty=qty,
            )
            self.strategy.register_position(pos)
            if self.store:
                await self.store.save_position(pos)
                await self.store.log_trade(
                    symbol, "ENTER", signal.side.value, size_usdt,
                    snap.funding_rate, snap.basis, signal.reason, dry_run=False
                )

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
            if self.store:
                await self.store.delete_position(symbol)
                await self.store.log_trade(
                    symbol, "EXIT", pos.side.value, pos.size_usdt,
                    reason=signal.reason, dry_run=True
                )
            return

        try:
            if pos.side == Side.LONG_SPOT_SHORT_PERP:
                await self._place_order(symbol, "buy", pos.perp_qty, account="future")
                spot_symbol = symbol.split(":")[0]
                await self._place_order(spot_symbol, "sell", pos.spot_qty, account="spot")

            self.strategy.remove_position(symbol)
            if self.store:
                await self.store.delete_position(symbol)
                await self.store.log_trade(
                    symbol, "EXIT", pos.side.value, pos.size_usdt,
                    reason=signal.reason, dry_run=False
                )
        except Exception as e:
            logger.exception(f"Exit failed for {symbol}: {e}")

    async def _rebalance(self, signal: Signal) -> None:
        symbol = signal.symbol
        pos = self.strategy.get_position(symbol)
        snap = signal.snapshot
        if not pos or not snap:
            logger.warning(f"Rebalance skipped – missing position or snapshot for {symbol}")
            return

        spot_notional = abs(pos.spot_qty * snap.spot_price)
        perp_notional = abs(pos.perp_qty * snap.mark_price)
        diff = spot_notional - perp_notional

        logger.info(
            f"{'[DRY] ' if self.dry_run else ''}REBALANCE {symbol} | "
            f"spot={spot_notional:.2f} perp={perp_notional:.2f} diff={diff:.2f} | {signal.reason}"
        )

        if abs(diff) < 5:
            return

        try:
            if pos.side == Side.LONG_SPOT_SHORT_PERP:
                qty = self.client.amount_to_precision(symbol, abs(diff) / snap.mark_price)
                if qty <= 0:
                    return
                if diff > 0:
                    if self.dry_run:
                        pos.perp_qty += qty
                    else:
                        await self._place_order(symbol, "sell", qty, account="future")
                        pos.perp_qty += qty
                else:
                    if self.dry_run:
                        pos.perp_qty -= qty
                    else:
                        await self._place_order(symbol, "buy", qty, account="future")
                        pos.perp_qty -= qty
            else:
                qty = self.client.amount_to_precision(symbol, abs(diff) / snap.mark_price)
                if qty <= 0:
                    return
                if diff > 0:
                    if self.dry_run:
                        pos.perp_qty -= qty
                    else:
                        await self._place_order(symbol, "sell", qty, account="future")
                        pos.perp_qty -= qty
                else:
                    if self.dry_run:
                        pos.perp_qty += qty
                    else:
                        await self._place_order(symbol, "buy", qty, account="future")
                        pos.perp_qty += qty

            pos.last_rebalance = utc_now()
            if self.store:
                await self.store.save_position(pos)
                await self.store.log_trade(
                    symbol, "REBALANCE", pos.side.value, abs(diff),
                    reason=signal.reason, dry_run=self.dry_run
                )
            logger.info(f"Rebalance done for {symbol} | new perp_qty={pos.perp_qty:.6f}")

        except Exception as e:
            logger.exception(f"Rebalance failed for {symbol}: {e}")

    async def _place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        account: str = "future",
        price: Optional[float] = None,
    ) -> dict:
        cfg = self.config.execution
        order_type = cfg.order_type
        params = {}
        if cfg.post_only and order_type == "limit":
            params["postOnly"] = True

        for attempt in range(1, cfg.retry_attempts + 1):
            try:
                order = await self.client.create_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=price,
                    order_type=order_type,
                    params=params,
                    account_type=account,
                )
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
