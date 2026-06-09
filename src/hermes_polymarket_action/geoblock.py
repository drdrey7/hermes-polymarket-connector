# src/hermes_polymarket_action/geoblock.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import httpx
from .config import ActionConfig


@dataclass
class GeoblockResult:
    allowed: bool
    country_code: Optional[str] = None
    error: Optional[str] = None


def get_country_code() -> Optional[str]:
    """Get country code from IP geolocation (ipapi.co)."""
    try:
        resp = httpx.get("https://ipapi.co/json/", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        country = data.get("country_code")
        return str(country) if country is not None else None
    except Exception:
        return None


def check_geoblock(config: Optional[ActionConfig] = None) -> GeoblockResult:
    """Check if current location is allowed per config."""
    if config is None:
        config = ActionConfig()
    if not config.geoblock_check:
        return GeoblockResult(allowed=True, country_code="BYPASS", error="Geoblock check disabled")

    country = get_country_code()
    if country is None:
        return GeoblockResult(allowed=False, error="Could not determine location")

    if country in config.allowed_countries:
        return GeoblockResult(allowed=True, country_code=country)

    return GeoblockResult(
        allowed=False,
        country_code=country,
        error=f"Country {country} not in allowed list: {config.allowed_countries}",
    )