"""
State persistence for open positions.
Saves to SQLite so the bot can recover after restart.
"""

from __future__ import annotations
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from loguru import logger

from src.strategy.funding_arb import OpenPosition, Side
from src.utils.helpers import utc_now


class PositionStore:
    def __init__(self, db_path: str = "data/trades.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS open_positions (
                symbol TEXT PRIMARY KEY,
                side TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                size_usdt REAL NOT NULL,
                entry_funding_rate REAL NOT NULL,
                entry_basis REAL NOT NULL,
                spot_qty REAL NOT NULL,
                perp_qty REAL NOT NULL,
                realized_funding REAL DEFAULT 0,
                last_rebalance TEXT,
                extra_json TEXT
            )
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                side TEXT,
                size_usdt REAL,
                funding_rate REAL,
                basis REAL,
                reason TEXT,
                dry_run INTEGER DEFAULT 1
            )
        """)
        await self._conn.commit()
        logger.info(f"PositionStore connected → {self.db_path}")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def save_position(self, pos: OpenPosition) -> None:
        if not self._conn:
            return
        await self._conn.execute(
            """INSERT OR REPLACE INTO open_positions
            (symbol, side, entry_time, size_usdt, entry_funding_rate, entry_basis,
             spot_qty, perp_qty, realized_funding, last_rebalance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pos.symbol, pos.side.value, pos.entry_time.isoformat(), pos.size_usdt,
             pos.entry_funding_rate, pos.entry_basis, pos.spot_qty, pos.perp_qty,
             pos.realized_funding,
             pos.last_rebalance.isoformat() if pos.last_rebalance else None),
        )
        await self._conn.commit()

    async def delete_position(self, symbol: str) -> None:
        if not self._conn:
            return
        await self._conn.execute("DELETE FROM open_positions WHERE symbol = ?", (symbol,))
        await self._conn.commit()

    async def load_all_positions(self) -> Dict[str, OpenPosition]:
        if not self._conn:
            return {}
        cursor = await self._conn.execute("SELECT * FROM open_positions")
        rows = await cursor.fetchall()
        positions: Dict[str, OpenPosition] = {}
        for row in rows:
            try:
                side = Side(row["side"])
                entry_time = datetime.fromisoformat(row["entry_time"])
                last_rebalance = (
                    datetime.fromisoformat(row["last_rebalance"])
                    if row["last_rebalance"] else entry_time
                )
                pos = OpenPosition(
                    symbol=row["symbol"], side=side, entry_time=entry_time,
                    size_usdt=row["size_usdt"], entry_funding_rate=row["entry_funding_rate"],
                    entry_basis=row["entry_basis"], spot_qty=row["spot_qty"],
                    perp_qty=row["perp_qty"], realized_funding=row["realized_funding"] or 0.0,
                    last_rebalance=last_rebalance,
                )
                positions[pos.symbol] = pos
            except Exception as e:
                logger.error(f"Failed to load position {row['symbol']}: {e}")
        logger.info(f"Loaded {len(positions)} positions from store")
        return positions

    async def log_trade(self, symbol: str, action: str, side: Optional[str] = None,
                        size_usdt: float = 0.0, funding_rate: float = 0.0,
                        basis: float = 0.0, reason: str = "", dry_run: bool = True) -> None:
        if not self._conn:
            return
        await self._conn.execute(
            """INSERT INTO trade_log
            (ts, symbol, action, side, size_usdt, funding_rate, basis, reason, dry_run)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (utc_now().isoformat(), symbol, action, side, size_usdt,
             funding_rate, basis, reason, 1 if dry_run else 0),
        )
        await self._conn.commit()
