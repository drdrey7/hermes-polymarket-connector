# tests/test_risk.py
from hermes_polymarket_action.risk import RiskEngine
from hermes_polymarket_action.config import ActionConfig
from hermes_polymarket_action.models import OrderRequest, Side
import os


def make_config(**overrides):
    defaults = {
        "MAX_ORDER_USD": "100",
        "MAX_DAILY_USD": "500",
        "MAX_SLIPPAGE_BPS": "100",
        "MAX_POSITION_USD": "1000",
    }
    for k, v in overrides.items():
        defaults[k] = v
    for k, v in defaults.items():
        os.environ[k] = str(v)
    return ActionConfig()


def make_risk_engine(config, tmp_path):
    """Create RiskEngine with isolated daily_spent file."""
    daily_file = tmp_path / "daily_spent.json"
    return RiskEngine(config, daily_spent_path=daily_file)


def test_risk_engine_rejects_over_max_order(tmp_path):
    config = make_config(MAX_ORDER_USD="100")
    engine = make_risk_engine(config, tmp_path)
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=150, price=0.5,
    )
    result = engine.check(req)
    assert result.allowed is False
    assert "exceeds max" in result.error


def test_risk_engine_rejects_over_daily_limit(tmp_path):
    config = make_config(MAX_DAILY_USD="100")
    engine = make_risk_engine(config, tmp_path)
    
    # First order uses up daily limit
    req1 = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=100, price=0.5,
    )
    result1 = engine.check(req1)
    assert result1.allowed is True
    engine.record_fill(100)
    
    # Second order should exceed daily limit
    req2 = OrderRequest(
        market_slug="test", token_id="0x" + "2"*64, outcome="No",
        side=Side.BUY, size_usd=10, price=0.5,
    )
    result2 = engine.check(req2)
    assert result2.allowed is False
    assert "Daily limit would be exceeded" in result2.error


def test_risk_engine_allows_under_limits(tmp_path):
    config = make_config()
    engine = make_risk_engine(config, tmp_path)
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=50, price=0.5,
    )
    result = engine.check(req)
    assert result.allowed is True


def test_risk_engine_rejects_slippage_over_limit(tmp_path):
    config = make_config(MAX_SLIPPAGE_BPS="100")
    engine = make_risk_engine(config, tmp_path)
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=50, price=0.5, slippage_bps=200,
    )
    result = engine.check(req)
    assert result.allowed is False
    assert "Slippage" in result.error


def test_risk_engine_warns_large_position(tmp_path):
    config = make_config(MAX_ORDER_USD="1000", MAX_DAILY_USD="5000", MAX_POSITION_USD="1000")
    engine = make_risk_engine(config, tmp_path)
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=600, price=0.5,  # >50% of max_position_usd
    )
    result = engine.check(req)
    assert result.allowed is True
    assert any("50%" in w for w in result.warnings)