# tests/test_validation.py
from hermes_polymarket_action.validation import validate_market_token


def test_validate_market_token_invalid_token_id():
    result = validate_market_token("test-market", "invalid", "Yes")
    assert result.valid is False
    assert "Invalid token_id format" in result.error

    result = validate_market_token("test-market", "0x123", "Yes")
    assert result.valid is False


def test_validate_market_token_fail_closed_when_skill_unavailable():
    # When get_market_for_token returns None (skill not integrated), validation fails closed
    result = validate_market_token("test-market", "0x" + "1" * 64, "Yes")
    assert result.valid is False
    assert "Market validation unavailable" in result.error
    assert "Hermes Polymarket skill not integrated" in result.error