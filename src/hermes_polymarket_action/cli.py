# src/hermes_polymarket_action/cli.py
from __future__ import annotations
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from .config import ActionConfig
from .models import OrderRequest, OrderPreview, Side
from .validation import validate_market_token
from .geoblock import check_geoblock
from .risk import RiskEngine
from .audit import audit_log, AuditEntry
from .confirmation import verify_confirmation, mark_executing, mark_result
from datetime import datetime

console = Console()
config = ActionConfig()
risk_engine = RiskEngine(config)


@click.group()
def main():
    """Hermes Polymarket Action Layer — Trading CLI"""
    pass


@main.command()
@click.option("--market", required=True, help="Market slug (for display)")
@click.option("--token", "token_id", required=True, help="CLOB token ID (0x...)")
@click.option("--outcome", required=True, help="Outcome label (Yes/No)")
@click.option("--side", type=click.Choice(["BUY", "SELL"]), required=True)
@click.option("--size", type=float, required=True, help="Order size in USD")
@click.option("--price", type=float, required=True, help="Limit price (0-1)")
@click.option("--slippage", "slippage_bps", type=int, default=100, help="Max slippage in bps")
@click.option("--fee-bps", type=int, default=10, help="Fee in basis points")
def preview(market, token_id, outcome, side, size, price, slippage_bps, fee_bps):
    """Generate trade preview with confirmation code."""
    req = OrderRequest(
        market_slug=market,
        token_id=token_id,
        outcome=outcome,
        side=Side(side),
        size_usd=size,
        price=price,
        slippage_bps=slippage_bps,
    )
    # Mock current price = requested price for preview
    preview_obj = OrderPreview.from_request(req, current_price=price, fee_bps=fee_bps)

    # Log preview to audit
    audit_entry = AuditEntry(
        timestamp=datetime.utcnow().isoformat(),
        action="preview",
        market_slug=market,
        token_id=token_id,
        outcome=outcome,
        side=side,
        size_usd=size,
        price=price,
        confirmation_code=preview_obj.confirmation_code,
        status="pending",
    )
    audit_log.log(audit_entry)

    # Display
    table = Table(title="Trade Preview", show_header=True)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Market", preview_obj.request.market_slug)
    table.add_row("Outcome", preview_obj.request.outcome)
    table.add_row("Side", preview_obj.request.side.value)
    table.add_row("Size (USD)", f"${preview_obj.request.size_usd:.2f}")
    table.add_row("Limit Price", f"{preview_obj.request.price:.4f}")
    table.add_row("Current Price", f"{preview_obj.current_price:.4f}")
    table.add_row("Fee (bps)", str(preview_obj.fee_bps))
    table.add_row("Est. Fee (USD)", f"${preview_obj.estimated_fee_usd:.4f}")
    table.add_row("Max Slippage (USD)", f"${preview_obj.max_slippage_usd:.4f}")
    table.add_row("Worst Case Price", f"{preview_obj.worst_case_price:.6f}")
    table.add_row("Notional (USD)", f"${preview_obj.notional_usd:.2f}")
    console.print(table)

    # Confirmation code panel
    console.print(Panel(
        f"[bold yellow]{preview_obj.confirmation_code}[/bold yellow]",
        title="CONFIRMATION CODE",
        subtitle="Save this code — required for execution",
        border_style="yellow",
    ))

    # Risk gate warnings
    if not config.is_live_enabled():
        console.print("[dim]Live trading disabled. Set LIVE_TRADING=true and provide credentials to execute.[/dim]")


@main.command()
@click.option("--confirm-code", required=True, help="Confirmation code from preview")
@click.option("--approve", is_flag=True, required=True, help="Explicit approval (required)")
def execute(confirm_code, approve):
    """Execute a trade using confirmation code from preview."""
    # Gate 1: Live trading enabled
    if not config.is_live_enabled():
        console.print("[red]Live trading disabled. Set LIVE_TRADING=true and provide credentials.[/red]")
        return

    # Gate 2: Verify confirmation
    result = verify_confirmation(confirm_code, approve)
    if not result.valid:
        console.print(f"[red]Confirmation failed: {result.error}[/red]")
        return

    entry = result.entry
    if entry is None:
        console.print("[red]No audit entry found[/red]")
        return

    # Gate 3: Re-create order request from audit entry
    req = OrderRequest(
        market_slug=entry.market_slug,
        token_id=entry.token_id,
        outcome=entry.outcome,
        side=Side(entry.side),
        size_usd=entry.size_usd,
        price=entry.price,
    )

    # Gate 4: Validation
    val_result = validate_market_token(req.market_slug, req.token_id, req.outcome)
    if not val_result.valid:
        console.print(f"[red]Validation failed: {val_result.error}[/red]")
        mark_result(confirm_code, "rejected", error=val_result.error)
        return

    # Gate 5: Geoblock
    geo_result = check_geoblock(config)
    if not geo_result.allowed:
        console.print(f"[red]Geoblock failed: {geo_result.error}[/red]")
        mark_result(confirm_code, "rejected", error=geo_result.error)
        return

    # Gate 6: Risk engine
    risk_result = risk_engine.check(req)
    if not risk_result.allowed:
        console.print(f"[red]Risk check failed: {risk_result.error}[/red]")
        for w in risk_result.warnings:
            console.print(f"[yellow]Warning: {w}[/yellow]")
        mark_result(confirm_code, "rejected", error=risk_result.error)
        return
    for w in risk_result.warnings:
        console.print(f"[yellow]Warning: {w}[/yellow]")

    # All gates passed - mark executing
    console.print("[green]All checks passed. Executing trade...[/green]")
    mark_executing(confirm_code, "pending-order-id")

    # TODO: Actual execution via py-clob-client
    # For now, simulate success
    console.print("[yellow]Execution not yet implemented (placeholder)[/yellow]")
    
    # Simulate fill
    mark_result(
        confirm_code,
        "filled",
        tx_hash="0x" + "a" * 64,  # placeholder
        filled_size_usd=req.size_usd,
        avg_fill_price=req.price,
    )
    console.print("[green]Trade executed successfully (simulated)[/green]")


@main.command()
def audit():
    """Show recent audit log entries."""
    entries = audit_log.read_all()
    if not entries:
        console.print("[dim]No audit entries[/dim]")
        return

    table = Table(title="Audit Log (last 20)", show_header=True)
    table.add_column("Time", style="cyan")
    table.add_column("Action", style="white")
    table.add_column("Market", style="white")
    table.add_column("Side", style="white")
    table.add_column("Size", style="white")
    table.add_column("Code", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("TX Hash", style="dim")

    for entry in entries[-20:]:
        table.add_row(
            entry.timestamp[:19],
            entry.action,
            entry.market_slug,
            entry.side,
            f"${entry.size_usd:.2f}",
            entry.confirmation_code or "-",
            entry.status,
            entry.tx_hash[:12] + "..." if entry.tx_hash else "-",
        )
    console.print(table)


if __name__ == "__main__":
    main()