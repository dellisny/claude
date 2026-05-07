# HPL-P1 v1 Feedback

Feedback received after first live run of the screener.

## Issues / Observations

### 1. Too Many ITM Options Being Flagged
Most flagged options were in-the-money (ITM). ITM options carry more intrinsic value so their premium is naturally high — this inflates the large-premium signal even when volume is actually small. Informed traders seeking leverage would use ATM or OTM options, consistent with Dave Wang's example output (all OTM).

**Action:** Restrict to options no more than ~2% ITM (i.e., ATM or slightly OTM). This also clears out low-OI situations where tiny volume looks outsized.

### 2. Congressional / Insider Data Not Appearing
No flagged positions showed congressional or insider activity in the UI. Open questions:
- Is the screener looking at activity in the specific option contract, or the underlying equity? (Should be equity.)
- If already doing equity-level lookups, this signal should get more weight to surface corroborated plays higher.
- Should exclude insider sales that are part of employee stock option / 10b5-1 scheduled programs — those are not informational.

### 3. Exclusion Rules Are Approximate
Current implementation uses scoring deductions (e.g., -1 for index ETF, -1 for earnings proximity) as a proxy for Wang's hard exclusions (earnings-week gamma hedging, married puts, index arb, roll activity, meme mechanics). Wang's more precise exclusions likely rely on data from Unusual Whales.

User is going to trial Unusual Whales to evaluate whether to integrate their data feed.

### 4. DTE Range May Be Too Restrictive
Wang's criteria specifies 7–21 DTE, but his example output included LEAPS (1-year expiry). User suspects informed traders may deliberately use longer-dated options to avoid detection. However, extending DTE too far increases data volume significantly.

**Status:** Needs more thought. No immediate change.

### 5. Run Time Was <1 Minute (Expected 10–20 min)
User's first run completed in under a minute. Reason unclear — possibly fewer tickers returned data than expected, or Yahoo Finance was returning cached/empty chains quickly.

### 6. "8 Workers" Explanation Needed
Instructions mention "8 workers" for concurrent Yahoo Finance fetching. This refers to a ThreadPoolExecutor with 8 threads running options chain requests in parallel.

## Future Ideas (Longer Term)

- AI-generated qualitative context around output (social media, news sentiment)
- AI-assisted backtesting of scan history
- Automated weekly scheduled runs that record results and flag changes
- Portfolio overlay mode: use screener as an alert system for stocks the user already holds or is watching (security considerations first)

## Decision: Hold All Fixes Until Unusual Whales + X Integration

Rather than patching the yfinance/EDGAR version incrementally, all fixes from this feedback (ITM filter, insider/congress logic, exclusion rules, DTE range) will be implemented together when Unusual Whales and X API keys are obtained and MCP integration is built. This avoids iterating twice on a half-baked data layer.

**Trigger:** User obtains Unusual Whales API key (trial in progress as of 2026-05-05).

## Session Log

| Date | Notes |
|---|---|
| 2026-05-05 | Feedback received and saved. Decision: hold all fixes until Unusual Whales + X MCP integration. |
