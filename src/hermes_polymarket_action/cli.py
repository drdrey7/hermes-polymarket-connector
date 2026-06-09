# src/hermes_polymarket_action/cli.py
from __future__ import annotations
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from .config import ActionConfig
from .models import OrderRequest, OrderPreview, Side, OrderStatus
from .validation import validate_market_token
from .geoblock import check_geoblock
from .risk import RiskEngine
from .audit import audit_log, AuditEntry
from .confirmation import mark_result
from .execution import ExecutionEngine
from datetime import datetime

console = Console()
config = ActionConfig()
risk_engine = RiskEngine(config)
execution_engine = ExecutionEngine(config)


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

    # Gates status
    if not config.is_live_enabled():
        console.print("[dim]Live trading disabled. Set LIVE_TRADING=true and provide credentials to execute.[/dim]")
    else:
        # Quick validation preview
        val = validate_market_token(req.market_slug, req.token_id, req.outcome)
        risk = risk_engine.check(req)
        geo = check_geoblock(config)
        
        gates = [
            ("Live trading", config.live_trading),
            ("Credentials", config.has_credentials()),
            ("Confirmation", config.require_confirmation),
            ("Market valid", val.valid),
            ("Risk limits", risk.allowed),
            ("Geoblock", geo.allowed),
        ]
        
        gate_table = Table(title="Safety Gates", show_header=True)
        gate_table.add_column("Gate", style="cyan")
        gate_table.add_column("Status", style="white")
        for name, passed in gates:
            gate_table.add_row(name, "[green]PASS[/green]" if passed else "[red]BLOCK[/red]")
        console.print(gate_table)


@main.command()
@click.option("--confirm-code", required=True, help="Confirmation code from preview")
@click.option("--approve", is_flag=True, required=True, help="Explicit approval (required)")
def execute(confirm_code, approve):
    """Execute a trade using confirmation code from preview."""
    plan = execution_engine.build_execution_plan(confirm_code, approve)
    
    if not plan.allowed:
        console.print(f"[red]BLOCKED: {plan.reason}[/red]")
        return
    
    console.print("[green]All gates passed. Executing...[/green]")
    
    if not config.live_trading:
        console.print("[yellow]DRY_RUN mode (LIVE_TRADING=false) — order not sent to network[/yellow]")
        # Simulate dry-run result
        mark_result(
            confirm_code,
            "dry_run",
            filled_size_usd=plan.order_request.size_usd if plan.order_request else 0,
            avg_fill_price=plan.order_request.price if plan.order_request else None,
        )
        console.print("[green]Dry-run complete (no network call)[/green]")
        return
    
    # Real execution
    result = execution_engine.execute_order(plan)
    
    if result.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED):
        console.print(f"[green]EXECUTED: order_id={result.order_id}, tx={result.tx_hash}[/green]")
    else:
        console.print(f"[red]FAILED: {result.error}[/red]")


@main.command()
@click.argument("order_id")
@click.option("--confirm-code", help="Confirmation code from preview (optional)")
def cancel(order_id, confirm_code):
    """Cancel an open order."""
    if not config.is_live_enabled():
        console.print("[red]BLOCKED: Live trading disabled[/red]")
        return
    
    if not config.live_trading:
        console.print("[yellow]DRY_RUN mode (LIVE_TRADING=false) — cancel not sent to network[/yellow]")
        return
    
    console.print(f"Cancelling order {order_id}...")
    result = execution_engine.cancel_order(order_id, confirm_code)
    
    if result.status == OrderStatus.CANCELLED:
        console.print(f"[green]CANCELLED: {order_id}[/green]")
    else:
        console.print(f"[red]CANCEL FAILED: {result.error}[/red]")


@main.command()
@click.option("--token", "token_id", required=True, help="CLOB token ID (0x...)")
@click.option("--size", type=float, required=True, help="Size to close in USD")
@click.option("--confirm-code", required=True, help="Confirmation code from preview (required)")
@click.option("--approve", is_flag=True, required=True, help="Explicit approval (required)")
def close(token_id, size, confirm_code, approve):
    """Close (reduce) a position. Requires confirmation code and approval."""
    if not config.is_live_enabled():
        console.print("[red]BLOCKED: Live trading disabled[/red]")
        return

    if not config.live_trading:
        console.print("[yellow]DRY_RUN mode (LIVE_TRADING=false) — close not sent to network[/yellow]")
        return

    console.print(f"Closing position for token {token_id[:12]}... (${size:.2f})")
    result = execution_engine.close_position(token_id, size, confirm_code, approve)

    if result.status in (OrderStatus.SUBMITTED, OrderStatus.FILLED):
        console.print(f"[green]CLOSE ORDER SUBMITTED: order_id={result.order_id}[/green]")
    else:
        console.print(f"[red]CLOSE FAILED: {result.error}[/red]")


@main.command()
def status():
    """Show account/CLOB status."""
    s = execution_engine.get_status()

    table = Table(title="Account Status", show_header=True)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    for k, v in s.items():
        table.add_row(k.replace("_", " ").title(), str(v))

    console.print(table)

    # Show gates summary with actual geoblock check
    console.print("\n[bold]Safety Gates[/bold]")
    gates_table = Table(show_header=True)
    gates_table.add_column("Gate", style="cyan")
    gates_table.add_column("Status", style="white")

    from .geoblock import check_geoblock
    geo = check_geoblock(config)

    gates = [
        ("LIVE_TRADING", config.live_trading),
        ("REQUIRE_CONFIRMATION", config.require_confirmation),
        ("Credentials", config.has_credentials()),
        ("Geoblock check", config.geoblock_check),
        ("Geoblock actual", geo.allowed),
    ]

    for name, passed in gates:
        gates_table.add_row(name, "[green]ON[/green]" if passed else "[red]OFF[/red]")
    console.print(gates_table)


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
            (entry.tx_hash[:12] + "...") if entry.tx_hash else "-",
        )
    console.print(table)


if __name__ == "__main__":
    main()