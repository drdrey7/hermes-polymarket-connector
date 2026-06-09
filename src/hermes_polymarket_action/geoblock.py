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


def check_geoblock(config: Optional[ActionConfig] = None) -> GeoblockResult:
    """
    Check geoblock using official Polymarket CLOB endpoint.
    
    Per Polymarket docs: https://docs.polymarket.com/api-reference/geoblock
    GET /geoblock returns {"country": "...", "blocked": true/false}
    
    If GEOBLOCK_CHECK=false: bypass (not recommended for production)
    If endpoint fails: block by default (fail-safe)
    If blocked=true: block execution
    """
    if config is None:
        config = ActionConfig()
    
    if not config.geoblock_check:
        return GeoblockResult(
            allowed=True, 
            country_code="BYPASS", 
            error="Geoblock check disabled (not recommended)"
        )
    
    try:
        resp = httpx.get(
            f"{config.clob_api_url}/geoblock",
            timeout=5.0,
            headers={"Accept": "application/json"}
        )
        resp.raise_for_status()
        data = resp.json()
        
        country = data.get("country", "unknown")
        blocked = data.get("blocked", True)  # default to blocked if missing
        
        if blocked:
            return GeoblockResult(
                allowed=False,
                country_code=country,
                error=f"Geoblock active: trading blocked in {country}"
            )
        
        return GeoblockResult(allowed=True, country_code=country)
        
    except httpx.TimeoutException:
        return GeoblockResult(
            allowed=False,
            error="Geoblock check timed out (blocked by default)"
        )
    except httpx.HTTPStatusError as e:
        return GeoblockResult(
            allowed=False,
            error=f"Geoblock check failed with HTTP {e.response.status_code} (blocked by default)"
        )
    except Exception as e:
        return GeoblockResult(
            allowed=False,
            error=f"Geoblock check failed: {type(e).__name__} (blocked by default)"
        )