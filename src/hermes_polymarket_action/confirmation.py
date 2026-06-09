# src/hermes_polymarket_action/confirmation.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional
import json
from .audit import AuditEntry, audit_log


@dataclass
class ConfirmationResult:
    valid: bool
    entry: Optional[AuditEntry] = None
    error: Optional[str] = None


def verify_confirmation(
    confirmation_code: str,
    user_approval: bool = True,
) -> ConfirmationResult:
    """
    Verify confirmation code matches a pending preview and user approves.
    """
    if not user_approval:
        return ConfirmationResult(valid=False, error="User did not approve")

    entry = audit_log.get_by_confirmation_code(confirmation_code)
    if entry is None:
        return ConfirmationResult(valid=False, error="Invalid or expired confirmation code")

    if entry.status != "pending":
        return ConfirmationResult(
            valid=False,
            error=f"Confirmation code already used (status: {entry.status})",
        )

    return ConfirmationResult(valid=True, entry=entry)


def _rewrite_log(entries: list[AuditEntry], log_path=None):
    """Rewrite entire log file with updated entries."""
    from .audit import audit_log as global_audit_log
    if log_path is None:
        log_path = global_audit_log.log_path
    
    with log_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            line = json.dumps(asdict(entry), ensure_ascii=False)
            f.write(line + "\n")


def mark_executing(confirmation_code: str, order_id: str) -> bool:
    """Mark audit entry as executing (updates file)."""
    entries = audit_log.read_all()
    for i, entry in enumerate(entries):
        if entry.confirmation_code == confirmation_code:
            entry.status = "executing"
            entry.order_id = order_id
            _rewrite_log(entries, audit_log.log_path)
            return True
    return False


def mark_result(
    confirmation_code: str,
    status: str,
    tx_hash: Optional[str] = None,
    filled_size_usd: float = 0.0,
    avg_fill_price: Optional[float] = None,
    error: Optional[str] = None,
) -> bool:
    """Mark audit entry with final result."""
    entries = audit_log.read_all()
    for i, entry in enumerate(entries):
        if entry.confirmation_code == confirmation_code:
            entry.status = status
            entry.tx_hash = tx_hash
            entry.filled_size_usd = filled_size_usd
            entry.avg_fill_price = avg_fill_price
            entry.error = error
            _rewrite_log(entries, audit_log.log_path)
            return True
    return False