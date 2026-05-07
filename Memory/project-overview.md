# Project Overview — claude/ Webapp

## What This Is

A personal FastAPI web dashboard served locally. It aggregates several tools and data sources into a unified, password-protected web interface. The app lives in `webapp/app.py` (~4000+ lines) and serves Jinja2 templates from `webapp/templates/`.

## Authentication

Session-based auth via cookie. Login at `/login`; sessions stored in `webapp/data/sessions.json`. Supports passphrase change and session revocation at `/sessions`.

## Features / Routes

| Route | Description |
|---|---|
| `/` | Dashboard index |
| `/headlines` | Aggregated RSS news headlines from multiple sources |
| `/bets` | Prediction market data (Polymarket, Manifold, PredictIt) |
| `/hnt` | Helium (HNT) token price tracker with anchor/threshold/pause controls |
| `/stock` | Stock data via yfinance |
| `/hpl-p1` | Options flow scanner (see below) |
| `/explorenyc` | NYC events scraper (The Skint, Songkick, TimeOut) |
| `/minorcay` | Task manager with undo support, stored in `minorcay_tasks.toml` |
| `/gittyup` | Git tool |
| `/btree` | B-tree visualizer |
| `/mastermind` | Mastermind game |
| `/shade` | Shade tool |
| `/twenty` | Twenty tool |
| `/sysinfo` | System info |
| `/sessions` | Session management |

## HPL-P1 (Options Flow Scanner)

The most complex feature. Scans a watchlist of tickers for unusual options activity and insider/congressional trading signals.

**Database:** `webapp/data/hpl_scans.db` (SQLite)
- `hpl_scans` — scan runs (id, status, progress, timestamps)
- `hpl_signals` — individual option signals per scan

**Signal fields include:**
- Option metadata: ticker, contract symbol, type (call/put), strike, expiry, DTE, volume, OI, vol/OI ratio, premium, last price, IV, ITM flag
- Derived flags: `is_golden_sweep`, `is_strong_vol_oi`, `near_earnings`, `is_index_etf`
- `conviction_score` — composite ranking score
- `insider_trades` / `congress_trades` — JSON-encoded related trades from SEC Form 4 and congressional disclosure data
- `flags` — JSON array of signal flag labels

**Scan flow:** POST `/hpl-p1/scan` starts an async scan (background thread, progress tracked by scan_id). GET `/hpl-p1/scan/{id}/progress` polls status via SSE. GET `/hpl-p1/scan/{id}/results` returns completed signals.

## Tech Stack

- **Framework:** FastAPI + Uvicorn/Gunicorn
- **Templates:** Jinja2 (dark terminal aesthetic, yellow accent color)
- **Data:** yfinance, feedparser, requests, pandas
- **Storage:** SQLite (hpl_scans.db), JSON files (sessions, claude_usage)
- **Auth:** Cookie-based sessions with passphrase

## Session Log

| Date | Topic |
|---|---|
| 2026-05-05 | User confirmed this Memory directory approach. Initial overview written from code inspection. |
| 2026-05-05 | User shared the origin article for HPL-P1 (Dave Wang newsletter, April 13 2026). Saved to `hpl-p1-origin.md`. |
| 2026-05-05 | v1 feedback reviewed. All fixes deferred to HPL-P2, which will also add Unusual Whales + X MCP integration. Roadmap saved to `hpl-p2-roadmap.md`. |
