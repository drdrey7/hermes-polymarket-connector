# tests/test_validation.py
from hermes_polymarket_action.validation import validate_market_token


def test_validate_market_token_invalid_token_id():
    result = validate_market_token("test-market", "invalid", "Yes")
    assert result.valid is False
    assert "Invalid token_id format" in result.error

    result = validate_market_token("test-market", "0x123", "Yes")
    assert result.valid is False


def test_validate_market_token_fallback_mode_ok():
    # When get_market_for_token returns None, fallback accepts user input
    result = validate_market_token("test-market", "0x" + "1" * 64, "Yes")
    assert result.valid is True
    assert result.market_slug == "test-market"
    assert result.token_id == "0x" + "1" * 64
    assert result.outcome == "Yes"