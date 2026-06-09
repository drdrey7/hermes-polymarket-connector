# src/hermes_polymarket_action/execution.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .config import ActionConfig
from .models import OrderRequest, OrderResult, OrderStatus, Side
from .confirmation import verify_confirmation, mark_executing, mark_result
from .validation import validate_market_token
from .risk import RiskEngine
from .geoblock import check_geoblock
from datetime import datetime

# Import py-clob-client types
try:
    from py_clob_client import ClobClient  # type: ignore[import-not-found]
    from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds  # type: ignore[import-not-found]
except ImportError:
    ClobClient = None
    OrderArgs = None
    OrderType = None
    ApiCreds = None


@dataclass
class ExecutionPlan:
    """Plan built after all safety checks pass."""
    allowed: bool
    reason: str = ""
    order_request: Optional[OrderRequest] = None
    confirmation_code: Optional[str] = None
    geoblock_result: Optional[object] = None
    risk_result: Optional[object] = None


class ExecutionEngine:
    """Safe execution engine for Polymarket CLOB using py_clob_client."""

    def __init__(self, config: Optional[ActionConfig] = None, risk_engine: Optional[RiskEngine] = None):
        self.config = config or ActionConfig()
        self.risk_engine = risk_engine or RiskEngine(self.config)
        self._client = None

    @property
    def client(self) -> ClobClient:
        """Lazy-initialized ClobClient."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> ClobClient:
        """Build authenticated ClobClient from local credentials."""
        if ClobClient is None:
            raise RuntimeError("py_clob_client not installed. Run: pip install py-clob-client")

        if not self.config.has_credentials():
            raise RuntimeError("Missing credentials: POLYMARKET_PRIVATE_KEY and POLYMARKET_FUNDER_ADDRESS required")

        try:
            client = ClobClient(
                host=self.config.clob_api_url,
                chain_id=self.config.chain_id,
                key=self.config.private_key,
                signature_type=self.config.signature_type,
                funder=self.config.funder_address,
            )
            # Derive or create API key for L2 auth
            creds = client.create_or_derive_api_creds()
            client.set_api_creds(creds)
            return client
        except Exception as e:
            raise RuntimeError(f"Failed to initialize ClobClient: {type(e).__name__}: {self._redact(str(e))}")

    def _redact(self, text: str) -> str:
        """Redact sensitive data from logs/exceptions."""
        import re
        # Redact private keys (0x + 64 hex)
        text = re.sub(r'0x[a-fA-F0-9]{64}', '0x***REDACTED***', text)
        # Redact API keys/secrets/passphrases
        text = re.sub(r'(api[_-]?key|secret|passphrase)[\s:=]+[^\s,}]+', r'\1=***REDACTED***', text, flags=re.IGNORECASE)
        # Redact Authorization headers
        text = re.sub(r'Authorization:\s*Bearer\s+[^\s,}]+', 'Authorization: Bearer ***REDACTED***', text, flags=re.IGNORECASE)
        # Redact POLY_* headers
        text = re.sub(r'POLY_(ADDRESS|SIGNATURE|TIMESTAMP|NONCE|API_KEY|PASSPHRASE)[\s:=]+[^\s,}]+', r'POLY_\1=***REDACTED***', text, flags=re.IGNORECASE)
        return text

    def validate_market(self, req: OrderRequest) -> tuple[bool, str]:
        """Validate market/token/outcome."""
        result = validate_market_token(req.market_slug, req.token_id, req.outcome)
        if not result.valid:
            return False, result.error or "Market validation failed"
        return True, "Market valid"

    def check_risk(self, req: OrderRequest) -> tuple[bool, str]:
        """Check risk limits."""
        risk_result = self.risk_engine.check(req)
        if not risk_result.allowed:
            return False, risk_result.error or "Risk limit exceeded"
        for _ in risk_result.warnings:
            pass  # warnings are logged separately
        return True, "Risk limits OK"

    def check_open_orders(self) -> tuple[bool, str]:
        """Check open orders count against limit."""
        if not self.config.is_live_enabled():
            return True, "Live trading disabled, skipping open orders check"
        try:
            orders = self.client.get_orders()
            count = len(orders) if orders else 0
            if count >= self.config.max_open_orders:
                return False, f"Open orders ({count}) >= limit ({self.config.max_open_orders})"
            return True, f"Open orders: {count}/{self.config.max_open_orders}"
        except Exception as e:
            return False, f"Open orders check failed: {type(e).__name__}"

    def build_execution_plan(
        self,
        confirmation_code: str,
        user_approval: bool,
    ) -> ExecutionPlan:
        """Run all safety gates and build execution plan."""

        # Gate: live trading enabled
        if not self.config.is_live_enabled():
            return ExecutionPlan(
                allowed=False,
                reason="Live trading not enabled. Set LIVE_TRADING=true and provide credentials."
            )

        # Gate: confirmation code + approval
        confirm_result = verify_confirmation(confirmation_code, user_approval)
        if not confirm_result.valid:
            return ExecutionPlan(
                allowed=False,
                reason=f"Confirmation failed: {confirm_result.error}"
            )

        entry = confirm_result.entry
        if entry is None:
            return ExecutionPlan(allowed=False, reason="No audit entry found")

        # Re-create order request from audit entry
        req = OrderRequest(
            market_slug=entry.market_slug,
            token_id=entry.token_id,
            outcome=entry.outcome,
            side=Side(entry.side),
            size_usd=entry.size_usd,
            price=entry.price,
        )

        # Gate: market validation
        valid, reason = self.validate_market(req)
        if not valid:
            mark_result(confirmation_code, "rejected", error=reason)
            return ExecutionPlan(allowed=False, reason=f"Market validation: {reason}")

        # Gate: geoblock (single source of truth)
        geo_result = check_geoblock(self.config)
        if not geo_result.allowed:
            mark_result(confirmation_code, "rejected", error=geo_result.error)
            return ExecutionPlan(allowed=False, reason=f"Geoblock: {geo_result.error}")

        # Gate: risk limits
        risk_allowed, risk_reason = self.check_risk(req)
        if not risk_allowed:
            mark_result(confirmation_code, "rejected", error=risk_reason)
            return ExecutionPlan(allowed=False, reason=f"Risk check: {risk_reason}")

        # Gate: open orders limit
        orders_allowed, orders_reason = self.check_open_orders()
        if not orders_allowed:
            mark_result(confirmation_code, "rejected", error=orders_reason)
            return ExecutionPlan(allowed=False, reason=f"Open orders: {orders_reason}")

        # All gates passed
        mark_executing(confirmation_code, "order-submitting")

        return ExecutionPlan(
            allowed=True,
            reason="All safety gates passed",
            order_request=req,
            confirmation_code=confirmation_code,
        )

    def execute_order(self, plan: ExecutionPlan) -> OrderResult:
        """Execute the order via ClobClient."""
        if not plan.allowed or plan.order_request is None:
            return OrderResult(
                status=OrderStatus.REJECTED,
                error=plan.reason,
                timestamp=datetime.utcnow()
            )

        req = plan.order_request
        confirmation_code = plan.confirmation_code

        try:
            if OrderArgs is None or OrderType is None:
                raise RuntimeError("py_clob_client types not available")

            # Convert USD size to shares (CLOB expects shares, not USD)
            shares = req.size_usd / req.price if req.price > 0 else 0

            # Prepare order args (no order_type - GTC is default in post_order)
            order_args = OrderArgs(
                token_id=req.token_id,
                price=req.price,
                size=shares,  # SHARES not USD
                side=req.side.value.lower(),  # "buy" or "sell"
                fee_rate_bps=10,  # default, could be configurable
                nonce=0,
            )

            # Create and post order in one call
            resp = self.client.create_and_post_order(order_args)
            order_id = resp.get("order_id") if isinstance(resp, dict) else getattr(resp, "order_id", None)
            tx_hash = None
            if isinstance(resp, dict):
                tx_hash = resp.get("tx_hash") or resp.get("transaction_hash")

            # Update audit
            filled_usd = req.size_usd  # assume full fill for now
            assert confirmation_code is not None
            mark_result(
                confirmation_code,
                "filled" if order_id else "submitted",
                tx_hash=tx_hash,
                filled_size_usd=filled_usd,
                avg_fill_price=req.price,
            )

            # Record spend for daily limit tracking
            self.risk_engine.record_fill(filled_usd)

            return OrderResult(
                order_id=order_id,
                status=OrderStatus.FILLED if order_id else OrderStatus.SUBMITTED,
                tx_hash=tx_hash,
                filled_size_usd=filled_usd,
                avg_fill_price=req.price,
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            redacted = self._redact(str(e))
            assert confirmation_code is not None
            mark_result(confirmation_code, "rejected", error=redacted)
            return OrderResult(
                status=OrderStatus.REJECTED,
                error=redacted,
                timestamp=datetime.utcnow()
            )

    def cancel_order(self, order_id: str, confirmation_code: Optional[str] = None) -> OrderResult:
        """Cancel an open order."""
        if not self.config.is_live_enabled():
            return OrderResult(status=OrderStatus.REJECTED, error="Live trading disabled")

        try:
            resp = self.client.cancel(order_id)
            success = resp.get("success", False) if isinstance(resp, dict) else bool(resp)

            status = OrderStatus.CANCELLED if success else OrderStatus.REJECTED
            error = None if success else f"Cancel failed: {self._redact(str(resp))}"

            # Update audit if confirmation code provided
            if confirmation_code:
                mark_result(
                    confirmation_code,
                    "cancelled" if success else "cancel_failed",
                    error=error,
                )

            return OrderResult(
                order_id=order_id,
                status=status,
                error=error,
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            redacted = self._redact(str(e))
            if confirmation_code:
                mark_result(confirmation_code, "cancel_failed", error=redacted)
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                error=redacted,
                timestamp=datetime.utcnow()
            )

    def close_position(self, token_id: str, size_usd: float, confirmation_code: str, user_approval: bool = True) -> OrderResult:
        """
        Close (reduce) a position by placing opposite order.
        REQUIRES confirmation code and runs all safety gates.
        """
        if not self.config.is_live_enabled():
            return OrderResult(status=OrderStatus.REJECTED, error="Live trading disabled")

        if not user_approval:
            return OrderResult(status=OrderStatus.REJECTED, error="User approval required for close_position")

        # Build execution plan with gates (reuses all validation)
        plan = self.build_execution_plan(confirmation_code, user_approval)
        if not plan.allowed:
            return OrderResult(status=OrderStatus.REJECTED, error=plan.reason)

        try:
            # Get current position via get_orders + balance allowance (best effort)
            # Note: py_clob_client doesn't have direct get_positions, so we use best available
            orders = self.client.get_orders()
            if not orders:
                return OrderResult(
                    status=OrderStatus.REJECTED,
                    error="No open orders found to determine position",
                    timestamp=datetime.utcnow()
                )

            # Find relevant order for this token
            position_order = None
            for o in orders:
                if o.get("token_id") == token_id or o.get("asset_id") == token_id:
                    position_order = o
                    break

            if not position_order:
                return OrderResult(
                    status=OrderStatus.REJECTED,
                    error=f"No open order found for token {token_id}",
                    timestamp=datetime.utcnow()
                )

            # Determine side to close (opposite of current)
            current_side = position_order.get("side", "").lower()
            close_side = Side.SELL if current_side == "buy" else Side.BUY

            # Use current price from order or fallback
            current_price = float(position_order.get("price", 0.5))
            if current_price <= 0:
                current_price = 0.5

            # Cap close size at requested
            close_size_usd = min(size_usd, float(position_order.get("size", 0)) * current_price)

            # Create close order request
            close_req = OrderRequest(
                market_slug=position_order.get("market", "unknown"),
                token_id=token_id,
                outcome=position_order.get("outcome", "unknown"),
                side=close_side,
                size_usd=close_size_usd,
                price=current_price,
            )

            # Replace plan's order request and execute
            plan.order_request = close_req
            return self.execute_order(plan)

        except Exception as e:
            redacted = self._redact(str(e))
            return OrderResult(
                status=OrderStatus.REJECTED,
                error=redacted,
                timestamp=datetime.utcnow()
            )

    def get_status(self) -> dict:
        """Get account/CLOB status."""
        if not self.config.has_credentials():
            return {"ready": False, "reason": "No credentials"}

        try:
            # Test connection
            orders = self.client.get_orders()
            # No get_positions in this client version

            return {
                "ready": True,
                "funder_address": self.config.funder_address[:10] + "..." if self.config.funder_address else None,
                "open_orders": len(orders) if orders else 0,
                "positions_note": "get_positions not available in py_clob_client 0.34.x",
                "paper_trading": not self.config.live_trading,
            }
        except Exception as e:
            return {
                "ready": False,
                "reason": f"Status check failed: {type(e).__name__}",
            }

