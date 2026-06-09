# src/hermes_polymarket_action/cli.py
from __future__ import annotations
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from .config import ActionConfig
from .models import OrderRequest, OrderPreview, Side

console = Console()
config = ActionConfig()


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


if __name__ == "__main__":
    main()