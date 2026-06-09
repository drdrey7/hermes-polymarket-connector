# src/hermes_polymarket_action/models.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import hashlib


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PREVIEW = "PREVIEW"
    CONFIRMED = "CONFIRMED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderRequest(BaseModel):
    market_slug: str = Field(..., description="Human-readable market slug")
    token_id: str = Field(..., description="CLOB token ID for the outcome")
    outcome: str = Field(..., description="Outcome label (Yes/No)")
    side: Side
    size_usd: float = Field(..., gt=0, description="Order size in USD")
    price: float = Field(..., gt=0, lt=1, description="Limit price (0-1)")
    slippage_bps: int = Field(default=100, ge=0, le=10000, description="Max slippage in basis points")
    expire_seconds: int = Field(default=300, ge=30, description="Order expiry seconds")

    @field_validator("token_id")
    @classmethod
    def validate_token_id(cls, v: str) -> str:
        if not v.startswith("0x") or len(v) != 66:
            raise ValueError("Token ID must be 0x + 64 hex chars")
        return v


@dataclass
class OrderPreview:
    request: OrderRequest
    current_price: float
    fee_bps: int
    estimated_fee_usd: float
    max_slippage_usd: float
    worst_case_price: float
    notional_usd: float
    confirmation_code: str

    @classmethod
    def from_request(cls, req: OrderRequest, current_price: float, fee_bps: int = 10) -> OrderPreview:
        notional = req.size_usd
        est_fee = notional * fee_bps / 10000
        max_slippage = notional * req.slippage_bps / 10000
        if req.side == Side.BUY:
            worst = current_price * (1 - req.slippage_bps / 10000)
        else:
            worst = current_price * (1 + req.slippage_bps / 10000)
        # Generate confirmation code: SHA256(request + timestamp)[:8].upper()
        raw = f"{req.model_dump_json()}{datetime.utcnow().isoformat()}".encode()
        code = hashlib.sha256(raw).hexdigest()[:8].upper()
        return cls(
            request=req,
            current_price=current_price,
            fee_bps=fee_bps,
            estimated_fee_usd=round(est_fee, 4),
            max_slippage_usd=round(max_slippage, 4),
            worst_case_price=round(worst, 6),
            notional_usd=notional,
            confirmation_code=code,
        )


class ConfirmationRequest(BaseModel):
    confirmation_code: str
    user_approval: bool = True


class OrderResult(BaseModel):
    order_id: Optional[str] = None
    status: OrderStatus
    tx_hash: Optional[str] = None
    filled_size_usd: float = 0.0
    avg_fill_price: Optional[float] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)