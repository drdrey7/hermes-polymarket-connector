# tests/test_geoblock.py
from hermes_polymarket_action.geoblock import check_geoblock
import hermes_polymarket_action.geoblock as gb
from hermes_polymarket_action.config import ActionConfig


def test_geoblock_bypass_when_disabled(monkeypatch):
    monkeypatch.setenv("GEOBLOCK_CHECK", "false")
    config = ActionConfig()
    result = check_geoblock(config)
    assert result.allowed is True
    assert result.country_code == "BYPASS"


def test_geoblock_allows_allowed_country(monkeypatch):
    monkeypatch.setenv("GEOBLOCK_CHECK", "true")
    monkeypatch.setenv("ALLOWED_COUNTRIES", '["PT", "US", "GB"]')
    config = ActionConfig()
    
    # Mock get_country_code to return PT
    original = gb.get_country_code
    gb.get_country_code = lambda: "PT"
    try:
        result = check_geoblock(config)
        assert result.allowed is True
        assert result.country_code == "PT"
    finally:
        gb.get_country_code = original


def test_geoblock_denies_blocked_country(monkeypatch):
    monkeypatch.setenv("GEOBLOCK_CHECK", "true")
    monkeypatch.setenv("ALLOWED_COUNTRIES", '["PT", "US", "GB"]')
    config = ActionConfig()
    
    original = gb.get_country_code
    gb.get_country_code = lambda: "RU"
    try:
        result = check_geoblock(config)
        assert result.allowed is False
        assert result.country_code == "RU"
        assert "not in allowed list" in result.error
    finally:
        gb.get_country_code = original


def test_geoblock_fails_when_no_location(monkeypatch):
    monkeypatch.setenv("GEOBLOCK_CHECK", "true")
    monkeypatch.setenv("ALLOWED_COUNTRIES", '["PT", "US", "GB"]')
    config = ActionConfig()
    
    original = gb.get_country_code
    gb.get_country_code = lambda: None
    try:
        result = check_geoblock(config)
        assert result.allowed is False
        assert "Could not determine location" in result.error
    finally:
        gb.get_country_code = original