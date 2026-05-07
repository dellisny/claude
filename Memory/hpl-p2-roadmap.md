# HPL-P2 Roadmap

**Status:** Waiting on Unusual Whales API key (trial starting week of 2026-05-12)

## What HPL-P2 Is

A full rebuild of the HPL-P1 options flow screener with real data sources replacing the free yfinance/SEC EDGAR layer. All v1 logic fixes will be folded in at the same time.

## Prerequisites

- [ ] Unusual Whales API key — confirm tier includes API access (not just web dashboard)
- [ ] X/Twitter API key
- [ ] Install and configure Unusual Whales MCP server
- [ ] Install and configure X MCP server

## Data Source Swap

| Signal | v1 (current) | v2 (target) |
|---|---|---|
| Options flow / tape | yfinance | Unusual Whales MCP |
| Insider trades | SEC EDGAR Form 4 XML | Unusual Whales MCP |
| Congressional trades | Congressional disclosure scrape | Unusual Whales MCP |
| Dark pool prints | Not available | Unusual Whales MCP |
| Earnings calendar | Not available | Unusual Whales MCP |
| Sentiment / catalysts | Not available | X MCP |

## Logic Fixes (from v1 feedback)

1. **ITM filter** — restrict to options no more than ~2% ITM (ATM/OTM only). Informed traders use options for leverage, not intrinsic value.
2. **Insider/congress lookup** — verify lookup is at equity level (not contract level). Exclude 10b5-1 scheduled sales from insider signals.
3. **Exclusion rules** — replace scoring deductions with hard exclusions using Unusual Whales data: earnings-week gamma hedging, married puts, index arb spillover, roll activity, meme mechanics.
4. **DTE range** — reconsider the 7–21 day cap. Wang's examples included LEAPS. Informed traders may use longer-dated options to avoid detection. Find a new upper bound that doesn't explode data volume.
5. **Conviction scoring** — give insider + congressional corroboration more weight once data is reliable.

## Future Features (post-P2)

- AI-generated qualitative context around output (social media, news, catalysts)
- Automated weekly scheduled runs with historical recording for backtesting
- AI-assisted backtesting of scan history
- Portfolio overlay mode: alerts for stocks user already holds or is watching (security review first)

## Session Log

| Date | Notes |
|---|---|
| 2026-05-05 | HPL-P2 roadmap created. Waiting on Unusual Whales trial week of 2026-05-12. |
