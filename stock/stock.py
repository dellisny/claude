#!/usr/bin/env python3
"""Stock Metrics CLI — fetch key investment metrics and ASCII price chart."""

import sys
import click
import yfinance as yf
import plotext as plt
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

PERIOD_MAP = {
    "1m": "1mo",
    "3m": "3mo",
    "6m": "6mo",
    "1y": "1y",
    "2y": "2y",
    "5y": "5y",
}

INDEX_MAP = {
    "NMS": ("^IXIC", "NASDAQ"),
    "NGM": ("^IXIC", "NASDAQ"),
    "NCM": ("^IXIC", "NASDAQ"),
    "NYQ": ("^GSPC", "S&P 500"),
    "ASE": ("^GSPC", "S&P 500"),
}


def resolve_ticker(company_name: str) -> tuple[str, str]:
    """Search for a company and return (symbol, longName)."""
    with console.status(f"[bold cyan]Searching for '{company_name}'...[/]"):
        results = yf.Search(company_name, max_results=5).quotes

    if not results:
        console.print(f"[red]No results found for '{company_name}'.[/]")
        sys.exit(1)

    # Filter to equity results only
    equities = [r for r in results if r.get("quoteType") == "EQUITY"]
    if not equities:
        equities = results  # fall back to all results

    top = equities[0]
    symbol = top.get("symbol", "")
    name = top.get("longname") or top.get("shortname") or symbol

    # Show alternatives if more than one equity found
    if len(equities) > 1:
        console.print(f"\n[bold]Matched:[/] [green]{symbol}[/] — {name}")
        console.print("[dim]Other matches:[/]")
        for r in equities[1:4]:
            console.print(
                f"  [dim]{r.get('symbol','?'):8s}  {r.get('longname') or r.get('shortname','')}[/]"
            )
        console.print()

    return symbol, name


def fmt_large(value) -> str:
    """Format large numbers (market cap, revenue) with T/B/M suffix."""
    if value is None:
        return "N/A"
    if value >= 1e12:
        return f"${value/1e12:.2f}T"
    if value >= 1e9:
        return f"${value/1e9:.2f}B"
    if value >= 1e6:
        return f"${value/1e6:.2f}M"
    return f"${value:,.0f}"


def fmt_pct(value) -> str:
    if value is None:
        return "N/A"
    return f"{value*100:.1f}%"


def fmt_float(value, decimals=2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def fmt_price(value) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def get_price_fcf(info: dict, cashflow) -> str:
    """Compute Price/FCF = price / (FCF per share)."""
    try:
        price = info.get("currentPrice")
        shares = info.get("sharesOutstanding")
        if cashflow is None or cashflow.empty or price is None or shares is None:
            return "N/A"

        # cashflow rows are labelled; find operating cash flow and capex
        def find_row(df, *keys):
            for key in keys:
                for idx in df.index:
                    if key.lower() in str(idx).lower():
                        return df.loc[idx].iloc[0]
            return None

        operating_cf = find_row(
            cashflow,
            "Operating Cash Flow",
            "Cash From Operations",
            "Total Cash From Operating Activities",
        )
        capex = find_row(
            cashflow,
            "Capital Expenditure",
            "Capital Expenditures",
            "Purchase Of Property Plant And Equipment",
        )

        if operating_cf is None or capex is None:
            return "N/A"

        # capex is typically negative in yfinance
        fcf = operating_cf + capex  # capex already negative
        if fcf <= 0:
            return "N/A"
        fcf_per_share = fcf / shares
        return fmt_float(price / fcf_per_share)
    except Exception:
        return "N/A"


def fetch_metrics(symbol: str):
    """Return (info dict, cashflow df, news list) for the given ticker."""
    with console.status(f"[bold cyan]Fetching data for {symbol}...[/]"):
        ticker = yf.Ticker(symbol)
        info = ticker.info
        try:
            cashflow = ticker.cashflow
        except Exception:
            cashflow = None
        try:
            news = ticker.news or []
        except Exception:
            news = []
    return info, cashflow, news


def select_index(info: dict) -> tuple[str, str]:
    """Return (index_symbol, index_label) based on exchange."""
    exchange = info.get("exchange", "")
    return INDEX_MAP.get(exchange, ("^GSPC", "S&P 500"))


def render_header(symbol: str, info: dict):
    name = info.get("longName") or info.get("shortName") or symbol
    sector = info.get("sector", "N/A")
    industry = info.get("industry", "N/A")
    exchange = info.get("exchange", "N/A")
    currency = info.get("currency", "USD")

    title = Text()
    title.append(symbol, style="bold green")
    title.append(f" · {name}", style="bold white")

    subtitle = f"Sector: {sector}  |  Industry: {industry}  |  Exchange: {exchange}  |  Currency: {currency}"
    console.print(Panel(subtitle, title=title, border_style="bright_blue"))


def _div_yield(info: dict) -> str:
    """Compute dividend yield from dividendRate / currentPrice (more reliable)."""
    rate = info.get("dividendRate")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if rate and price and price > 0:
        return fmt_pct(rate / price)
    # Fall back to the field directly if it looks like a decimal fraction
    raw = info.get("dividendYield")
    if raw is not None:
        return fmt_pct(raw if raw < 1 else raw / 100)
    return "N/A"


def render_metrics(symbol: str, info: dict, cashflow):
    price_fcf = get_price_fcf(info, cashflow)

    price = info.get("currentPrice")
    lo52 = info.get("fiftyTwoWeekLow")
    hi52 = info.get("fiftyTwoWeekHigh")
    week_range = (
        f"{fmt_price(lo52)} / {fmt_price(hi52)}"
        if lo52 and hi52
        else "N/A"
    )

    # Build three-column table
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan", expand=False)
    table.add_column("Valuation", style="white", min_width=26)
    table.add_column("Profitability", style="white", min_width=26)
    table.add_column("Other", style="white", min_width=26)

    rows = [
        (
            f"[bold]Market Cap[/]   {fmt_large(info.get('marketCap'))}",
            f"[bold]Gross Margin[/]  {fmt_pct(info.get('grossMargins'))}",
            f"[bold]Beta[/]          {fmt_float(info.get('beta'))}",
        ),
        (
            f"[bold]Price[/]         {fmt_price(price)}",
            f"[bold]Net Margin[/]    {fmt_pct(info.get('profitMargins'))}",
            f"[bold]Div Yield[/]     {_div_yield(info)}",
        ),
        (
            f"[bold]P/E (ttm)[/]     {fmt_float(info.get('trailingPE'))}",
            f"[bold]Rev (TTM)[/]     {fmt_large(info.get('totalRevenue'))}",
            f"[bold]52W Range[/]     {week_range}",
        ),
        (
            f"[bold]P/E (fwd)[/]     {fmt_float(info.get('forwardPE'))}",
            "",
            "",
        ),
        (
            f"[bold]EV/EBITDA[/]     {fmt_float(info.get('enterpriseToEbitda'))}",
            "",
            "",
        ),
        (
            f"[bold]P/FCF[/]         {price_fcf}",
            "",
            "",
        ),
    ]

    for r in rows:
        table.add_row(*r)

    console.print(table)


def render_news(news: list, limit: int = 5):
    """Print top news headlines."""
    if not news:
        console.print("[dim]No recent news found.[/]\n")
        return

    console.print("[bold cyan]Top News[/]")
    for i, item in enumerate(news[:limit], 1):
        content = item.get("content", {})
        title = content.get("title") or item.get("title") or "(no title)"
        provider = (content.get("provider") or {}).get("displayName") or item.get("publisher", "")
        pub_date = content.get("pubDate") or ""
        date_str = pub_date[:10] if pub_date else ""
        meta = "  ".join(filter(None, [provider, date_str]))
        console.print(f"  [bold white]{i}.[/] {title}")
        if meta:
            console.print(f"     [dim]{meta}[/]")
    console.print()


def render_chart(symbol: str, index_symbol: str, index_label: str, period: str):
    yf_period = PERIOD_MAP.get(period, "1y")
    label_period = period.upper()

    with console.status(f"[bold cyan]Downloading price history ({label_period})...[/]"):
        data = yf.download(
            [symbol, index_symbol],
            period=yf_period,
            interval="1d",
            auto_adjust=True,
            progress=False,
        )

    if data.empty:
        console.print("[red]Could not fetch price history.[/]")
        return

    try:
        close = data["Close"]
        stock_prices = close[symbol].dropna()
        index_prices = close[index_symbol].dropna()
    except KeyError:
        console.print("[red]Price data missing for one or both tickers.[/]")
        return

    # Align dates
    common_idx = stock_prices.index.intersection(index_prices.index)
    if len(common_idx) < 2:
        console.print("[red]Insufficient overlapping price data.[/]")
        return

    stock_prices = stock_prices.loc[common_idx]
    index_prices = index_prices.loc[common_idx]

    # Normalize to 100 at start
    stock_norm = (stock_prices / stock_prices.iloc[0] * 100).tolist()
    index_norm = (index_prices / index_prices.iloc[0] * 100).tolist()

    # X-axis: integer offsets (plotext works best with these)
    x = list(range(len(common_idx)))
    dates = [str(d.date()) for d in common_idx]

    # Tick positions and labels (show ~6 evenly spaced dates)
    n = len(x)
    tick_count = min(6, n)
    tick_pos = [round(i * (n - 1) / (tick_count - 1)) for i in range(tick_count)]
    tick_labels = [dates[i] for i in tick_pos]

    plt.clf()
    plt.plot(x, stock_norm, label=symbol)
    plt.plot(x, index_norm, label=index_label)
    plt.title(f"{symbol} vs {index_label} — {label_period} (normalized to 100)")
    plt.xlabel("Date")
    plt.ylabel("Relative Price")
    plt.xticks(tick_pos, tick_labels)
    plt.theme("dark")
    plt.plotsize(100, 25)
    plt.show()


@click.command()
@click.argument("company_name")
@click.option(
    "--period",
    default="1y",
    show_default=True,
    type=click.Choice(["1m", "3m", "6m", "1y", "2y", "5y"]),
    help="Chart lookback period.",
)
def main(company_name: str, period: str):
    """Show key investment metrics and ASCII price chart for a public company.

    COMPANY_NAME can be a full name ("Apple Inc"), common name ("Apple"),
    or ticker ("AAPL").
    """
    symbol, _name = resolve_ticker(company_name)
    info, cashflow, news = fetch_metrics(symbol)

    if not info or info.get("quoteType") not in ("EQUITY", "ETF", None):
        # quoteType may be absent for some tickers — proceed anyway
        pass

    index_symbol, index_label = select_index(info)

    console.print()
    render_header(symbol, info)
    console.print()
    render_metrics(symbol, info, cashflow)
    console.print()
    render_news(news)
    render_chart(symbol, index_symbol, index_label, period)


if __name__ == "__main__":
    main()
