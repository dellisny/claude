#!/usr/bin/env python3
"""webapp — Web interface for headlines and bets programs."""

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import feedparser
import requests
import yfinance as yf
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Dashboard")
templates = Jinja2Templates(directory="templates")

ET = ZoneInfo("America/New_York")
FETCH_TIMEOUT = 8

# ---------------------------------------------------------------------------
# Headlines
# ---------------------------------------------------------------------------

HEADLINE_SOURCES = [
    {"name": "NYT",     "label": "NYT",     "color": "#e8e8e8", "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"},
    {"name": "MKTWTCH", "label": "MKTWTCH", "color": "#00e5ff", "url": "https://feeds.marketwatch.com/marketwatch/topstories/"},
    {"name": "FT",      "label": "FT",      "color": "#ffd600", "url": "https://www.ft.com/?format=rss"},
    {"name": "REUTERS", "label": "REUTERS", "color": "#ff5252", "url": "https://feeds.reuters.com/reuters/topNews"},
    {"name": "BBC",     "label": "BBC",     "color": "#40c4ff", "url": "https://feeds.bbci.co.uk/news/rss.xml"},
    {"name": "GUARD",   "label": "GUARD",   "color": "#69f0ae", "url": "https://www.theguardian.com/world/rss"},
    {"name": "NY POST", "label": "NY POST", "color": "#ea80fc", "url": "https://nypost.com/feed/"},
    {"name": "ECONMST", "label": "ECONMST", "color": "#ff6e40", "url": "https://www.economist.com/the-world-this-week/rss.xml"},
    {"name": "AP",      "label": "AP",      "color": "#bdbdbd", "url": "https://feeds.apnews.com/rss/apf-topnews"},
]

MAX_PER_SOURCE = 6


def fetch_feed(source: dict) -> list[dict]:
    try:
        resp = requests.get(
            source["url"],
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (headlines/1.0)"},
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        stories = []
        for entry in feed.entries[:MAX_PER_SOURCE]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            stories.append({
                "source": source["name"],
                "label": source["label"],
                "color": source["color"],
                "title": title,
                "pub": pub,
                "url": entry.get("link", ""),
            })
        return stories
    except Exception:
        return []


def relative_time(pub: datetime | None) -> str:
    if pub is None:
        return ""
    now = datetime.now(timezone.utc)
    delta = int((now - pub).total_seconds())
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def fetch_all_headlines() -> list[dict]:
    all_stories = []
    with ThreadPoolExecutor(max_workers=len(HEADLINE_SOURCES)) as pool:
        futures = {pool.submit(fetch_feed, src): src for src in HEADLINE_SOURCES}
        for future in as_completed(futures):
            all_stories.extend(future.result())
    timestamped = [s for s in all_stories if s["pub"]]
    no_time = [s for s in all_stories if not s["pub"]]
    timestamped.sort(key=lambda s: s["pub"], reverse=True)
    return timestamped + no_time


def dedup_headlines(stories: list[dict], count: int, max_per_source: int = 3) -> list[dict]:
    seen_words: list[set] = []
    source_counts: dict[str, int] = {}
    selected = []
    for story in stories:
        src = story["source"]
        if source_counts.get(src, 0) >= max_per_source:
            continue
        words = set(story["title"].lower().split())
        duplicate = any(
            len(words & seen) / max(len(words | seen), 1) > 0.5
            for seen in seen_words
        )
        if not duplicate:
            selected.append(story)
            seen_words.append(words)
            source_counts[src] = source_counts.get(src, 0) + 1
        if len(selected) >= count:
            break
    return selected


# ---------------------------------------------------------------------------
# Bets
# ---------------------------------------------------------------------------

BETS_TIMEOUT = 10


def fetch_polymarket(keyword: Optional[str], limit: int) -> list[dict]:
    try:
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
            timeout=BETS_TIMEOUT,
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
                "volume": f"${vol:,.0f}/day",
                "url": f"https://polymarket.com/market/{m.get('slug', '')}",
            })
            if len(results) >= limit:
                break
        return results
    except requests.RequestException:
        return []


def fetch_manifold(keyword: Optional[str], limit: int) -> list[dict]:
    try:
        params = {
            "term": keyword or "",
            "limit": limit,
            "sort": "liquidity",
            "filter": "open",
        }
        resp = requests.get(
            "https://api.manifold.markets/v0/search-markets",
            params=params,
            timeout=BETS_TIMEOUT,
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
                "volume": f"M${liquidity:,.0f}",
                "url": m.get("url", ""),
            })
        return results
    except requests.RequestException:
        return []


def fetch_predictit(keyword: Optional[str], limit: int) -> list[dict]:
    try:
        resp = requests.get(
            "https://www.predictit.org/api/marketdata/all/",
            headers={"Accept": "application/json"},
            timeout=BETS_TIMEOUT,
        )
        resp.raise_for_status()
        all_markets = resp.json().get("markets", [])
        if keyword:
            kw = keyword.lower()
            all_markets = [m for m in all_markets if kw in m.get("name", "").lower()]
        results = []
        for m in all_markets[:limit]:
            contracts = m.get("contracts") or []
            if len(contracts) == 1:
                c = contracts[0]
                price = c.get("lastTradePrice") or c.get("bestBuyYesCost")
                prob_str = f"{price * 100:.0f}%" if price is not None else "—"
                leader = ""
            else:
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
    except requests.RequestException:
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/headlines")


@app.get("/headlines", response_class=HTMLResponse)
async def headlines_page(
    request: Request,
    q: Optional[str] = None,
    n: int = 20,
):
    stories = fetch_all_headlines()
    if q:
        kw = q.lower()
        top = [s for s in stories if kw in s["title"].lower()]
    else:
        top = dedup_headlines(stories, n)

    for s in top:
        s["age"] = relative_time(s["pub"])

    now_et = datetime.now(ET).strftime("%a %d %b %Y  %H:%M ET")
    sources_seen = len(set(s["source"] for s in top))
    return templates.TemplateResponse("headlines.html", {
        "request": request,
        "stories": top,
        "timestamp": now_et,
        "query": q or "",
        "count": n,
        "sources_seen": sources_seen,
    })


@app.get("/bets", response_class=HTMLResponse)
async def bets_page(
    request: Request,
    q: Optional[str] = None,
    n: int = 10,
):
    keyword = q or None
    limit = n

    def _fetch():
        with ThreadPoolExecutor(max_workers=3) as pool:
            pm_f = pool.submit(fetch_polymarket, keyword, limit)
            mf_f = pool.submit(fetch_manifold, keyword, limit)
            pi_f = pool.submit(fetch_predictit, keyword, limit)
            return pm_f.result(), mf_f.result(), pi_f.result()

    polymarket, manifold, predictit = _fetch()

    sources = [
        {"name": "Polymarket", "color": "#69f0ae", "results": polymarket},
        {"name": "Manifold",   "color": "#40c4ff", "results": manifold},
        {"name": "PredictIt",  "color": "#ea80fc", "results": predictit},
    ]

    return templates.TemplateResponse("bets.html", {
        "request": request,
        "sources": sources,
        "query": q or "",
        "limit": limit,
    })


# ---------------------------------------------------------------------------
# HNT
# ---------------------------------------------------------------------------

def fetch_hnt() -> dict:
    try:
        url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=helium&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
        )
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
        h = data.get("helium", {})
        return {
            "price": h.get("usd"),
            "change_24h": h.get("usd_24h_change"),
            "vol_24h": h.get("usd_24h_vol"),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/hnt", response_class=HTMLResponse)
async def hnt_page(request: Request):
    data = fetch_hnt()
    return templates.TemplateResponse("hnt.html", {"request": request, "data": data})


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------

PERIOD_MAP = {"1m": "1mo", "3m": "3mo", "6m": "6mo", "1y": "1y", "2y": "2y", "5y": "5y"}
INDEX_MAP = {
    "NMS": ("^IXIC", "NASDAQ"), "NGM": ("^IXIC", "NASDAQ"), "NCM": ("^IXIC", "NASDAQ"),
    "NYQ": ("^GSPC", "S&P 500"), "ASE": ("^GSPC", "S&P 500"),
}


def _fmt_large(v):
    if v is None: return "N/A"
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9:  return f"${v/1e9:.2f}B"
    if v >= 1e6:  return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"

def _fmt_pct(v):
    if v is None: return "N/A"
    return f"{v*100:.1f}%"

def _fmt_float(v, d=2):
    if v is None: return "N/A"
    return f"{v:.{d}f}"

def _fmt_price(v):
    if v is None: return "N/A"
    return f"${v:,.2f}"

def _div_yield(info):
    rate = info.get("dividendRate")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if rate and price and price > 0:
        return _fmt_pct(rate / price)
    raw = info.get("dividendYield")
    if raw is not None:
        return _fmt_pct(raw if raw < 1 else raw / 100)
    return "N/A"

def _price_fcf(info, cashflow):
    try:
        price = info.get("currentPrice")
        shares = info.get("sharesOutstanding")
        if cashflow is None or cashflow.empty or not price or not shares:
            return "N/A"
        def find_row(df, *keys):
            for key in keys:
                for idx in df.index:
                    if key.lower() in str(idx).lower():
                        return df.loc[idx].iloc[0]
            return None
        ocf = find_row(cashflow, "Operating Cash Flow", "Cash From Operations", "Total Cash From Operating Activities")
        capex = find_row(cashflow, "Capital Expenditure", "Capital Expenditures", "Purchase Of Property Plant And Equipment")
        if ocf is None or capex is None: return "N/A"
        fcf = ocf + capex
        if fcf <= 0: return "N/A"
        return _fmt_float(price / (fcf / shares))
    except Exception:
        return "N/A"


def _resolve_to_ticker(user_input: str) -> tuple[str, bool]:
    """Use Claude Haiku to resolve fuzzy input to a US stock ticker.

    Returns (ticker_or_original, is_definite_ticker).
    """
    try:
        client = _anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": (
                    f"What is the US stock ticker symbol for: '{user_input}'?\n"
                    "Reply with ONLY the ticker symbol (e.g. AAPL, SJM, TSLA). "
                    "If you don't know, reply with the word UNKNOWN."
                ),
            }],
        )
        ticker = resp.content[0].text.strip().upper().strip('"').strip("'").split()[0]
        if ticker and ticker != "UNKNOWN" and ticker.isalpha() and len(ticker) <= 5:
            return ticker, True
    except Exception:
        pass
    return user_input, False


def fetch_stock(query: str, period: str) -> dict:
    resolved, is_ticker = _resolve_to_ticker(query)
    interpreted_as = resolved if resolved.upper() != query.upper() else None
    equities_tail = []

    if is_ticker:
        symbol = resolved
        try:
            t = yf.Ticker(symbol)
            info = t.info
            try:    cashflow = t.cashflow
            except Exception: cashflow = None
            try:    raw_news = t.news or []
            except Exception: raw_news = []
        except Exception as e:
            return {"error": str(e)}
    else:
        try:
            results = yf.Search(resolved, max_results=5).quotes
        except Exception:
            return {"error": f"Search failed for '{query}'"}
        if not results:
            return {"error": f"No results found for '{query}'"}
        equities = [r for r in results if r.get("quoteType") == "EQUITY"] or results
        symbol = equities[0].get("symbol", "")
        equities_tail = equities[1:4]
        try:
            t = yf.Ticker(symbol)
            info = t.info
            try:    cashflow = t.cashflow
            except Exception: cashflow = None
            try:    raw_news = t.news or []
            except Exception: raw_news = []
        except Exception as e:
            return {"error": str(e)}

    index_symbol, index_label = INDEX_MAP.get(info.get("exchange", ""), ("^GSPC", "S&P 500"))
    lo52, hi52 = info.get("fiftyTwoWeekLow"), info.get("fiftyTwoWeekHigh")

    # Price history for chart
    chart = None
    try:
        data = yf.download(
            [symbol, index_symbol], period=PERIOD_MAP.get(period, "1y"),
            interval="1d", auto_adjust=True, progress=False,
        )
        if not data.empty:
            close = data["Close"]
            sp = close[symbol].dropna()
            ip = close[index_symbol].dropna()
            common = sp.index.intersection(ip.index)
            if len(common) >= 2:
                sp, ip = sp.loc[common], ip.loc[common]
                chart = {
                    "dates":  [str(d.date()) for d in common],
                    "stock":  (sp / sp.iloc[0] * 100).tolist(),
                    "index":  (ip / ip.iloc[0] * 100).tolist(),
                    "stock_label": symbol,
                    "index_label": index_label,
                }
    except Exception:
        pass

    return {
        "header": {
            "symbol":   symbol,
            "name":     info.get("longName") or info.get("shortName") or symbol,
            "sector":   info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "exchange": info.get("exchange", "N/A"),
            "currency": info.get("currency", "USD"),
        },
        "metrics": [
            ("Market Cap",    _fmt_large(info.get("marketCap"))),
            ("Price",         _fmt_price(info.get("currentPrice"))),
            ("P/E (ttm)",     _fmt_float(info.get("trailingPE"))),
            ("P/E (fwd)",     _fmt_float(info.get("forwardPE"))),
            ("EV/EBITDA",     _fmt_float(info.get("enterpriseToEbitda"))),
            ("P/FCF",         _price_fcf(info, cashflow)),
            ("Gross Margin",  _fmt_pct(info.get("grossMargins"))),
            ("Net Margin",    _fmt_pct(info.get("profitMargins"))),
            ("Revenue (TTM)", _fmt_large(info.get("totalRevenue"))),
            ("Beta",          _fmt_float(info.get("beta"))),
            ("Div Yield",     _div_yield(info)),
            ("52W Range",     f"{_fmt_price(lo52)} / {_fmt_price(hi52)}" if lo52 and hi52 else "N/A"),
        ],
        "chart": chart,
        "news": [
            {
                "title": (item.get("content") or {}).get("title") or item.get("title", ""),
                "publisher": ((item.get("content") or {}).get("provider") or {}).get("displayName") or item.get("publisher", ""),
                "date": ((item.get("content") or {}).get("pubDate") or "")[:10],
                "url": ((item.get("content") or {}).get("canonicalUrl") or {}).get("url") or item.get("link", ""),
            }
            for item in raw_news[:5]
            if (item.get("content") or {}).get("title") or item.get("title")
        ],
        "alternatives": [
            {"symbol": r.get("symbol", ""), "name": r.get("longname") or r.get("shortname", "")}
            for r in equities_tail
        ],
        "period": period,
        "interpreted_as": interpreted_as,
    }


@app.get("/stock", response_class=HTMLResponse)
async def stock_page(request: Request, q: Optional[str] = None, period: str = "1y"):
    result = fetch_stock(q, period) if q else None
    return templates.TemplateResponse("stock.html", {
        "request": request,
        "query": q or "",
        "result": result,
        "period": period,
        "periods": ["1m", "3m", "6m", "1y", "2y", "5y"],
    })


# ---------------------------------------------------------------------------
# BTree
# ---------------------------------------------------------------------------

BTREE_FILE = os.path.expanduser("~/.btree")


def btree_load() -> list[int]:
    try:
        content = open(BTREE_FILE).read().strip()
        return sorted(set(int(x) for x in content.split())) if content else []
    except FileNotFoundError:
        return []


def btree_save(vals: list[int]):
    with open(BTREE_FILE, "w") as f:
        if vals:
            f.write(" ".join(str(v) for v in vals) + "\n")


class _BNode:
    __slots__ = ("val", "left", "right", "x", "y")
    def __init__(self, val, left=None, right=None):
        self.val, self.left, self.right = val, left, right
        self.x = self.y = 0


def _build(vals: list[int]) -> Optional[_BNode]:
    if not vals: return None
    mid = len(vals) // 2
    return _BNode(vals[mid], _build(vals[:mid]), _build(vals[mid+1:]))


def _assign_pos(node, depth=0, counter=None):
    if counter is None: counter = [0]
    if node is None: return
    _assign_pos(node.left,  depth + 1, counter)
    node.x, node.y = counter[0], depth
    counter[0] += 1
    _assign_pos(node.right, depth + 1, counter)


def btree_to_svg(root: Optional[_BNode]) -> Optional[str]:
    if root is None: return None
    _assign_pos(root)

    nodes: list[_BNode] = []
    def collect(n):
        if n is None: return
        nodes.append(n); collect(n.left); collect(n.right)
    collect(root)

    R, HG, VG, M = 22, 52, 64, 40
    W = (max(n.x for n in nodes) + 1) * HG + 2 * M
    H = (max(n.y for n in nodes) + 1) * VG + 2 * M

    def cx(n): return M + n.x * HG
    def cy(n): return M + n.y * VG

    parts = []
    for n in nodes:
        for child in (n.left, n.right):
            if child:
                parts.append(f'<line x1="{cx(n)}" y1="{cy(n)}" x2="{cx(child)}" y2="{cy(child)}" stroke="#333" stroke-width="1.5"/>')
    for n in nodes:
        fs = 11 if len(str(n.val)) <= 3 else 9
        parts.append(f'<circle cx="{cx(n)}" cy="{cy(n)}" r="{R}" fill="#111" stroke="#ffd600" stroke-width="1.5"/>')
        parts.append(f'<text x="{cx(n)}" y="{cy(n)}" text-anchor="middle" dominant-baseline="central" fill="#ffd600" font-family="monospace" font-size="{fs}">{n.val}</text>')

    return f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'


@app.get("/btree", response_class=HTMLResponse)
async def btree_get(request: Request, error: Optional[str] = None):
    vals = btree_load()
    svg = btree_to_svg(_build(vals))
    return templates.TemplateResponse("btree.html", {
        "request": request, "vals": vals, "svg": svg, "error": error,
    })


@app.post("/btree", response_class=RedirectResponse)
async def btree_post(value: str = Form(...)):
    try:
        v = int(value.strip())
    except ValueError:
        return RedirectResponse(url="/btree?error=Not+a+valid+integer", status_code=303)
    vals = btree_load()
    if v not in vals:
        if len(vals) >= 100:
            return RedirectResponse(url="/btree?error=Tree+is+full+(max+100)", status_code=303)
        vals.append(v)
        vals.sort()
        btree_save(vals)
    return RedirectResponse(url="/btree", status_code=303)


@app.post("/btree/reset", response_class=RedirectResponse)
async def btree_reset():
    btree_save([])
    return RedirectResponse(url="/btree", status_code=303)


@app.get("/robotwar", response_class=HTMLResponse)
async def robotwar_page(request: Request):
    return templates.TemplateResponse("robotwar.html", {"request": request})


SHADE_FILE = os.path.expanduser("~/.shade_outings.json")


def shade_load() -> list[dict]:
    try:
        return json.loads(open(SHADE_FILE).read())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def shade_save(outings: list[dict]):
    with open(SHADE_FILE, "w") as f:
        json.dump(outings, f)


@app.get("/shade", response_class=HTMLResponse)
async def shade_page(request: Request):
    return templates.TemplateResponse("shade.html", {"request": request, "active": "shade"})


@app.get("/shade/outings")
async def shade_get_outings():
    return shade_load()


@app.post("/shade/outings")
async def shade_add_outing(request: Request):
    outing = await request.json()
    outings = shade_load()
    outings.insert(0, outing)
    shade_save(outings)
    return outing


@app.delete("/shade/outings/{outing_id}")
async def shade_delete_outing(outing_id: int):
    outings = shade_load()
    outings = [o for o in outings if o.get("id") != outing_id]
    shade_save(outings)
    return {"ok": True}


@app.delete("/shade/outings")
async def shade_clear_outings():
    shade_save([])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Twenty Questions
# ---------------------------------------------------------------------------

import anthropic as _anthropic

_TQ_MAX = 20
_TQ_SYSTEM = """\
You are playing 20 Questions. The human has secretly chosen something — it could be \
an animal, vegetable, mineral, a specific person, a place, an abstract concept, or \
anything else.

Your goal is to identify it by asking strategic yes/no questions, then guess.

Strategy:
- Start broad to establish category (living/non-living, natural/man-made, etc.)
- Use answers to binary-search down rapidly
- Never repeat information already established
- When confidence is high (roughly 85%+), stop asking and guess
- You may guess before using all questions — do so as soon as you're confident

Respond with ONLY a JSON object — no other text, no markdown fences.

To ask a question:
{"action": "ask", "question": "Is it a living thing?"}

To make a guess:
{"action": "guess", "guess": "a grand piano", "reasoning": "It's large, man-made, found indoors, makes music, and has black and white keys."}

If you've used all your questions, always respond with a guess, never a question.\
"""

_tq_game: dict = {
    "status": "idle",  # idle | asking | guessed | won | lost
    "history": [],
    "question": None,
    "guess": None,
    "reasoning": None,
    "q_num": 0,
    "reveal": "",
}


def _tq_reset():
    _tq_game.update({
        "status": "idle", "history": [], "question": None,
        "guess": None, "reasoning": None, "q_num": 0, "reveal": "",
    })


def _tq_call_claude(history: list[dict], questions_left: int, attempt: int = 0) -> dict:
    import re, time as _time
    client = _anthropic.Anthropic()
    if not history:
        user_msg = f"I've thought of something. You have {_TQ_MAX} questions. Ask your first question."
    else:
        lines = [f"Q{i}: {h['question']} → {h['answer']}" for i, h in enumerate(history, 1)]
        summary = "\n".join(lines)
        if questions_left == 0:
            user_msg = f"Here is everything we know:\n{summary}\n\nYou have no questions left. Make your best guess now."
        else:
            user_msg = f"Here is everything we know:\n{summary}\n\nYou have {questions_left} question(s) left. What is your next move?"

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=_TQ_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = resp.content[0].text.strip()

    def parse(t):
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
        stripped = re.sub(r"^```(?:json)?\s*", "", t)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*?\}", t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"No valid JSON: {t!r}")

    try:
        return parse(text)
    except ValueError:
        if attempt < 2:
            _time.sleep(1)
            return _tq_call_claude(history, questions_left, attempt + 1)
        if questions_left == 0:
            return {"action": "guess", "guess": "I'm not sure", "reasoning": ""}
        return {"action": "ask", "question": "Is it something you can physically touch?"}


def _tq_state():
    return {k: _tq_game[k] for k in ("status", "history", "question", "guess", "reasoning", "q_num", "reveal")}


@app.get("/twenty", response_class=HTMLResponse)
async def twenty_page(request: Request):
    return templates.TemplateResponse("twenty.html", {"request": request, "active": "twenty"})


@app.post("/twenty/start")
async def twenty_start():
    _tq_reset()
    _tq_game["status"] = "asking"
    _tq_game["q_num"] = 1
    move = _tq_call_claude([], _TQ_MAX)
    _tq_game["question"] = move.get("question", "Is it a living thing?")
    return _tq_state()


@app.post("/twenty/answer")
async def twenty_answer(request: Request):
    body = await request.json()
    answer = (body.get("answer") or "").strip()
    if not answer or _tq_game["status"] != "asking":
        return {"error": "invalid state"}
    _tq_game["history"].append({"question": _tq_game["question"], "answer": answer})
    questions_left = _TQ_MAX - _tq_game["q_num"]
    if questions_left <= 0:
        move = _tq_call_claude(_tq_game["history"], 0)
        _tq_game["status"] = "guessed"
        _tq_game["guess"] = move.get("guess", "I'm not sure")
        _tq_game["reasoning"] = move.get("reasoning", "")
    else:
        move = _tq_call_claude(_tq_game["history"], questions_left)
        if move.get("action") == "guess":
            _tq_game["status"] = "guessed"
            _tq_game["guess"] = move.get("guess", "I'm not sure")
            _tq_game["reasoning"] = move.get("reasoning", "")
        else:
            _tq_game["q_num"] += 1
            _tq_game["question"] = move.get("question", "Is it man-made?")
    return _tq_state()


@app.post("/twenty/confirm")
async def twenty_confirm(request: Request):
    body = await request.json()
    correct = body.get("correct", False)
    _tq_game["status"] = "won" if correct else "lost"
    _tq_game["reveal"] = body.get("reveal", "")
    return _tq_state()


@app.post("/twenty/reset")
async def twenty_reset():
    _tq_reset()
    return _tq_state()


# ---------------------------------------------------------------------------
# Mastermind
# ---------------------------------------------------------------------------

import random as _random

_MM_PEGS   = 4
_MM_COLORS = 6
_MM_MAX    = 12


def _mm_score(guess: tuple, secret: tuple) -> tuple:
    black = sum(g == s for g, s in zip(guess, secret))
    white = sum(min(guess.count(c), secret.count(c)) for c in range(1, _MM_COLORS + 1)) - black
    return black, white


_mm_game: dict = {
    "status":  "idle",   # idle | playing | won | lost
    "secret":  None,
    "guesses": [],       # [{guess, black, white}]
}


def _mm_reset():
    _mm_game.update({"status": "idle", "secret": None, "guesses": []})


def _mm_state() -> dict:
    return {
        "status":  _mm_game["status"],
        "guesses": _mm_game["guesses"],
        "secret":  list(_mm_game["secret"]) if _mm_game["secret"] and _mm_game["status"] in ("won", "lost") else None,
        "max":     _MM_MAX,
    }


@app.get("/mastermind", response_class=HTMLResponse)
async def mastermind_page(request: Request):
    return templates.TemplateResponse("mastermind.html", {"request": request, "active": "mastermind"})


@app.post("/mastermind/start")
async def mastermind_start():
    _mm_reset()
    _mm_game["secret"] = tuple(_random.randint(1, _MM_COLORS) for _ in range(_MM_PEGS))
    _mm_game["status"] = "playing"
    return _mm_state()


@app.post("/mastermind/guess")
async def mastermind_guess(request: Request):
    body  = await request.json()
    guess = body.get("guess", [])
    if _mm_game["status"] != "playing":
        return _mm_state()
    if len(guess) != _MM_PEGS or not all(1 <= c <= _MM_COLORS for c in guess):
        return {"error": "invalid guess"}
    gt = tuple(guess)
    black, white = _mm_score(gt, _mm_game["secret"])
    _mm_game["guesses"].append({"guess": list(gt), "black": black, "white": white})
    if black == _MM_PEGS:
        _mm_game["status"] = "won"
    elif len(_mm_game["guesses"]) >= _MM_MAX:
        _mm_game["status"] = "lost"
    return _mm_state()


@app.post("/mastermind/reset")
async def mastermind_reset():
    _mm_reset()
    return _mm_state()
