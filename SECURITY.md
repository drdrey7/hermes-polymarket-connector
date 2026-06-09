# Security Policy

## Private Key Handling

- **Never commit `.env`** — `.gitignore` enforces this
- **Private keys stay local** — never transmitted to our servers, never logged
- **Use dedicated wallet** — create a fresh Polymarket deposit wallet for this tool
- **Minimal funds** — only deposit what you're willing to lose (recommend 1-5 USDC for first tests)

```bash
# .env (local only, NEVER commit)
POLYMARKET_PRIVATE_KEY=0x...          # 64 hex chars, 0x prefix
POLYMARKET_FUNDER_ADDRESS=0x...       # Deposit wallet address (NOT necessarily owner EOA)
POLYMARKET_SIGNATURE_TYPE=3           # 3 = new API users / deposit wallet flow
```

> **Signature type 3** is for Polymarket deposit wallet flow. The `FUNDER_ADDRESS` should be your Polymarket deposit wallet address, which may differ from your EOA owner address. Verify this in your Polymarket account settings.

---

## Credential Isolation

- **Local-only** — credentials never leave your machine
- **No cloud storage** — no key vault, no remote backup
- **Environment variables** — loaded from `.env` at runtime only
- **No defaults** — all credentials must be explicitly provided

---

## Audit Log Redaction

Append-only JSONL at `~/.hermes/polymarket-action/audit.log`:

**Always redacted:**
- Private keys (`0x` + 64 hex)
- API keys/secrets/passphrases
- `Authorization: Bearer ...` headers
- `POLY_*` authentication headers

**Logged (safe):**
- Confirmation codes
- Market slugs, token IDs, outcomes
- Order sizes, prices, sides
- Status transitions (pending → executing → filled/rejected)
- Transaction hashes (public on-chain)

---

## Geoblock Policy

- **Official endpoint only** — `GET https://clob.polymarket.com/geoblock`
- **Fail-safe** — any endpoint failure blocks execution by default
- **No bypass** — VPN/geoblock circumvention not supported
- **Runtime check** — called before every live execution

```json
// Success response
{"country": "PT", "blocked": false}

// Blocked response
{"country": "RU", "blocked": true}
```

---

## Risk Limits (Configurable)

| Limit | Default (First Test) | Description |
|-------|---------------------|-------------|
| `MAX_ORDER_USD` | 1 | Single order max size |
| `MAX_DAILY_USD` | 3 | Daily volume cap |
| `MAX_POSITION_USD` | 5 | Max position exposure |
| `MAX_SLIPPAGE_BPS` | 100 | Max slippage (1%) |
| `MAX_OPEN_ORDERS` | 50 | Concurrent open orders |

> **Always start tiny.** First live order should use $1 or less.

---

## Execution Safety

All gates must pass before real order:

```
LIVE_TRADING=true
REQUIRE_CONFIRMATION=true
├── Valid credentials present
├── Confirmation code matches latest preview
├── Explicit --approve flag
├── Geoblock clear
├── Risk limits OK
├── Market/token valid & market active
└── Audit log writable
```

If ANY gate fails → **BLOCKED**, clear reason returned, no network call.

---

## What We Don't Do

- ❌ No autonomous trading
- ❌ No strategy engine / AI analysis
- ❌ No cloud key storage
- ❌ No VPN/geoblock bypass
- ❌ No high default limits
- ❌ No profit promises
- ❌ No financial advice

---

## Threat Model

| Threat | Mitigation |
|--------|------------|
| Private key leak | Local `.env`, gitignored, redacted in logs |
| API credential leak | Never logged, never printed |
| Geoblock bypass | Official endpoint, fail-safe default |
| Over-exposure | Configurable risk limits, daily caps |
| Audit tampering | Append-only JSONL |
| Replay attacks | Per-preview confirmation codes (SHA256) |

---

## Reporting Security Issues

Report vulnerabilities via GitHub Security Advisories (private) or email.

---

## Disclaimer

**This is experimental software.** Use at your own risk. Polymarket trading involves financial risk. Never trade more than you can afford to lose. This tool provides execution infrastructure only — no strategy, no advice, no guarantees.