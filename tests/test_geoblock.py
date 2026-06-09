# tests/test_geoblock.py
from hermes_polymarket_action.geoblock import check_geoblock
from hermes_polymarket_action.config import ActionConfig
import os
import httpx
from unittest.mock import patch, MagicMock, Mock


def make_config(**overrides):
    """Create ActionConfig with test values."""
    defaults = {
        "GEOBLOCK_CHECK": "true",
        "POLYMARKET_CLOB_API_URL": "https://clob.polymarket.com",
    }
    for k, v in overrides.items():
        defaults[k] = v
    for k, v in defaults.items():
        os.environ[k] = str(v)
    return ActionConfig()


def test_geoblock_bypass_when_disabled():
    config = make_config(GEOBLOCK_CHECK="false")
    result = check_geoblock(config)
    assert result.allowed is True
    assert result.country_code == "BYPASS"
    assert "disabled" in result.error.lower()


def test_geoblock_allows_allowed_country():
    """Geoblock endpoint returns blocked=false."""
    config = make_config()
    
    with patch('httpx.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"country": "PT", "blocked": False}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_geoblock(config)
        assert result.allowed is True
        assert result.country_code == "PT"
    
    # Verify correct endpoint called
    assert mock_get.called
    args, kwargs = mock_get.call_args
    assert args[0] == "https://polymarket.com/api/geoblock"


def test_geoblock_denies_blocked_country():
    """Geoblock endpoint returns blocked=true."""
    config = make_config()
    
    with patch('httpx.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"country": "RU", "blocked": True}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_geoblock(config)
        assert result.allowed is False
        assert result.country_code == "RU"
        assert "blocked in RU" in result.error


def test_geoblock_fails_when_no_location():
    """Geoblock endpoint returns no country field."""
    config = make_config()
    
    with patch('httpx.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocked": False}  # no country
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_geoblock(config)
        assert result.allowed is True
        assert result.country_code == "unknown"


def test_geoblock_timeout_blocks_by_default():
    """Geoblock timeout should block by default."""
    config = make_config()
    
    with patch('httpx.get') as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Timeout")
        
        result = check_geoblock(config)
        assert result.allowed is False
        assert "timed out" in result.error.lower()


def test_geoblock_http_error_blocks_by_default():
    """Geoblock HTTP error should block by default."""
    config = make_config()
    
    with patch('httpx.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.side_effect = httpx.HTTPStatusError("Server Error", request=Mock(), response=mock_response)
        
        result = check_geoblock(config)
        assert result.allowed is False
        assert "HTTP 500" in result.error or "failed" in result.error.lower()


def test_geoblock_network_error_blocks_by_default():
    """Geoblock network error should block by default."""
    config = make_config()
    
    with patch('httpx.get') as mock_get:
        mock_get.side_effect = httpx.NetworkError("Connection refused")
        
        result = check_geoblock(config)
        assert result.allowed is False
        assert "failed" in result.error.lower()