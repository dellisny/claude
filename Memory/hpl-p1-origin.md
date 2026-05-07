# HPL-P1 Origin Document

**Source:** "How to build an unusual options screener (using Claude Code)" by Dave Wang, April 13, 2026

This newsletter article was the original spec used to build the HPL-P1 options flow scanner.

## Core Concept

Options markets leave "footprints" when insiders with informational edge place directional bets. The goal is to separate signal from noise automatically by:

1. Connecting to live options data via MCP servers
2. Running an 8-step screening funnel with institutional thresholds
3. Cross-referencing with insider trades, congressional activity, and social sentiment
4. Scoring and ranking by conviction (0–10), saving all scans for backtesting

## Original Data Sources (from article)

- **Unusual Whales MCP** — live options flow alerts, full options tape, contract screener, insider transactions, congressional trades, OI changes, earnings calendars, dark pool prints
- **X MCP** — Twitter/X sentiment scanning and catalyst research

> Note: Our implementation uses **yfinance** for options data and **SEC EDGAR** for insider trades (Form 4 XML parsing) + congressional disclosure data — not the MCP servers. This was a deliberate substitution: user does not yet have API keys for Unusual Whales or X/Twitter. Claude suggested these free alternatives as a starting point. When API keys are obtained, upgrading to Unusual Whales MCP (live tape, dark pool prints) and X MCP (sentiment) is the intended next step.

## Screening Criteria (Hard Filters)

| Filter | Threshold | Strong Signal |
|---|---|---|
| Vol/OI ratio | > 2x | > 5x |
| Premium | > $250K | > $1M ("golden sweep") |
| DTE | 7–21 days | — |
| Execution | Ask-side (buyer paid offer) | — |

## False-Positive Exclusions

Automatically strips out:
- Earnings-week gamma hedging
- Married puts
- Index arbitrage spillover
- Dividend capture strategies
- Roll activity
- Meme squeeze mechanics

## Conviction Scoring Rubric (0–10)

**+2 points each:**
- Insider trade in same direction within 30 days
- Congressional trade in same direction within 60 days
- Same ticker on consecutive scan days (repeat activity)
- Vol/OI > 5x OR premium > $1M

**+1 point each:**
- Sweep execution, ask-side fills, short DTE, deep OTM, floor trades, confirmed opening positions

**Deductions (-1 to -2):**
- Earnings proximity, macro event alignment, bid-side execution, meme stock flags

## Example Results from April 10 Scan (from article)

**Bullish — $PANW (score: 10/10):**
- CEO Nikesh Arora bought ~68k shares at $146.87 on March 27 (~$10M open-market)
- Rep. Gilbert Cisneros bought PANW stock March 13
- $3.1M in LEAPS call sweeps at $175 strike (March 2027 expiry), all at ask, across multiple exchanges

**Bearish — $MU (score: 9/10):**
- EVP Sumit Sadana sold 24k shares at $421 (discretionary, not 10b5-1)
- Put OI building for 9 consecutive days on $345 strike, >$4M put premium across near-term strikes
- Earnings not until June 24 — not routine hedging

## Key Design Philosophy

"Quantimental" approach: fundamental catalysts scored by quantitative signals, refined by a growing proprietary dataset of scan history.
