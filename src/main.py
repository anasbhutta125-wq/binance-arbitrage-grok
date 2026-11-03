"""
Binance Funding Rate Arbitrage Bot
==================================
Main entry point.
"""

from __future__ import annotations
import asyncio
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger

from src.utils.config import load_config
from src.utils.logger import setup_logger
from src.data.exchange_client import ExchangeClient
from src.data.market_data import MarketDataService
from src.strategy.funding_arb import FundingArbStrategy
from src.risk.risk_manager import RiskManager
from src.execution.executor import Executor
from src.monitoring.alerts import AlertService


class FundingArbBot:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        setup_logger(self.config.monitoring.log_level)

        self.client = ExchangeClient(self.config)
        self.market_data = MarketDataService(self.client, self.config)
        self.strategy = FundingArbStrategy(self.config, self.market_data)
        self.risk = RiskManager(self.config)
        self.executor = Executor(self.client, self.market_data, self.strategy, self.risk, self.config)
        self.alerts = AlertService(self.config)

        self._running = False
        self._tasks = []
        self._dashboard_server = None

    async def start(self) -> None:
        logger.info("=" * 60)
        logger.info("Binance Funding Rate Arbitrage Bot starting...")
        logger.info(f"Dry-run mode : {self.config.runtime.dry_run}")
        logger.info(f"Testnet      : {self.config.exchange.testnet}")
        logger.info(f"Symbols      : {self.config.strategy.symbols}")
        logger.info("=" * 60)

        if not self.config.runtime.dry_run and not self.config.exchange.testnet:
            logger.warning("!!! LIVE TRADING ON MAINNET – BE CAREFUL !!!")
            await asyncio.sleep(3)

        await self.client.connect()
        await self.market_data.start()

        self._running = True
        await self.alerts.info("Funding Arb Bot started")

        await self._start_dashboard()

        self._tasks.append(asyncio.create_task(self._main_loop()))
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))

        await asyncio.gather(*self._tasks)

    async def _start_dashboard(self) -> None:
        try:
            import uvicorn
            from src.web.app import create_app

            app = create_app(self)
            host = getattr(self.config.monitoring, "dashboard_host", "0.0.0.0")
            port = getattr(self.config.monitoring, "dashboard_port", 8080)

            config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
            self._dashboard_server = uvicorn.Server(config)
            self._tasks.append(asyncio.create_task(self._dashboard_server.serve()))
            logger.info(f"Dashboard available at  http://{host}:{port}")
            await self.alerts.info(f"Dashboard: http://{host}:{port}")
        except Exception as e:
            logger.warning(f"Could not start dashboard: {e}")

    async def stop(self) -> None:
        logger.info("Shutting down...")
        self._running = False
        if self._dashboard_server:
            self._dashboard_server.should_exit = True
        for t in self._tasks:
            t.cancel()
        await self.market_data.stop()
        await self.client.close()
        await self.alerts.info("Funding Arb Bot stopped")
        logger.info("Shutdown complete")

    async def _main_loop(self) -> None:
        interval = self.config.runtime.check_interval_sec
        while self._running:
            try:
                signals = self.strategy.generate_signals()
                for sig in signals:
                    logger.info(f"Signal: {sig.symbol} | {sig.action.value} | {sig.reason}")
                    await self.executor.process_signal(sig)
            except Exception as e:
                logger.exception(f"Main loop error: {e}")
                await self.alerts.critical(f"Main loop error: {e}")
            await asyncio.sleep(interval)

    async def _heartbeat_loop(self) -> None:
        interval = self.config.runtime.heartbeat_interval_sec
        while self._running:
            open_pos = len(self.strategy.positions)
            snaps = self.market_data.all_snapshots()
            logger.info(f"Heartbeat | open positions={open_pos} | tracked symbols={len(snaps)} | dry_run={self.config.runtime.dry_run}")
            await asyncio.sleep(interval)


async def main():
    bot = FundingArbBot()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.stop()))
    try:
        await bot.start()
    except asyncio.CancelledError:
        pass
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
