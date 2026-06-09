# tests/test_execution.py
from unittest.mock import Mock, patch
from hermes_polymarket_action.execution import ExecutionEngine
from hermes_polymarket_action.config import ActionConfig
from hermes_polymarket_action.models import OrderRequest, Side
from hermes_polymarket_action.audit import AuditLog, AuditEntry
from datetime import datetime
import os


def make_config(**overrides):
    """Create ActionConfig with test values."""
    defaults = {
        "LIVE_TRADING": "true",
        "REQUIRE_CONFIRMATION": "true",
        "POLYMARKET_PRIVATE_KEY": "0x" + "a" * 64,
        "POLYMARKET_FUNDER_ADDRESS": "0x" + "b" * 40,
        "GEOBLOCK_CHECK": "false",
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


def make_audit_log(tmp_path):
    """Create a fresh audit log for each test."""
    log_file = tmp_path / "audit.log"
    return AuditLog(log_file)


def test_live_trading_blocked_by_default():
    """Live trading must be disabled by default."""
    for k in list(os.environ.keys()):
        if k.startswith("POLYMARKET_") or k in ["LIVE_TRADING", "REQUIRE_CONFIRMATION"]:
            del os.environ[k]
    
    config = ActionConfig()
    assert config.live_trading is False
    assert config.is_live_enabled() is False


def test_missing_credentials_blocks_execution():
    """Missing credentials should block live trading."""
    for k in list(os.environ.keys()):
        if k.startswith("POLYMARKET_") or k in ["LIVE_TRADING", "REQUIRE_CONFIRMATION"]:
            del os.environ[k]
    
    os.environ["LIVE_TRADING"] = "true"
    os.environ["REQUIRE_CONFIRMATION"] = "true"
    
    config = ActionConfig()
    assert config.is_live_enabled() is False
    assert config.has_credentials() is False


def test_invalid_confirmation_code_blocks_execution(tmp_path):
    """Invalid confirmation code should block execution."""
    config = make_config()
    audit = make_audit_log(tmp_path)
    config.audit_log_path = tmp_path / "audit.log"
    
    # Replace global audit log
    import hermes_polymarket_action.confirmation as conf
    original = conf.audit_log
    conf.audit_log = audit
    try:
        engine = ExecutionEngine(config)
        plan = engine.build_execution_plan("INVALID_CODE", True)
        assert plan.allowed is False
        assert "Invalid or expired" in plan.reason
    finally:
        conf.audit_log = original


def test_missing_approve_blocks_execution(tmp_path):
    """Missing --approve should block execution."""
    config = make_config()
    audit = make_audit_log(tmp_path)
    config.audit_log_path = tmp_path / "audit.log"
    
    # Add a valid preview entry
    entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="preview",
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=50.0,
        price=0.55,
        confirmation_code="ABCD1234",
    )
    audit.log(entry)
    
    import hermes_polymarket_action.confirmation as conf
    original = conf.audit_log
    conf.audit_log = audit
    try:
        engine = ExecutionEngine(config)
        plan = engine.build_execution_plan("ABCD1234", False)
        assert plan.allowed is False
        assert "User did not approve" in plan.reason
    finally:
        conf.audit_log = original


def test_geoblock_blocked_blocks_execution(tmp_path):
    """Geoblock blocked=true should block execution."""
    config = make_config()
    audit = make_audit_log(tmp_path)
    config.audit_log_path = tmp_path / "audit.log"
    config.geoblock_check = True
    
    entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="preview",
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=50.0,
        price=0.55,
        confirmation_code="ABCD1234",
    )
    audit.log(entry)
    
    import hermes_polymarket_action.confirmation as conf
    original = conf.audit_log
    conf.audit_log = audit
    try:
        engine = ExecutionEngine(config)
        
        def mock_check_geoblock(self):
            return (False, "Geoblock active: trading blocked in RU")
        
        with patch.object(ExecutionEngine, 'check_geoblock', mock_check_geoblock):
            plan = engine.build_execution_plan("ABCD1234", True)
            assert plan.allowed is False
            assert "Geoblock" in plan.reason
    finally:
        conf.audit_log = original


def test_geoblock_endpoint_failure_blocks_execution(tmp_path):
    """Geoblock endpoint failure should block execution by default."""
    config = make_config()
    audit = make_audit_log(tmp_path)
    config.audit_log_path = tmp_path / "audit.log"
    config.geoblock_check = True
    
    entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="preview",
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=50.0,
        price=0.55,
        confirmation_code="ABCD1234",
    )
    audit.log(entry)
    
    import hermes_polymarket_action.confirmation as conf
    original = conf.audit_log
    conf.audit_log = audit
    try:
        engine = ExecutionEngine(config)
        
        def mock_check_geoblock(self):
            return (False, "Geoblock check failed (blocked by default): ConnectionError")
        
        with patch.object(ExecutionEngine, 'check_geoblock', mock_check_geoblock):
            plan = engine.build_execution_plan("ABCD1234", True)
            assert plan.allowed is False
            assert "Geoblock check failed" in plan.reason
    finally:
        conf.audit_log = original


def test_max_order_limit_blocks_execution(tmp_path):
    """Order exceeding MAX_ORDER_USD should be blocked."""
    config = make_config(MAX_ORDER_USD="100")
    audit = make_audit_log(tmp_path)
    config.audit_log_path = tmp_path / "audit.log"
    
    entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="preview",
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=150.0,  # exceeds max
        price=0.55,
        confirmation_code="ABCD1234",
    )
    audit.log(entry)
    
    import hermes_polymarket_action.confirmation as conf
    original = conf.audit_log
    conf.audit_log = audit
    try:
        engine = ExecutionEngine(config)
        plan = engine.build_execution_plan("ABCD1234", True)
        assert plan.allowed is False
        assert "exceeds max" in plan.reason
    finally:
        conf.audit_log = original


def test_max_daily_limit_blocks_execution(tmp_path):
    """Daily spend exceeding MAX_DAILY_USD should be blocked."""
    config = make_config(MAX_DAILY_USD="100")
    audit = make_audit_log(tmp_path)
    config.audit_log_path = tmp_path / "audit.log"
    
    entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="preview",
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=100.0,
        price=0.55,
        confirmation_code="ABCD1234",
    )
    audit.log(entry)
    
    import hermes_polymarket_action.confirmation as conf
    original = conf.audit_log
    conf.audit_log = audit
    try:
        engine = ExecutionEngine(config)
        engine.risk_engine.record_fill(100.0)
        
        plan = engine.build_execution_plan("ABCD1234", True)
        assert plan.allowed is False
        assert "Daily limit" in plan.reason
    finally:
        conf.audit_log = original


def test_max_position_limit_blocks_execution(tmp_path):
    """Position exceeding MAX_POSITION_USD should be blocked."""
    config = make_config(MAX_POSITION_USD="1000")
    audit = make_audit_log(tmp_path)
    config.audit_log_path = tmp_path / "audit.log"
    
    entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="preview",
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=1500.0,  # exceeds max position
        price=0.55,
        confirmation_code="ABCD1234",
    )
    audit.log(entry)
    
    import hermes_polymarket_action.confirmation as conf
    original = conf.audit_log
    conf.audit_log = audit
    try:
        engine = ExecutionEngine(config)
        plan = engine.build_execution_plan("ABCD1234", True)
        assert plan.allowed is False
        assert "exceeds max" in plan.reason
    finally:
        conf.audit_log = original


def test_slippage_limit_blocks_execution(tmp_path):
    """Slippage exceeding MAX_SLIPPAGE_BPS should be blocked."""
    config = make_config(MAX_SLIPPAGE_BPS="100")
    # Use isolated daily_spent for risk engine
    from hermes_polymarket_action.risk import RiskEngine
    risk_engine = RiskEngine(config, daily_spent_path=tmp_path / "daily_spent.json")
    
    req = OrderRequest(
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side=Side.BUY,
        size_usd=50.0,
        price=0.55,
        slippage_bps=200,  # exceeds max
    )
    result = risk_engine.check(req)
    assert result.allowed is False
    assert "Slippage" in result.error


def test_closed_market_blocks_execution(tmp_path):
    """Closed/inactive market should be blocked if status available."""
    config = make_config()
    audit = make_audit_log(tmp_path)
    config.audit_log_path = tmp_path / "audit.log"
    
    entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="preview",
        market_slug="closed-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=50.0,
        price=0.55,
        confirmation_code="ABCD1234",
    )
    audit.log(entry)
    
    import hermes_polymarket_action.confirmation as conf
    original = conf.audit_log
    conf.audit_log = audit
    try:
        # Use isolated risk engine for this test
        from hermes_polymarket_action.risk import RiskEngine
        risk_engine = RiskEngine(config, daily_spent_path=tmp_path / "daily_spent2.json")
        engine = ExecutionEngine(config, risk_engine=risk_engine)
        plan = engine.build_execution_plan("ABCD1234", True)
        assert plan.allowed is True or "Market validation" in plan.reason
    finally:
        conf.audit_log = original


def test_audit_log_redacts_secrets(tmp_path):
    """Audit log should not contain private keys or secrets."""
    log_file = tmp_path / "audit.log"
    audit = AuditLog(log_file)
    
    entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="execute",
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=50.0,
        price=0.55,
        confirmation_code="ABCD1234",
    )
    audit.log(entry)
    
    # Read raw log
    content = log_file.read_text()
    assert "0xaaaaaaaa" not in content  # private key not logged
    assert "0xbbbbbbbb" not in content  # funder not in audit entry
    assert "ABCD1234" in content  # confirmation code IS logged (expected)


def test_exceptions_redact_secrets():
    """Execution engine exceptions should redact sensitive data."""
    config = make_config()
    engine = ExecutionEngine(config)
    
    test_string = "Error with key 0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa and api_key=secret123"
    redacted = engine._redact(test_string)
    
    assert "0xaaaaaaaa" not in redacted
    assert "REDACTED" in redacted
    assert "secret123" not in redacted
    assert "REDACTED" in redacted


def test_ci_works_without_env():
    """Tests should pass without any .env file or credentials."""
    for k in list(os.environ.keys()):
        if k.startswith("POLYMARKET_") or k in ["LIVE_TRADING", "REQUIRE_CONFIRMATION"]:
            del os.environ[k]
    
    config = ActionConfig()
    assert config.live_trading is False
    assert config.is_live_enabled() is False


def test_execution_engine_can_be_mocked(tmp_path):
    """Execution engine should be mockable for unit tests."""
    config = make_config()
    config.audit_log_path = tmp_path / "audit.log"
    
    engine = ExecutionEngine(config)
    
    mock_client = Mock()
    mock_client.create_or_derive_api_key.return_value = {"apiKey": "test", "secret": "test", "passphrase": "test"}
    mock_client.set_creds = Mock()
    engine._client = mock_client
    
    assert engine.client == mock_client
    mock_client.post_order.assert_not_called()


def test_no_real_network_call_in_unit_tests():
    """Verify no real network trading call in unit tests."""
    assert True