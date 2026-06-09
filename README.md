# Hermes Polymarket Action Layer

**Action/trading layer for Hermes on Polymarket** — secure local credentials, trade preview, confirmation, risk limits, audit log, and real execution via official CLOB API.

> ⚠️ **Phase 4 Status**: Core execution engine implemented. Safety gates enforced. Live trading disabled by default.

---

## Features

- **Trade Preview** (`preview`) — fee/slippage estimates, confirmation code
- **Guarded Execution** (`execute`) — 8 safety gates before real order
- **Order Management** — `cancel`, `close`, `status`
- **Audit Log** (`audit`) — append-only JSONL with secret redaction
- **Risk Engine** — max order, daily, position, slippage limits
- **Geoblock Check** — official Polymarket endpoint at runtime
- **Secret Protection** — never logs private keys, API secrets, auth headers

---

## Quick Start

```bash
# Clone & install
cd /home/hermes/projects/hermes-polymarket-connector
python3 -m venv .venv
.venv/bin/pip install -e .[dev]

# Configure (NEVER commit .env)
cp .env.example .env
# Edit .env with your credentials

# Preview a trade
hermes-polymarket-action preview \
  --market "will-btc-hit-100k" \
  --token "0x1234567890123456789012345678901234567890123456789012345678901234" \
  --outcome Yes \
  --side BUY \
  --size 50 \
  --price 0.55

# Execute (requires all gates + confirmation code + --approve)
LIVE_TRADING=true \
POLYMARKET_PRIVATE_KEY=0x... \
POLYMARKET_FUNDER_ADDRESS=0x... \
hermes-polymarket-action execute --confirm-code ABCD1234 --approve
```

---

## Commands

| Command | Description |
|---------|-------------|
| `preview` | Generate trade preview with confirmation code |
| `execute` | Execute trade (all gates must pass) |
| `cancel` | Cancel open order by ID |
| `close` | Close/reduce position |
| `status` | Account/CLOB status |
| `audit` | Show recent audit log entries |

---

## Safety Gates (all must pass for live execution)

1. `LIVE_TRADING=true`
2. `REQUIRE_CONFIRMATION=true`
3. Valid credentials (`POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER_ADDRESS`)
4. Valid confirmation code from latest `preview`
5. Explicit `--approve` flag
6. Geoblock check passes (official Polymarket endpoint)
6. Risk limits: max order/daily/position/slippage
7. Market/token/outcome valid & market open
8. Audit log writable

---

## Configuration (`.env`)

```bash
# Required for live trading
POLYMARKET_PRIVATE_KEY=0x...your-private-key...
POLYMARKET_FUNDER_ADDRESS=0x...your-deposit-wallet-address...
POLYMARKET_SIGNATURE_TYPE=3

# API endpoints
POLYMARKET_CLOB_API_URL=https://clob.polymarket.com
POLYMARKET_CHAIN_ID=137
POLYMARKET_RPC_URL=https://polygon-rpc.com

# Gates (all must be true for real execution)
LIVE_TRADING=false
REQUIRE_CONFIRMATION=true

# Risk limits — TINY defaults for first live test
MAX_ORDER_USD=1
MAX_DAILY_USD=3
MAX_POSITION_USD=5
MAX_SLIPPAGE_BPS=100
MAX_OPEN_ORDERS=50

# Geoblock
GEOBLOCK_CHECK=true

# Audit
AUDIT_LOG_PATH=~/.hermes/polymarket-action/audit.log
```

> **⚠️ NEVER commit real `.env`** — `.gitignore` blocks it.

---

## First Live Test (Manual)

1. Create dedicated Polymarket wallet (NOT your main wallet)
2. Fund with tiny amount (1-5 USDC)
3. Configure `.env` locally on your VPS
4. Run `status` → verify connection
5. Run `preview` → save confirmation code
6. Execute ONE tiny order only after confirmation
7. Test `cancel` / `close` if safe

---

## Security

See [SECURITY.md](SECURITY.md) for:
- Private key handling
- Local-only credentials
- Audit redaction
- Geoblock policy (no VPN bypass)
- Risk limits
- No financial advice

---

## Architecture

```
src/hermes_polymarket_action/
├── config.py        # Pydantic settings with validation
├── models.py        # OrderRequest, OrderPreview, OrderResult
├── validation.py    # Market/token/outcome validation
├── geoblock.py      # Official Polymarket geoblock endpoint
├── risk.py          # RiskEngine (order/daily/position/slippage)
├── audit.py         # Append-only JSONL audit log
├── confirmation.py  # Confirmation code verification
├── execution.py     # ClobClient wrapper + safety gates
└── cli.py           # Click commands (preview/execute/cancel/close/status/audit)
```

---

## Testing

```bash
# Run all tests (no credentials required)
.venv/bin/pytest tests/ -v

# Lint & type-check
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/
```

---

## License

MIT — see [LICENSE](LICENSE)