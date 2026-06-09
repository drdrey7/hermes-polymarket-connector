### Task 0.1: Create pyproject.toml with deps

**Files:** Create `pyproject.toml`

**Step 1: Write failing test**

```bash
# No test — scaffold task
```

**Step 2: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "hermes-polymarket-action"
version = "0.1.0"
description = "Action/trading layer for Hermes on Polymarket — secure local credentials, trade preview, confirmation, risk limits, audit log"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "python-keyring>=25.0",
    "click>=8.1",
    "py-clob-client>=0.3",
    "httpx>=0.27",
    "python-dotenv>=1.0",
    "rich>=13.7",
]
dynamic = ["version"]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-mock>=3.14",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.7",
]

[project.entry-points."console_scripts"]
hermes-polymarket-action = "hermes_polymarket_action.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

**Step 3: Verify**

```bash
cd /home/hermes/projects/hermes-polymarket-connector
python -m pip install -e .[dev]  # Should succeed
```

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pyproject.toml with deps and entry point"
```

---

### Task 0.2: Create config models with validation

**Files:** Create `src/hermes_polymarket_action/__init__.py`, `src/hermes_polymarket_action/config.py`, `tests/test_config.py`

**Step 1: Write failing test**

```python
# tests/test_config.py
def test_config_loads_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "a" * 64)
    monkeypatch.setenv("POLYMARKET_FUNDER", "0x" + "b" * 40)
    from hermes_polymarket_action.config import ActionConfig
    cfg = ActionConfig()
    assert cfg.private_key == "0x" + "a" * 64
    assert cfg.funder == "0x" + "b" * 40
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_config.py::test_config_loads_from_env -v
# Expected: FAIL — module not found
```

**Step 3: Write config.py**

```python
# src/hermes_polymarket_action/config.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class ActionConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required for live trading
    private_key: Optional[str] = Field(default=None, alias="POLYMARKET_PRIVATE_KEY")
    funder: Optional[str] = Field(default=None, alias="POLYMARKET_FUNDER")
    proxy_wallet: Optional[str] = Field(default=None, alias="POLYMARKET_PROXY_WALLET")

    # RPC / API
    rpc_url: str = Field(default="https://polygon-rpc.com", alias="POLYMARKET_RPC_URL")
    clob_api_url: str = Field(default="https://clob.polymarket.com", alias="POLYMARKET_CLOB_API_URL")

    # Live trading gates (ALL must be true for real execution)
    live_trading: bool = Field(default=False, alias="LIVE_TRADING")
    require_confirmation: bool = Field(default=True, alias="REQUIRE_CONFIRMATION")

    # Risk limits
    max_order_usd: float = Field(default=100.0, alias="MAX_ORDER_USD")
    max_daily_usd: float = Field(default=500.0, alias="MAX_DAILY_USD")
    max_slippage_bps: int = Field(default=100, alias="MAX_SLIPPAGE_BPS")
    max_position_usd: float = Field(default=1000.0, alias="MAX_POSITION_USD")

    # Geoblock
    geoblock_check: bool = Field(default=True, alias="GEOBLOCK_CHECK")
    allowed_countries: list[str] = Field(default=["PT", "US", "GB", "DE", "FR"], alias="ALLOWED_COUNTRIES")

    # Audit
    audit_log_path: Path = Field(default=Path("~/.hermes/polymarket-action/audit.log").expanduser(), alias="AUDIT_LOG_PATH")

    @field_validator("private_key")
    @classmethod
    def validate_private_key(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("0x"):
            raise ValueError("Private key must start with 0x")
        if v is not None and len(v) != 66:
            raise ValueError("Private key must be 66 chars (0x + 64 hex)")
        return v

    @field_validator("funder", "proxy_wallet")
    @classmethod
    def validate_address(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.startswith("0x") and len(v) == 42):
            raise ValueError("Address must be 0x + 40 hex chars")
        return v

    def is_live_enabled(self) -> bool:
        return (
            self.live_trading
            and self.require_confirmation
            and self.private_key is not None
            and self.funder is not None
        )
```

**Step 4: Write __init__.py**

```python
# src/hermes_polymarket_action/__init__.py
from __future__ import annotations
__version__ = "0.1.0"
from .config import ActionConfig
__all__ = ["ActionConfig", "__version__"]
```

**Step 5: Run test to verify pass**

```bash
pytest tests/test_config.py::test_config_loads_from_env -v
# Expected: PASS
```

**Step 6: Commit**

```bash
git add src/hermes_polymarket_action/__init__.py src/hermes_polymarket_action/config.py tests/test_config.py
git commit -m "feat: add config models with validation and live-trading gates"
```

---

### Task 0.3: Create .env.example and .gitignore

**Files:** Create `.env.example`, `.gitignore`

**Step 1: Write .env.example**

```bash
# .env.example — copy to .env and fill in (NEVER commit .env)
# Required for live trading
POLYMARKET_PRIVATE_KEY=0x...your-private-key...
POLYMARKET_FUNDER=0x...your-wallet-address...
# Optional: if using proxy wallet
# POLYMARKET_PROXY_WALLET=0x...proxy-address...

# RPC / API (defaults shown)
POLYMARKET_RPC_URL=https://polygon-rpc.com
POLYMARKET_CLOB_API_URL=https://clob.polymarket.com

# Live trading gates — ALL must be true for real execution
LIVE_TRADING=false
REQUIRE_CONFIRMATION=true

# Risk limits
MAX_ORDER_USD=100
MAX_DAILY_USD=500
MAX_SLIPPAGE_BPS=100
MAX_POSITION_USD=1000

# Geoblock
GEOBLOCK_CHECK=true
ALLOWED_COUNTRIES=PT,US,GB,DE,FR

# Audit
AUDIT_LOG_PATH=~/.hermes/polymarket-action/audit.log
```

**Step 2: Write .gitignore**

```
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
build/
dist/
*.egg-info/
.venv/
venv/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Env & secrets
.env
.env.local
*.key
*.pem

# Logs
*.log
~/.hermes/polymarket-action/audit.log

# Test artifacts
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# OS
.DS_Store
Thumbs.db
```

**Step 3: Commit**

```bash
git add .env.example .gitignore
git commit -m "chore: add .env.example and .gitignore"
```

---

## Phase 1 — Core Types & Trade Preview

### Task 1.1: Define trade models (Order, Preview, Confirmation, Result)

**Files:** Create `src/hermes_polymarket_action/models.py`, `tests/test_models.py`

**Step 1: Write failing test**

```python
# tests/test_models.py
def test_order_preview_calculates_fees_and_slippage():
    from hermes_polymarket_action.models import OrderRequest, OrderPreview
    req = OrderRequest(
        market_slug="test-market",
        token_id="0x123...",
        outcome="Yes",
        side="BUY",
        size_usd=50.0,
        price=0.55,
        slippage_bps=100,
    )
    preview = OrderPreview.from_request(req, current_price=0.55, fee_bps=10)
    assert preview.estimated_fee_usd == 0.05  # 50 * 10bps
    assert preview.max_slippage_usd == 0.50   # 50 * 100bps
    assert preview.worst_case_price == 0.545  # 0.55 * (1 - 1%)
```

**Step 2: Write models.py**

```python
# src/hermes_polymarket_action/models.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import secrets
import hashlib

class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PREVIEW = "PREVIEW"
    CONFIRMED = "CONFIRMED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class OrderRequest(BaseModel):
    market_slug: str = Field(..., description="Human-readable market slug")
    token_id: str = Field(..., description="CLOB token ID for the outcome")
    outcome: str = Field(..., description="Outcome label (Yes/No)")
    side: Side
    size_usd: float = Field(..., gt=0, description="Order size in USD")
    price: float = Field(..., gt=0, lt=1, description="Limit price (0-1)")
    slippage_bps: int = Field(default=100, ge=0, le=10000, description="Max slippage in basis points")
    expire_seconds: int = Field(default=300, ge=30, description="Order expiry seconds")

    @field_validator("token_id")
    @classmethod
    def validate_token_id(cls, v: str) -> str:
        if not v.startswith("0x") or len(v) != 66:
            raise ValueError("Token ID must be 0x + 64 hex chars")
        return v

@dataclass
class OrderPreview:
    request: OrderRequest
    current_price: float
    fee_bps: int
    estimated_fee_usd: float
    max_slippage_usd: float
    worst_case_price: float
    notional_usd: float
    confirmation_code: str

    @classmethod
    def from_request(cls, req: OrderRequest, current_price: float, fee_bps: int = 10) -> OrderPreview:
        notional = req.size_usd
        est_fee = notional * fee_bps / 10000
        max_slippage = notional * req.slippage_bps / 10000
        if req.side == Side.BUY:
            worst = current_price * (1 - req.slippage_bps / 10000)
        else:
            worst = current_price * (1 + req.slippage_bps / 10000)
        # Generate confirmation code: SHA256(request + timestamp)[:8].upper()
        raw = f"{req.model_dump_json()}{datetime.utcnow().isoformat()}".encode()
        code = hashlib.sha256(raw).hexdigest()[:8].upper()
        return cls(
            request=req,
            current_price=current_price,
            fee_bps=fee_bps,
            estimated_fee_usd=round(est_fee, 4),
            max_slippage_usd=round(max_slippage, 4),
            worst_case_price=round(worst, 6),
            notional_usd=notional,
            confirmation_code=code,
        )

class ConfirmationRequest(BaseModel):
    confirmation_code: str
    user_approval: bool = True

class OrderResult(BaseModel):
    order_id: Optional[str] = None
    status: OrderStatus
    tx_hash: Optional[str] = None
    filled_size_usd: float = 0.0
    avg_fill_price: Optional[float] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

**Step 3: Run test**

```bash
pytest tests/test_models.py::test_order_preview_calculates_fees_and_slippage -v
# Expected: PASS
```

**Step 4: Commit**

```bash
git add src/hermes_polymarket_action/models.py tests/test_models.py
git commit -m "feat: add trade models (OrderRequest, OrderPreview, Confirmation, OrderResult)"
```