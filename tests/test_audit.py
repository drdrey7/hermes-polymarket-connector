# tests/test_audit.py
from hermes_polymarket_action.audit import AuditLog, AuditEntry
from hermes_polymarket_action.config import ActionConfig


def make_audit_log(tmp_path):
    log_file = tmp_path / "audit.log"
    config = ActionConfig()
    config.audit_log_path = log_file
    return AuditLog(log_file)


def test_audit_log_append_and_read(tmp_path):
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
    
    line_num = audit.log(entry)
    assert line_num == "1"
    
    entries = audit.read_all()
    assert len(entries) == 1
    assert entries[0].confirmation_code == "ABCD1234"
    assert entries[0].request_hash is not None


def test_audit_log_find_by_confirmation_code(tmp_path):
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
    
    found = audit.get_by_confirmation_code("ABCD1234")
    assert found is not None
    assert found.confirmation_code == "ABCD1234"
    
    not_found = audit.get_by_confirmation_code("WRONGCODE")
    assert not_found is None