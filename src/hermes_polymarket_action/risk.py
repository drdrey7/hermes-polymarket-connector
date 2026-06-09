# src/hermes_polymarket_action/risk.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from pathlib import Path
import json
from .config import ActionConfig
from .models import OrderRequest


@dataclass
class RiskCheckResult:
    allowed: bool
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


class RiskEngine:
    def __init__(self, config: Optional[ActionConfig] = None, daily_spent_path: Optional[Path] = None):
        self.config = config or ActionConfig()
        if daily_spent_path is None:
            self.daily_spent_path = Path("~/.hermes/polymarket-action/daily_spent.json").expanduser()
        else:
            self.daily_spent_path = daily_spent_path
        self.daily_spent_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_daily_spent(self) -> dict[str, float]:
        if self.daily_spent_path.exists():
            import typing
            return typing.cast(dict[str, float], json.loads(self.daily_spent_path.read_text()))
        return {}

    def _save_daily_spent(self, data: dict[str, float]):
        self.daily_spent_path.write_text(json.dumps(data))

    def _get_today_spent(self) -> float:
        data = self._load_daily_spent()
        today = date.today().isoformat()
        return float(data.get(today, 0.0))

    def _record_spent(self, amount_usd: float):
        data = self._load_daily_spent()
        today = date.today().isoformat()
        data[today] = data.get(today, 0.0) + amount_usd
        self._save_daily_spent(data)

    def check(self, req: OrderRequest) -> RiskCheckResult:
        # Max order
        if req.size_usd > self.config.max_order_usd:
            return RiskCheckResult(
                allowed=False,
                error=f"Order size ${req.size_usd:.2f} exceeds max ${self.config.max_order_usd:.2f}",
            )

        # Daily limit
        today_spent = self._get_today_spent()
        if today_spent + req.size_usd > self.config.max_daily_usd:
            return RiskCheckResult(
                allowed=False,
                error=f"Daily limit would be exceeded: ${today_spent:.2f} spent + ${req.size_usd:.2f} > ${self.config.max_daily_usd:.2f}",
            )

        # Slippage
        if req.slippage_bps > self.config.max_slippage_bps:
            return RiskCheckResult(
                allowed=False,
                error=f"Slippage {req.slippage_bps}bps exceeds max {self.config.max_slippage_bps}bps",
            )

        # Position limit (would need position tracking — placeholder)
        warnings = []
        if req.size_usd > self.config.max_position_usd * 0.5:
            warnings.append(f"Order size is >50% of max position limit (${self.config.max_position_usd})")

        return RiskCheckResult(allowed=True, warnings=warnings)

    def record_fill(self, filled_usd: float):
        """Call after order fills to update daily spend."""
        self._record_spent(filled_usd)