"""
Simple FastAPI dashboard for the Funding Rate Arbitrage Bot.
Serves a live status page + JSON API.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

_bot_ref = None


def create_app(bot) -> FastAPI:
    global _bot_ref
    _bot_ref = bot

    app = FastAPI(title="Funding Arb Dashboard", description="Live monitoring for Binance Funding Rate Arbitrage Bot", version="1.0.0")

    templates_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    templates = Jinja2Templates(directory=str(templates_dir))

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse("dashboard.html", {"request": request})

    @app.get("/api/status")
    async def api_status() -> Dict[str, Any]:
        if _bot_ref is None:
            return {"error": "Bot not attached"}
        cfg = _bot_ref.config
        return {
            "running": _bot_ref._running,
            "dry_run": cfg.runtime.dry_run,
            "testnet": cfg.exchange.testnet,
            "symbols": cfg.strategy.symbols,
            "min_funding_apr": cfg.strategy.min_funding_apr,
            "position_size_usdt": cfg.strategy.position_size_usdt,
            "max_total_exposure_usdt": cfg.strategy.max_total_exposure_usdt,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/market")
    async def api_market() -> List[Dict[str, Any]]:
        if _bot_ref is None:
            return []
        snaps = _bot_ref.market_data.all_snapshots()
        result = []
        for s in snaps:
            result.append({
                "symbol": s.symbol,
                "funding_rate": round(s.funding_rate, 8),
                "projected_apr": round(s.projected_apr * 100, 2),
                "mark_price": round(s.mark_price, 4),
                "spot_price": round(s.spot_price, 4),
                "basis_pct": round(s.basis * 100, 4),
                "next_funding_time": s.next_funding_time.isoformat() if s.next_funding_time else None,
                "timestamp": s.timestamp.isoformat(),
            })
        return result

    @app.get("/api/positions")
    async def api_positions() -> List[Dict[str, Any]]:
        if _bot_ref is None:
            return []
        positions = []
        for sym, pos in _bot_ref.strategy.positions.items():
            hold_hours = (datetime.now(timezone.utc) - pos.entry_time).total_seconds() / 3600
            positions.append({
                "symbol": pos.symbol,
                "side": pos.side.value,
                "size_usdt": round(pos.size_usdt, 2),
                "entry_funding_rate": round(pos.entry_funding_rate, 8),
                "entry_basis": round(pos.entry_basis * 100, 4),
                "spot_qty": round(pos.spot_qty, 6),
                "perp_qty": round(pos.perp_qty, 6),
                "realized_funding": round(pos.realized_funding, 4),
                "entry_time": pos.entry_time.isoformat(),
                "hold_hours": round(hold_hours, 2),
            })
        return positions

    @app.get("/api/risk")
    async def api_risk() -> Dict[str, Any]:
        if _bot_ref is None:
            return {}
        state = _bot_ref.risk.state
        can_trade, reason = _bot_ref.risk.check_can_trade()
        return {
            "halted": state.halted,
            "halt_reason": state.halt_reason,
            "can_trade": can_trade,
            "reason": reason,
            "daily_pnl": round(state.daily_pnl, 2),
            "current_equity": round(state.current_equity, 2),
            "peak_equity": round(state.peak_equity, 2),
            "open_positions": len(_bot_ref.strategy.positions),
            "max_open_positions": _bot_ref.config.risk.max_open_positions,
        }

    @app.get("/api/summary")
    async def api_summary() -> Dict[str, Any]:
        status = await api_status()
        market = await api_market()
        positions = await api_positions()
        risk = await api_risk()
        return {"status": status, "market": market, "positions": positions, "risk": risk}

    logger.info("Dashboard FastAPI app created")
    return app
