# src/hermes_polymarket_action/validation.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import asyncio


@dataclass
class ValidationResult:
    valid: bool
    market_slug: Optional[str] = None
    token_id: Optional[str] = None
    outcome: Optional[str] = None
    error: Optional[str] = None


async def get_market_for_token(token_id: str) -> Optional[dict]:
    """
    Minimal market lookup — delegates to existing Hermes Polymarket skill.
    This is the ONLY read operation; no full market search duplication.
    """
    # TODO: integrate with actual Hermes skill when available
    # For now, returns None (caller must handle)
    return None


def validate_market_token(
    market_slug: str,
    token_id: str,
    outcome: str,
) -> ValidationResult:
    """
    Validate that token_id belongs to market_slug and matches outcome.
    Uses existing Hermes Polymarket skill for read-only lookup.
    
    FAIL CLOSED: If skill unavailable, validation fails.
    This prevents trading on invalid/unknown markets.
    """
    # Basic format checks
    if not token_id.startswith("0x") or len(token_id) != 66:
        return ValidationResult(valid=False, error="Invalid token_id format")

    # Delegate to skill for authoritative check (async -> sync bridge)
    market_data = asyncio.run(get_market_for_token(token_id))

    if market_data is None:
        # FAIL CLOSED: No skill integration → cannot validate
        return ValidationResult(
            valid=False,
            error="Market validation unavailable: Hermes Polymarket skill not integrated. Cannot verify token/market/outcome."
        )

    if market_data.get("slug") != market_slug:
        return ValidationResult(valid=False, error=f"Token belongs to market '{market_data.get('slug')}', not '{market_slug}'")

    token_match = False
    for token in market_data.get("tokens", []):
        if token.get("token_id") == token_id and token.get("outcome") == outcome:
            token_match = True
            break

    if not token_match:
        return ValidationResult(valid=False, error=f"No matching token for outcome '{outcome}' in market")

    return ValidationResult(
        valid=True,
        market_slug=market_data["slug"],
        token_id=token_id,
        outcome=outcome,
    )