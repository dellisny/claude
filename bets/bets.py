#!/usr/bin/env python3
"""bets — Top prediction market bets from Polymarket, Manifold, and PredictIt."""

import json
from typing import Optional
import click
import requests
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()
TIMEOUT = 10


# ---------------------------------------------------------------------------
# Polymarket (Gamma API)
# ---------------------------------------------------------------------------

def fetch_polymarket(keyword: Optional[str], limit: int) -> list[dict]:
    try:
        # When filtering by keyword, fetch a large batch for client-side filtering
        # (the API's q= param does not reliably filter results)
        fetch_limit = 500 if keyword else max(limit * 3, 30)
        params = {
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": fetch_limit,
        }

        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params=params,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        markets = resp.json()

        if keyword:
            kw = keyword.lower()
            markets = [
                m for m in markets
                if kw in (m.get("question") or m.get("title") or "").lower()
            ]

        results = []
        for m in markets:
            title = m.get("question") or m.get("title") or "Unknown"

            prob = None
            raw = m.get("outcomePrices")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    raw = None
            if isinstance(raw, list) and raw:
                try:
                    prob = float(raw[0])
                except (ValueError, TypeError):
                    pass

            vol = 0.0
            try:
                vol = float(m.get("volume24hr") or m.get("volume") or 0)
            except (ValueError, TypeError):
                pass

            results.append({
                "title": title,
                "prob": ("<1%" if prob * 100 < 1 else f"{prob * 100:.0f}%") if prob is not None else "—",
                "volume": f"${vol:>10,.0f}/day",
                "url": f"https://polymarket.com/market/{m.get('slug', '')}",
            })
            if len(results) >= limit:
                break

        return results
    except requests.RequestException as e:
        console.print(f"  [dim red]Polymarket error: {e}[/dim red]")
        return []


# ---------------------------------------------------------------------------
# Manifold Markets
# ---------------------------------------------------------------------------

def fetch_manifold(keyword: Optional[str], limit: int) -> list[dict]:
    try:
        # search-markets accepts sort=liquidity for both keyword and no-keyword cases
        params = {
            "term": keyword or "",
            "limit": limit,
            "sort": "liquidity",
            "filter": "open",
        }
        resp = requests.get(
            "https://api.manifold.markets/v0/search-markets",
            params=params,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        markets = resp.json()

        results = []
        for m in markets[:limit]:
            prob = m.get("probability")
            liquidity = 0.0
            try:
                liquidity = float(m.get("totalLiquidity") or m.get("volume") or 0)
            except (ValueError, TypeError):
                pass

            results.append({
                "title": m.get("question", "Unknown"),
                "prob": f"{prob * 100:.0f}%" if prob is not None else "—",
                "volume": f"M${liquidity:>8,.0f}",
                "url": m.get("url", ""),
            })
        return results
    except requests.RequestException as e:
        console.print(f"  [dim red]Manifold error: {e}[/dim red]")
        return []


# ---------------------------------------------------------------------------
# PredictIt
# ---------------------------------------------------------------------------

def fetch_predictit(keyword: Optional[str], limit: int) -> list[dict]:
    try:
        resp = requests.get(
            "https://www.predictit.org/api/marketdata/all/",
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        all_markets = resp.json().get("markets", [])

        if keyword:
            kw = keyword.lower()
            all_markets = [
                m for m in all_markets
                if kw in m.get("name", "").lower()
            ]

        results = []
        for m in all_markets[:limit]:
            contracts = m.get("contracts") or []
            # For binary markets show Yes%; for multi-contract show leading option
            if len(contracts) == 1:
                c = contracts[0]
                price = c.get("lastTradePrice") or c.get("bestBuyYesCost")
                prob_str = f"{price * 100:.0f}%" if price is not None else "—"
                leader = ""
            else:
                # Sort by lastTradePrice descending to find leading option
                contracts_sorted = sorted(
                    contracts,
                    key=lambda c: c.get("lastTradePrice") or 0,
                    reverse=True,
                )
                top = contracts_sorted[0]
                price = top.get("lastTradePrice") or top.get("bestBuyYesCost")
                prob_str = f"{price * 100:.0f}%" if price is not None else "—"
                leader = top.get("name", "")

            title = m.get("name", "Unknown")
            if leader:
                title = f"{title}  [{leader}]"

            results.append({
                "title": title,
                "prob": prob_str,
                "volume": f"{len(contracts)} contract{'s' if len(contracts) != 1 else ''}",
                "url": m.get("url", ""),
            })

        return results
    except requests.RequestException as e:
        console.print(f"  [dim red]PredictIt error: {e}[/dim red]")
        return []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_table(name: str, color: str, results: list[dict]) -> None:
    if not results:
        console.print(f"[{color}]{name}[/{color}]: [dim]no results[/dim]\n")
        return

    table = Table(
        title=f"[bold {color}]{name}[/bold {color}]",
        box=box.ROUNDED,
        show_header=True,
        header_style=f"bold {color}",
        expand=True,
    )
    table.add_column("#", style="dim", width=3, no_wrap=True, justify="right")
    table.add_column("Market / Question", ratio=5, overflow="fold")
    table.add_column("Yes %", justify="right", width=6, no_wrap=True)
    table.add_column("Activity", justify="right", width=20, no_wrap=True)

    for i, r in enumerate(results, 1):
        table.add_row(str(i), r["title"], r["prob"], r["volume"])

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.argument("keyword", required=False, default=None)
@click.option("--limit", "-n", default=10, show_default=True, help="Results per source.")
def main(keyword: Optional[str], limit: int) -> None:
    """Show top prediction market bets.

    Optionally filter by KEYWORD across Polymarket, Manifold, and PredictIt.
    """
    header = "[bold cyan]Top Bets[/bold cyan]"
    if keyword:
        header += f"  [dim]·[/dim]  [bold yellow]{keyword}[/bold yellow]"
    console.print(f"\n{header}\n")

    sources = [
        ("Polymarket", "green", fetch_polymarket),
        ("Manifold", "blue", fetch_manifold),
        ("PredictIt", "magenta", fetch_predictit),
    ]

    with console.status("[bold green]Fetching markets…[/bold green]", spinner="dots"):
        fetched = [(name, color, fn(keyword, limit)) for name, color, fn in sources]

    console.print()
    for name, color, results in fetched:
        render_table(name, color, results)


if __name__ == "__main__":
    main()
