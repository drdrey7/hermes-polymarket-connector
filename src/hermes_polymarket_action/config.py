# src/hermes_polymarket_action/config.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ActionConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required for live trading
    private_key: Optional[str] = Field(default=None, alias="POLYMARKET_PRIVATE_KEY")
    funder: Optional[str] = Field(default=None, alias="POLYMARKET_FUNDER")
    proxy_wallet: Optional[str] = Field(default=None, alias="POLYMARKET_PROXY_WALLET")

    # RPC / API
    rpc_url: str = Field(default="https://polygon-rpc.com", alias="POLYMARKET_RPC_URL")
    clob_api_url: str = Field(default="https://clob.polymarket.com", alias="POLYMARKET_CLOB_API_URL")

    # Live trading gates (ALL must be true for real execution)
    live_trading: bool = Field(default=False, alias="LIVE_TRADING")
    require_confirmation: bool = Field(default=True, alias="REQUIRE_CONFIRMATION")

    # Risk limits
    max_order_usd: float = Field(default=100.0, alias="MAX_ORDER_USD")
    max_daily_usd: float = Field(default=500.0, alias="MAX_DAILY_USD")
    max_slippage_bps: int = Field(default=100, alias="MAX_SLIPPAGE_BPS")
    max_position_usd: float = Field(default=1000.0, alias="MAX_POSITION_USD")

    # Geoblock
    geoblock_check: bool = Field(default=True, alias="GEOBLOCK_CHECK")
    allowed_countries: list[str] = Field(default=["PT", "US", "GB", "DE", "FR"], alias="ALLOWED_COUNTRIES")

    # Audit
    audit_log_path: Path = Field(default=Path("~/.hermes/polymarket-action/audit.log").expanduser(), alias="AUDIT_LOG_PATH")

    @field_validator("private_key")
    @classmethod
    def validate_private_key(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("0x"):
            raise ValueError("Private key must start with 0x")
        if v is not None and len(v) != 66:
            raise ValueError("Private key must be 66 chars (0x + 64 hex)")
        return v

    @field_validator("funder", "proxy_wallet")
    @classmethod
    def validate_address(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.startswith("0x") and len(v) == 42):
            raise ValueError("Address must be 0x + 40 hex chars")
        return v

    def is_live_enabled(self) -> bool:
        return (
            self.live_trading
            and self.require_confirmation
            and self.private_key is not None
            and self.funder is not None
        )