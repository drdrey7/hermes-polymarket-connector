# src/hermes_polymarket_action/execution.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .config import ActionConfig
from .models import OrderRequest, OrderResult, OrderStatus, Side
from .confirmation import verify_confirmation, mark_executing, mark_result
from .validation import validate_market_token
from .risk import RiskEngine
from datetime import datetime

# Import py-clob-client types at module level to avoid undefined name errors
try:
    from py_clob_client_v2.clob.types import OrderArgs, OrderType  # type: ignore[import-not-found]
except ImportError:
    OrderArgs = None
    OrderType = None


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
    """Safe execution engine for Polymarket CLOB."""
    
    def __init__(self, config: Optional[ActionConfig] = None, risk_engine: Optional[RiskEngine] = None):
        self.config = config or ActionConfig()
        self.risk_engine = risk_engine or RiskEngine(self.config)
        self._client = None
    
    @property
    def client(self):
        """Lazy-initialized ClobClient."""
        if self._client is None:
            self._client = self._build_client()
        return self._client
    
    def _build_client(self):
        """Build authenticated ClobClient from local credentials."""
        from py_clob_client_v2 import ClobClient  # type: ignore[import-not-found]
        
        if not self.config.has_credentials():
            raise RuntimeError("Missing credentials: POLYMARKET_PRIVATE_KEY and POLYMARKET_FUNDER_ADDRESS required")
        
        try:
            client = ClobClient(
                host=self.config.clob_api_url,
                chain_id=self.config.chain_id,
                key=self.config.private_key,
            )
            # Derive or create API key for L2 auth
            creds = client.create_or_derive_api_key()
            client.set_creds(creds)
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

    def check_geoblock(self) -> tuple[bool, str]:
        """Check geoblock using official Polymarket endpoint."""
        if not self.config.geoblock_check:
            return True, "Geoblock check disabled (not recommended)"
        
        try:
            import httpx
            resp = httpx.get(
                "https://clob.polymarket.com/geoblock",
                timeout=5.0,
                headers={"Accept": "application/json"}
            )
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("blocked") is True:
                country = data.get("country", "unknown")
                return False, f"Geoblock active: trading blocked in {country}"
            
            return True, f"Geoblock clear (country: {data.get('country', 'unknown')})"
        except Exception as e:
            return False, f"Geoblock check failed (blocked by default): {type(e).__name__}"
    
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
        for w in risk_result.warnings:
            pass  # warnings are logged separately
        return True, "Risk limits OK"
    
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
        
        # Gate: geoblock
        geo_allowed, geo_reason = self.check_geoblock()
        if not geo_allowed:
            mark_result(confirmation_code, "rejected", error=geo_reason)
            return ExecutionPlan(allowed=False, reason=f"Geoblock: {geo_reason}")
        
        # Gate: risk limits
        risk_allowed, risk_reason = self.check_risk(req)
        if not risk_allowed:
            mark_result(confirmation_code, "rejected", error=risk_reason)
            return ExecutionPlan(allowed=False, reason=f"Risk check: {risk_reason}")
        
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
            # Place order via py-clob-client
            # Note: The CLOB client expects signed order - we need to construct the order payload
            from py_clob_client_v2.clob.types import OrderArgs, OrderType
            
            # Prepare order args
            order_args = OrderArgs(
                token_id=req.token_id,
                price=req.price,
                size=req.size_usd,  # size in USD / price = shares
                side=req.side.value.lower(),  # "buy" or "sell"
                fee_rate_bps=10,  # default, could be configurable
                nonce=0,
                order_type=OrderType.GTC,
            )
            
            # Create and sign order
            signed_order = self.client.create_order(order_args)
            
            # Post order
            resp = self.client.post_order(signed_order)
            order_id = resp.get("order_id")
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
            resp = self.client.cancel_order(order_id)
            success = resp.get("success", False) or resp.get("cancelled", False)
            
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
    
    def close_position(self, token_id: str, size_usd: float, confirmation_code: Optional[str] = None) -> OrderResult:
        """Close (reduce) a position by placing opposite order."""
        # Get current position first
        try:
            positions = self.client.get_positions()
            position = None
            for p in positions:
                if p.get("token_id") == token_id:
                    position = p
                    break
            
            if not position:
                return OrderResult(
                    status=OrderStatus.REJECTED,
                    error=f"No open position found for token {token_id}",
                    timestamp=datetime.utcnow()
                )
            
            current_size = float(position.get("size", 0))
            if current_size <= 0:
                return OrderResult(
                    status=OrderStatus.REJECTED,
                    error="Position already closed or zero",
                    timestamp=datetime.utcnow()
                )
            
            # Determine close size (cap at current position)
            close_size = min(size_usd, current_size)
            
            # Place opposite order to close
            req = OrderRequest(
                market_slug=position.get("market_slug", "unknown"),
                token_id=token_id,
                outcome=position.get("outcome", "unknown"),
                side=Side.SELL if position.get("side") == "buy" else Side.BUY,
                size_usd=close_size,
                price=float(position.get("current_price", 0.5)),
            )
            
            # Build plan and execute
            if confirmation_code:
                plan = self.build_execution_plan(confirmation_code, True)
                plan.order_request = req
                return self.execute_order(plan)
            else:
                # No confirmation - just place reduce order
                order_args = OrderArgs(
                    token_id=req.token_id,
                    price=req.price,
                    size=close_size,
                    side=req.side.value.lower(),
                    fee_rate_bps=10,
                    nonce=0,
                    order_type=OrderType.GTC,
                )
                signed_order = self.client.create_order(order_args)
                resp = self.client.post_order(signed_order)
                order_id = resp.get("order_id")
                
                return OrderResult(
                    order_id=order_id,
                    status=OrderStatus.SUBMITTED,
                    timestamp=datetime.utcnow()
                )
                
        except Exception as e:
            redacted = self._redact(str(e))
            return OrderResult(
                status=OrderStatus.REJECTED,
                error=redacted,
                timestamp=datetime.utcnow()
            )
    
    def get_status(self) -> dict:
        """Get account/clob status."""
        if not self.config.has_credentials():
            return {"ready": False, "reason": "No credentials"}
        
        try:
            # Test connection
            positions = self.client.get_positions()
            open_orders = self.client.get_orders()
            
            return {
                "ready": True,
                "funder_address": self.config.funder_address[:10] + "..." if self.config.funder_address else None,
                "open_positions": len(positions),
                "open_orders": len(open_orders),
                "paper_trading": not self.config.live_trading,
            }
        except Exception as e:
            return {
                "ready": False,
                "reason": f"Status check failed: {type(e).__name__}",
            }