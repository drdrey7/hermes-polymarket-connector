# src/hermes_polymarket_action/audit.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import hashlib
from typing import Optional
from .config import ActionConfig

config = ActionConfig()


@dataclass
class AuditEntry:
    timestamp: str
    action: str  # preview, execute, cancel, close
    market_slug: str
    token_id: str
    outcome: str
    side: str
    size_usd: float
    price: float
    confirmation_code: Optional[str] = None
    request_hash: Optional[str] = None
    order_id: Optional[str] = None
    tx_hash: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None
    filled_size_usd: float = 0.0
    avg_fill_price: Optional[float] = None


class AuditLog:
    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or config.audit_log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _compute_request_hash(self, entry: AuditEntry) -> str:
        """Compute SHA256 of request parameters for integrity."""
        payload = f"{entry.market_slug}:{entry.token_id}:{entry.outcome}:{entry.side}:{entry.size_usd}:{entry.price}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def log(self, entry: AuditEntry) -> str:
        """Append entry to JSONL log. Returns the line number."""
        if entry.request_hash is None:
            entry.request_hash = self._compute_request_hash(entry)

        line = json.dumps(asdict(entry), ensure_ascii=False)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return str(self._get_line_count())

    def _get_line_count(self) -> int:
        if not self.log_path.exists():
            return 0
        return sum(1 for _ in self.log_path.open("r"))

    def read_all(self) -> list[AuditEntry]:
        """Read all entries from log."""
        if not self.log_path.exists():
            return []
        entries = []
        with self.log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    entries.append(AuditEntry(**data))
        return entries

    def get_by_confirmation_code(self, code: str) -> Optional[AuditEntry]:
        """Find entry by confirmation code."""
        for entry in self.read_all():
            if entry.confirmation_code == code:
                return entry
        return None


audit_log = AuditLog()