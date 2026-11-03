"""Configuration loader with validation."""

from pathlib import Path
from typing import List, Optional
import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class ExchangeConfig(BaseModel):
    name: str = "binance"
    testnet: bool = True
    api_key: str
    api_secret: str


class StrategyConfig(BaseModel):
    symbols: List[str]
    min_funding_apr: float = 0.25
    max_basis_pct: float = 0.0015
    position_size_usdt: float = 100.0
    max_total_exposure_usdt: float = 500.0
    max_leverage: float = 2.0
    funding_lookback_hours: int = 8
    exit_funding_apr: float = 0.08
    rebalance_threshold_pct: float = 0.01
    min_hold_hours: float = 4.0
    round_trip_fee_pct: float = 0.0016
    expected_hold_hours: float = 24.0


class RiskConfig(BaseModel):
    max_daily_loss_usdt: float = 30.0
    max_drawdown_pct: float = 0.05
    liquidation_buffer_pct: float = 0.20
    max_open_positions: int = 3
    emergency_flatten_on_error: bool = True


class ExecutionConfig(BaseModel):
    order_type: str = "limit"
    limit_offset_bps: float = 2.0
    max_slippage_bps: float = 10.0
    post_only: bool = True
    retry_attempts: int = 3
    retry_delay_sec: float = 1.5


class DataConfig(BaseModel):
    funding_update_interval_sec: int = 30
    account_update_interval_sec: int = 15
    orderbook_depth: int = 10


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class MonitoringConfig(BaseModel):
    log_level: str = "INFO"
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    save_trades: bool = True
    db_path: str = "data/trades.db"
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8080


class RuntimeConfig(BaseModel):
    dry_run: bool = True
    check_interval_sec: int = 10
    heartbeat_interval_sec: int = 60


class AppConfig(BaseModel):
    exchange: ExchangeConfig
    strategy: StrategyConfig
    risk: RiskConfig
    execution: ExecutionConfig
    data: DataConfig
    monitoring: MonitoringConfig
    runtime: RuntimeConfig


def load_config(path: str | Path = "config/config.yaml") -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            "Copy config/config.example.yaml → config/config.yaml and fill values."
        )
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return AppConfig(**raw)
