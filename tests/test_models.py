# tests/test_models.py
import pytest
from hermes_polymarket_action.models import OrderRequest, OrderPreview


def test_order_preview_calculates_fees_and_slippage():
    req = OrderRequest(
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=50.0,
        price=0.55,
        slippage_bps=100,
    )
    preview = OrderPreview.from_request(req, current_price=0.55, fee_bps=10)
    assert preview.estimated_fee_usd == 0.05  # 50 * 10bps
    assert preview.max_slippage_usd == 0.50   # 50 * 100bps
    assert preview.worst_case_price == 0.5445  # 0.55 * (1 - 1%) = 0.5445


def test_order_preview_sell_side_worst_case():
    req = OrderRequest(
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="SELL",
        size_usd=100.0,
        price=0.60,
        slippage_bps=200,  # 2%
    )
    preview = OrderPreview.from_request(req, current_price=0.60, fee_bps=10)
    # For SELL, worst case = price * (1 + slippage) = 0.60 * 1.02 = 0.612
    assert preview.worst_case_price == 0.612
    assert preview.estimated_fee_usd == 0.10  # 100 * 10bps
    assert preview.max_slippage_usd == 2.00   # 100 * 200bps


def test_order_request_validates_token_id():
    with pytest.raises(ValueError, match="Token ID must be 0x"):
        OrderRequest(
            market_slug="test", token_id="invalid", outcome="Yes",
            side="BUY", size_usd=10, price=0.5,
        )
    with pytest.raises(ValueError, match="Token ID must be 0x"):
        OrderRequest(
            market_slug="test", token_id="0x123", outcome="Yes",
            side="BUY", size_usd=10, price=0.5,
        )
    # Valid
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1" * 64, outcome="Yes",
        side="BUY", size_usd=10, price=0.5,
    )
    assert req.token_id == "0x" + "1" * 64


def test_confirmation_code_format():
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1" * 64, outcome="Yes",
        side="BUY", size_usd=10, price=0.5,
    )
    preview = OrderPreview.from_request(req, current_price=0.5, fee_bps=10)
    assert len(preview.confirmation_code) == 8
    assert preview.confirmation_code.isupper()
    assert preview.confirmation_code.isalnum()