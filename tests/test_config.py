# tests/test_config.py
import pytest


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "a" * 64)
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0x" + "b" * 40)
    from hermes_polymarket_action.config import ActionConfig
    cfg = ActionConfig()
    assert cfg.private_key == "0x" + "a" * 64
    assert cfg.funder_address == "0x" + "b" * 40


def test_config_validates_private_key_format(monkeypatch):
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "invalid-key")
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0x" + "b" * 40)
    from hermes_polymarket_action.config import ActionConfig
    with pytest.raises(ValueError, match="Private key must start with 0x"):
        ActionConfig()


def test_config_validates_address_format(monkeypatch):
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "a" * 64)
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setenv("POLYMARKET_PROXY_WALLET", "invalid-address")
    from hermes_polymarket_action.config import ActionConfig
    with pytest.raises(ValueError, match="Address must be 0x"):
        ActionConfig()


def test_config_live_enabled_gates(monkeypatch):
    from hermes_polymarket_action.config import ActionConfig
    
    # All false by default
    cfg = ActionConfig()
    assert cfg.is_live_enabled() is False
    
    # Only live_trading true
    monkeypatch.setenv("LIVE_TRADING", "true")
    cfg = ActionConfig()
    assert cfg.is_live_enabled() is False  # missing credentials
    
    # Live trading + credentials + confirmation = all gates pass
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "a" * 64)
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setenv("REQUIRE_CONFIRMATION", "true")
    cfg = ActionConfig()
    assert cfg.is_live_enabled() is True