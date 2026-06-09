# tests/test_risk.py
from hermes_polymarket_action.risk import RiskEngine
from hermes_polymarket_action.config import ActionConfig
from hermes_polymarket_action.models import OrderRequest, Side


def test_risk_engine_rejects_over_max_order(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_USD", "100")
    monkeypatch.setenv("MAX_DAILY_USD", "500")
    monkeypatch.setenv("MAX_SLIPPAGE_BPS", "100")
    config = ActionConfig()
    engine = RiskEngine(config)
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=150, price=0.5,
    )
    result = engine.check(req)
    assert result.allowed is False
    assert "exceeds max" in result.error


def test_risk_engine_rejects_over_daily_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_ORDER_USD", "100")
    monkeypatch.setenv("MAX_DAILY_USD", "100")
    monkeypatch.setenv("MAX_SLIPPAGE_BPS", "100")
    config = ActionConfig()
    
    # Use temp file for daily spent
    daily_file = tmp_path / "daily_spent.json"
    engine = RiskEngine(config)
    engine.daily_spent_path = daily_file
    
    # First order uses up daily limit
    req1 = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=100, price=0.5,
    )
    result1 = engine.check(req1)
    assert result1.allowed is True
    engine.record_fill(100)  # record fill
    
    # Second order should exceed daily limit
    req2 = OrderRequest(
        market_slug="test", token_id="0x" + "2"*64, outcome="No",
        side=Side.BUY, size_usd=10, price=0.5,
    )
    result2 = engine.check(req2)
    assert result2.allowed is False
    assert "Daily limit would be exceeded" in result2.error


def test_risk_engine_allows_under_limits(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_USD", "100")
    monkeypatch.setenv("MAX_DAILY_USD", "500")
    monkeypatch.setenv("MAX_SLIPPAGE_BPS", "100")
    config = ActionConfig()
    engine = RiskEngine(config)
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=50, price=0.5,
    )
    result = engine.check(req)
    assert result.allowed is True


def test_risk_engine_rejects_slippage_over_limit(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_USD", "100")
    monkeypatch.setenv("MAX_DAILY_USD", "500")
    monkeypatch.setenv("MAX_SLIPPAGE_BPS", "100")
    config = ActionConfig()
    engine = RiskEngine(config)
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=50, price=0.5, slippage_bps=200,
    )
    result = engine.check(req)
    assert result.allowed is False
    assert "Slippage" in result.error


def test_risk_engine_warns_large_position(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_USD", "1000")
    monkeypatch.setenv("MAX_DAILY_USD", "5000")
    monkeypatch.setenv("MAX_SLIPPAGE_BPS", "100")
    monkeypatch.setenv("MAX_POSITION_USD", "1000")
    config = ActionConfig()
    engine = RiskEngine(config)
    req = OrderRequest(
        market_slug="test", token_id="0x" + "1"*64, outcome="Yes",
        side=Side.BUY, size_usd=600, price=0.5,  # >50% of max_position_usd
    )
    result = engine.check(req)
    assert result.allowed is True
    assert any("50%" in w for w in result.warnings)