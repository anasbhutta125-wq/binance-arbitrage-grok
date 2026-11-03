"""Binance exchange client wrapper using ccxt (async)."""

from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional
import ccxt.async_support as ccxt
from loguru import logger

from src.utils.config import AppConfig


class ExchangeClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.exchange: Optional[ccxt.binance] = None
        self._markets_loaded = False

    async def connect(self) -> None:
        opts = {
            "apiKey": self.config.exchange.api_key,
            "secret": self.config.exchange.api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
        if self.config.exchange.testnet:
            opts["sandbox"] = True
            opts["urls"] = {
                "api": {
                    "public": "https://testnet.binancefuture.com",
                    "private": "https://testnet.binancefuture.com",
                }
            }
            logger.warning("Running against Binance TESTNET")

        self.exchange = ccxt.binance(opts)
        await self.exchange.load_markets()
        self._markets_loaded = True
        logger.info("Exchange client connected & markets loaded")

    async def close(self) -> None:
        if self.exchange:
            await self.exchange.close()
            logger.info("Exchange client closed")

    async def fetch_funding_rate(self, symbol: str) -> Dict[str, Any]:
        return await self.exchange.fetch_funding_rate(symbol)

    async def fetch_funding_rate_history(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        return await self.exchange.fetch_funding_rate_history(symbol, limit=limit)

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        return await self.exchange.fetch_ticker(symbol)

    async def fetch_order_book(self, symbol: str, limit: int = 10) -> Dict[str, Any]:
        return await self.exchange.fetch_order_book(symbol, limit=limit)

    async def fetch_spot_ticker(self, symbol: str) -> Dict[str, Any]:
        original = self.exchange.options.get("defaultType")
        self.exchange.options["defaultType"] = "spot"
        try:
            return await self.exchange.fetch_ticker(symbol)
        finally:
            self.exchange.options["defaultType"] = original

    async def fetch_balance(self, account_type: str = "future") -> Dict[str, Any]:
        original = self.exchange.options.get("defaultType")
        self.exchange.options["defaultType"] = account_type
        try:
            return await self.exchange.fetch_balance()
        finally:
            self.exchange.options["defaultType"] = original

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        return await self.exchange.fetch_positions(symbols)

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        return await self.exchange.fetch_open_orders(symbol)

    async def create_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None, order_type: str = "limit", params: Optional[Dict] = None, account_type: str = "future") -> Dict[str, Any]:
        params = params or {}
        original = self.exchange.options.get("defaultType")
        self.exchange.options["defaultType"] = account_type
        try:
            if order_type == "market":
                return await self.exchange.create_order(symbol, "market", side, amount, params=params)
            else:
                return await self.exchange.create_order(symbol, "limit", side, amount, price, params=params)
        finally:
            self.exchange.options["defaultType"] = original

    async def cancel_order(self, order_id: str, symbol: str) -> Dict:
        return await self.exchange.cancel_order(order_id, symbol)

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            await self.exchange.set_leverage(leverage, symbol)
            logger.info(f"Leverage set to {leverage}x for {symbol}")
        except Exception as e:
            logger.warning(f"Could not set leverage for {symbol}: {e}")

    def market(self, symbol: str) -> Dict:
        if not self._markets_loaded:
            raise RuntimeError("Markets not loaded")
        return self.exchange.market(symbol)

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        return float(self.exchange.amount_to_precision(symbol, amount))

    def price_to_precision(self, symbol: str, price: float) -> float:
        return float(self.exchange.price_to_precision(symbol, price))
