# tests/test_confirmation.py
from hermes_polymarket_action.confirmation import verify_confirmation, mark_executing, mark_result
from hermes_polymarket_action.audit import AuditLog, AuditEntry
from hermes_polymarket_action.config import ActionConfig


def make_audit_log(tmp_path):
    """Create an AuditLog with a temp file."""
    log_file = tmp_path / "audit.log"
    config = ActionConfig()
    config.audit_log_path = log_file
    return AuditLog(log_file)


def test_verify_confirmation_valid(tmp_path):
    audit = make_audit_log(tmp_path)
    
    entry = AuditEntry(
        timestamp="2026-01-01T00:00:00",
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
    
    # Monkeypatch the singleton
    import hermes_polymarket_action.confirmation as conf
    original_log = conf.audit_log
    conf.audit_log = audit
    try:
        result = verify_confirmation("ABCD1234", user_approval=True)
        assert result.valid is True
        assert result.entry is not None
        assert result.entry.confirmation_code == "ABCD1234"
    finally:
        conf.audit_log = original_log


def test_verify_confirmation_invalid_code(tmp_path):
    audit = make_audit_log(tmp_path)
    
    import hermes_polymarket_action.confirmation as conf
    original_log = conf.audit_log
    conf.audit_log = audit
    try:
        result = verify_confirmation("INVALID", user_approval=True)
        assert result.valid is False
        assert "Invalid or expired" in result.error
    finally:
        conf.audit_log = original_log


def test_verify_confirmation_user_denied(tmp_path):
    audit = make_audit_log(tmp_path)
    
    entry = AuditEntry(
        timestamp="2026-01-01T00:00:00",
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
    original_log = conf.audit_log
    conf.audit_log = audit
    try:
        result = verify_confirmation("ABCD1234", user_approval=False)
        assert result.valid is False
        assert "User did not approve" in result.error
    finally:
        conf.audit_log = original_log


def test_verify_confirmation_already_used(tmp_path):
    audit = make_audit_log(tmp_path)
    
    entry = AuditEntry(
        timestamp="2026-01-01T00:00:00",
        action="execute",
        market_slug="test-market",
        token_id="0x" + "1" * 64,
        outcome="Yes",
        side="BUY",
        size_usd=50.0,
        price=0.55,
        confirmation_code="ABCD1234",
        status="filled",
    )
    audit.log(entry)
    
    import hermes_polymarket_action.confirmation as conf
    original_log = conf.audit_log
    conf.audit_log = audit
    try:
        result = verify_confirmation("ABCD1234", user_approval=True)
        assert result.valid is False
        assert "already used" in result.error
    finally:
        conf.audit_log = original_log


def test_mark_executing_and_result(tmp_path):
    audit = make_audit_log(tmp_path)
    
    entry = AuditEntry(
        timestamp="2026-01-01T00:00:00",
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
    original_log = conf.audit_log
    conf.audit_log = audit
    try:
        # Mark executing
        assert mark_executing("ABCD1234", "order-123") is True
        entries = audit.read_all()
        assert entries[0].status == "executing"
        assert entries[0].order_id == "order-123"
        
        # Mark result
        assert mark_result("ABCD1234", "filled", "tx-hash-123", 50.0, 0.545) is True
        entries = audit.read_all()
        assert entries[0].status == "filled"
        assert entries[0].tx_hash == "tx-hash-123"
        assert entries[0].filled_size_usd == 50.0
        assert entries[0].avg_fill_price == 0.545
    finally:
        conf.audit_log = original_log