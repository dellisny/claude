import asyncio
import json
import os
import sqlite3
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(_DIR, "templates"))

# --- DB ---

_DB = os.path.join(_DIR, "data", "whale_old.db")
_SCAN_STATE: dict = {}
_CACHE: dict = {}
_CACHE_TTL = 3600


def _conn():
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    return c


def _init():
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS hpl_scans (
            id TEXT PRIMARY KEY, created_at TEXT, status TEXT,
            total_tickers INTEGER, processed_tickers INTEGER DEFAULT 0,
            current_ticker TEXT, error TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS hpl_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id TEXT,
            ticker TEXT, contract_symbol TEXT, option_type TEXT,
            strike REAL, expiry TEXT, dte INTEGER,
            volume INTEGER, open_interest INTEGER, vol_oi_ratio REAL,
            premium REAL, last_price REAL, implied_volatility REAL,
            in_the_money INTEGER, is_golden_sweep INTEGER,
            is_strong_vol_oi INTEGER, near_earnings INTEGER,
            is_index_etf INTEGER, conviction_score REAL,
            flags TEXT, insider_trades TEXT, congress_trades TEXT,
            FOREIGN KEY (scan_id) REFERENCES hpl_scans(id))""")


_init()

# --- Ticker universe ---

_INDEX_ETFS = {
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO', 'IVV', 'GLD', 'SLV',
    'TLT', 'HYG', 'LQD', 'VXX', 'UVXY', 'SQQQ', 'TQQQ', 'XLF', 'XLK',
    'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE',
}

_FALLBACK_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'BRK-B', 'UNH', 'JPM',
    'V', 'XOM', 'LLY', 'JNJ', 'MA', 'PG', 'HD', 'MRK', 'AVGO', 'CVX',
    'ABBV', 'PEP', 'COST', 'KO', 'BAC', 'WMT', 'MCD', 'CRM', 'NFLX', 'AMD',
    'TMO', 'ACN', 'LIN', 'DHR', 'ADBE', 'TXN', 'PM', 'CSCO', 'NKE', 'DIS',
    'INTU', 'WFC', 'NEE', 'COP', 'UPS', 'MS', 'AMGN', 'SPGI', 'RTX', 'GS',
    'BLK', 'HON', 'SYK', 'ISRG', 'PFE', 'AXP', 'T', 'BKNG', 'CAT', 'SCHW',
    'GILD', 'SBUX', 'BA', 'BMY', 'MDLZ', 'C', 'PLD', 'AMAT', 'PANW', 'ADI',
    'MU', 'GE', 'DE', 'CB', 'MMC', 'ZTS', 'LRCX', 'VRTX', 'REGN', 'CI',
    'TJX', 'SLB', 'EOG', 'MCO', 'USB', 'FI', 'SO', 'DUK', 'ITW', 'PGR',
    'NOC', 'LMT', 'GD', 'ADP', 'CSX', 'HCA', 'ELV', 'CME', 'AON', 'PSA',
]


def _get_tickers() -> list:
    try:
        df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        return df['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception:
        return _FALLBACK_TICKERS


# --- Options screener ---

_MIN_VOL_OI = 2.0
_MIN_PREMIUM = 250_000
_MIN_DTE = 7
_MAX_DTE = 21


def _scan_ticker(symbol: str) -> list:
    signals = []
    try:
        t = yf.Ticker(symbol)
        today = datetime.now().date()
        is_etf = symbol in _INDEX_ETFS
        near_earnings = False
        try:
            ts = t.info.get('earningsTimestamp') or t.info.get('earningsTimestampStart')
            if ts:
                ed = datetime.fromtimestamp(ts).date()
                near_earnings = 0 <= (ed - today).days <= 3
        except Exception:
            pass
        if not t.options:
            return signals
        for expiry in t.options:
            exp = datetime.strptime(expiry, '%Y-%m-%d').date()
            dte = (exp - today).days
            if not (_MIN_DTE <= dte <= _MAX_DTE):
                continue
            try:
                chain = t.option_chain(expiry)
            except Exception:
                continue
            for df, opt_type in [(chain.calls, 'call'), (chain.puts, 'put')]:
                for _, row in df.iterrows():
                    vol = int(row.get('volume', 0) or 0)
                    oi = int(row.get('openInterest', 0) or 0)
                    if vol <= 0 or oi <= 0:
                        continue
                    vol_oi = vol / oi
                    if vol_oi < _MIN_VOL_OI:
                        continue
                    last = float(row.get('lastPrice', 0) or 0)
                    ask = float(row.get('ask', 0) or 0)
                    price = last if last > 0 else ask
                    premium = vol * price * 100
                    if premium < _MIN_PREMIUM:
                        continue
                    signals.append({
                        'ticker': symbol,
                        'contract_symbol': str(row.get('contractSymbol', '')),
                        'option_type': opt_type,
                        'strike': float(row.get('strike', 0)),
                        'expiry': expiry,
                        'dte': dte,
                        'volume': vol,
                        'open_interest': oi,
                        'vol_oi_ratio': round(vol_oi, 2),
                        'premium': premium,
                        'last_price': last,
                        'implied_volatility': float(row.get('impliedVolatility', 0) or 0),
                        'in_the_money': bool(row.get('inTheMoney', False)),
                        'is_golden_sweep': premium >= 1_000_000,
                        'is_strong_vol_oi': vol_oi >= 5.0,
                        'near_earnings': near_earnings,
                        'is_index_etf': is_etf,
                        'conviction_score': 0.0,
                        'flags': [],
                        'insider_trades': [],
                        'congress_trades': [],
                    })
    except Exception:
        pass
    return signals


# --- Insider trades (SEC EDGAR) ---

_EDGAR_HEADERS = {"User-Agent": "Whale-Old Options Screener dellis@pobox.com"}


def _load_cik_map() -> dict:
    cached = _CACHE.get('cik_map')
    if cached and (time.time() - cached['ts']) < 86400:
        return cached['data']
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers=_EDGAR_HEADERS, timeout=15)
        data = {v['ticker'].upper(): str(v['cik_str']) for v in r.json().values()}
        _CACHE['cik_map'] = {'data': data, 'ts': time.time()}
        return data
    except Exception:
        return {}


def _parse_form4_xml(cik_int: int, accession_nodash: str, primary_doc: str, filing_date: str) -> list:
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{primary_doc}"
    try:
        r = requests.get(url, headers=_EDGAR_HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        name = root.findtext('.//rptOwnerName') or 'Unknown'
        title = root.findtext('.//officerTitle') or ''
        trades = []
        for tx in root.findall('.//nonDerivativeTransaction'):
            code = tx.findtext('.//transactionAcquiredDisposedCode/value') or ''
            if code not in ('A', 'D'):
                continue
            shares_str = tx.findtext('.//transactionShares/value') or '0'
            price_str = tx.findtext('.//transactionPricePerShare/value') or '0'
            tx_date = tx.findtext('.//transactionDate/value') or filing_date
            trades.append({
                'date': tx_date,
                'name': name,
                'title': title,
                'transaction_type': 'buy' if code == 'A' else 'sell',
                'shares': int(float(shares_str)),
                'price': float(price_str),
            })
        return trades
    except Exception:
        return []


def _get_insider_trades(ticker: str, days: int = 30) -> list:
    cik_map = _load_cik_map()
    cik = cik_map.get(ticker.upper())
    if not cik:
        return []
    try:
        cik_padded = cik.zfill(10)
        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik_padded}.json",
                         headers=_EDGAR_HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        recent = data.get('filings', {}).get('recent', {})
        form_types = recent.get('form', [])
        dates = recent.get('filingDate', [])
        accessions = recent.get('accessionNumber', [])
        primary_docs = recent.get('primaryDocument', [])
        cutoff = (datetime.now() - timedelta(days=days)).date()
        trades = []
        for i, ft in enumerate(form_types):
            if ft not in ('4', '4/A'):
                continue
            fd = datetime.strptime(dates[i], '%Y-%m-%d').date()
            if fd < cutoff:
                break
            if i < len(primary_docs) and primary_docs[i]:
                accession_nodash = accessions[i].replace('-', '')
                trades.extend(_parse_form4_xml(int(cik), accession_nodash, primary_docs[i], dates[i]))
            if len(trades) >= 10:
                break
        return trades[:10]
    except Exception:
        return []


# --- Congressional trades ---

def _load_congress_trades() -> list:
    cached = _CACHE.get('congress_trades')
    if cached and (time.time() - cached['ts']) < _CACHE_TTL:
        return cached['data']
    trades = []
    for url, chamber, name_key in [
        ("https://house-stock-watcher.com/api/all_transactions.json", "house", "representative"),
        ("https://senate-stock-watcher.com/api/all_transactions.json", "senate", "senator"),
    ]:
        try:
            r = requests.get(url, timeout=30)
            for t in r.json():
                tx = t.get('type', '').lower()
                trades.append({
                    'ticker': t.get('ticker', '').upper().strip(),
                    'representative': t.get(name_key, t.get('representative', '')),
                    'party': t.get('party', ''),
                    'transaction_type': 'purchase' if 'purchase' in tx else 'sale',
                    'amount': t.get('amount', ''),
                    'date': t.get('transaction_date', ''),
                    'chamber': chamber,
                })
        except Exception:
            pass
    _CACHE['congress_trades'] = {'data': trades, 'ts': time.time()}
    return trades


def _get_congress_trades(ticker: str, days: int = 60) -> list:
    cutoff = (datetime.now() - timedelta(days=days)).date()
    result = []
    for t in _load_congress_trades():
        if t.get('ticker') != ticker.upper():
            continue
        try:
            if datetime.strptime(t['date'][:10], '%Y-%m-%d').date() >= cutoff:
                result.append(t)
        except Exception:
            continue
    return result


# --- Scoring ---

def _score(signal: dict) -> float:
    score = 0.0
    flags = []
    opt = signal['option_type']
    if signal['insider_trades']:
        dirs = [t['transaction_type'] for t in signal['insider_trades']]
        if (opt == 'call' and 'buy' in dirs) or (opt == 'put' and 'sell' in dirs):
            score += 2.0
            flags.append('insider_corroboration')
    if signal['congress_trades']:
        dirs = [t['transaction_type'] for t in signal['congress_trades']]
        if (opt == 'call' and 'purchase' in dirs) or (opt == 'put' and 'sale' in dirs):
            score += 2.0
            flags.append('congressional_corroboration')
    if signal['is_strong_vol_oi']:
        score += 2.0
        flags.append('strong_vol_oi_5x')
    if signal['is_golden_sweep']:
        score += 2.0
        flags.append('golden_sweep_1m')
    if signal['vol_oi_ratio'] >= 2.0:
        score += 1.0
        flags.append('elevated_vol_oi_2x')
    if not signal['in_the_money']:
        score += 1.0
        flags.append('out_of_money')
    if signal['dte'] <= 14:
        score += 1.0
        flags.append('short_dte')
    if signal['premium'] >= 500_000:
        score += 1.0
        flags.append('large_premium_500k')
    if signal['near_earnings']:
        score -= 1.0
        flags.append('near_earnings_risk')
    if signal['is_index_etf']:
        score -= 2.0
        flags.append('index_etf_noise')
    signal['flags'] = flags
    signal['conviction_score'] = max(0.0, min(10.0, score))
    return signal['conviction_score']


# --- Scan orchestration ---

def _run_scan(scan_id: str):
    tickers = _get_tickers()
    total = len(tickers)
    _SCAN_STATE[scan_id] = {
        'status': 'scanning', 'total': total, 'processed': 0,
        'current_ticker': '', 'signals_found': 0,
    }
    with _conn() as c:
        c.execute("UPDATE hpl_scans SET total_tickers=? WHERE id=?", (total, scan_id))
    all_signals = []
    processed = 0
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(_scan_ticker, t): t for t in tickers}
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    all_signals.extend(future.result(timeout=30))
                except Exception:
                    pass
                processed += 1
                _SCAN_STATE[scan_id].update({
                    'processed': processed,
                    'current_ticker': ticker,
                    'signals_found': len(all_signals),
                })
                with _conn() as c:
                    c.execute(
                        "UPDATE hpl_scans SET processed_tickers=?, current_ticker=? WHERE id=?",
                        (processed, ticker, scan_id)
                    )
        _SCAN_STATE[scan_id]['status'] = 'enriching'
        with _conn() as c:
            c.execute("UPDATE hpl_scans SET status='enriching' WHERE id=?", (scan_id,))
        unique = list({s['ticker'] for s in all_signals})
        for i, ticker in enumerate(unique):
            insider = _get_insider_trades(ticker)
            congress = _get_congress_trades(ticker)
            for s in all_signals:
                if s['ticker'] == ticker:
                    s['insider_trades'] = insider
                    s['congress_trades'] = congress
            _SCAN_STATE[scan_id]['enrich_progress'] = f"{i+1}/{len(unique)}"
        for s in all_signals:
            _score(s)
        all_signals.sort(key=lambda s: s['conviction_score'], reverse=True)
        with _conn() as c:
            for s in all_signals:
                c.execute("""INSERT INTO hpl_signals (
                    scan_id, ticker, contract_symbol, option_type, strike, expiry, dte,
                    volume, open_interest, vol_oi_ratio, premium, last_price,
                    implied_volatility, in_the_money, is_golden_sweep, is_strong_vol_oi,
                    near_earnings, is_index_etf, conviction_score,
                    flags, insider_trades, congress_trades
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    scan_id, s['ticker'], s['contract_symbol'], s['option_type'],
                    s['strike'], s['expiry'], s['dte'], s['volume'], s['open_interest'],
                    s['vol_oi_ratio'], s['premium'], s['last_price'],
                    s['implied_volatility'], int(s['in_the_money']),
                    int(s['is_golden_sweep']), int(s['is_strong_vol_oi']),
                    int(s['near_earnings']), int(s['is_index_etf']), s['conviction_score'],
                    json.dumps(s['flags']), json.dumps(s['insider_trades']),
                    json.dumps(s['congress_trades']),
                ))
            c.execute("UPDATE hpl_scans SET status='complete' WHERE id=?", (scan_id,))
        _SCAN_STATE[scan_id].update({'status': 'complete', 'signals_found': len(all_signals)})
    except Exception as e:
        with _conn() as c:
            c.execute("UPDATE hpl_scans SET status='error', error=? WHERE id=?", (str(e), scan_id))
        _SCAN_STATE[scan_id].update({'status': 'error', 'error': str(e)})


# --- Routes ---

@app.get("/whale-old", response_class=HTMLResponse)
async def whale_old_page(request: Request):
    with _conn() as c:
        scans = [dict(r) for r in c.execute(
            "SELECT id, created_at, status, total_tickers, processed_tickers "
            "FROM hpl_scans ORDER BY created_at DESC LIMIT 20"
        ).fetchall()]
    return templates.TemplateResponse("whale_old.html", {
        "request": request, "scans": scans,
    })


@app.post("/whale-old/scan")
async def start_scan():
    scan_id = uuid.uuid4().hex[:8]
    with _conn() as c:
        c.execute(
            "INSERT INTO hpl_scans (id, created_at, status, total_tickers) VALUES (?,?,?,?)",
            (scan_id, datetime.utcnow().isoformat(), 'scanning', 0)
        )
    threading.Thread(target=_run_scan, args=(scan_id,), daemon=True).start()
    return JSONResponse({"scan_id": scan_id})


@app.get("/whale-old/scan/{scan_id}/progress")
async def scan_progress(scan_id: str):
    async def generate():
        while True:
            with _conn() as c:
                row = c.execute("SELECT * FROM hpl_scans WHERE id=?", (scan_id,)).fetchone()
                if not row:
                    yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                    break
                d = dict(row)
                sig_count = c.execute(
                    "SELECT COUNT(*) FROM hpl_signals WHERE scan_id=?", (scan_id,)
                ).fetchone()[0]
            payload = {
                'status': d['status'],
                'processed': d['processed_tickers'],
                'total': d['total_tickers'],
                'current_ticker': d['current_ticker'] or '',
                'signals_found': sig_count,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if d['status'] in ('complete', 'error'):
                break
            await asyncio.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/whale-old/scan/{scan_id}/results")
async def scan_results(scan_id: str):
    with _conn() as c:
        scan = c.execute("SELECT * FROM hpl_scans WHERE id=?", (scan_id,)).fetchone()
        if not scan:
            return JSONResponse(status_code=404, content={"error": "Not found"})
        signals = c.execute(
            "SELECT * FROM hpl_signals WHERE scan_id=? ORDER BY conviction_score DESC",
            (scan_id,)
        ).fetchall()
    result = dict(scan)
    result['signals'] = []
    for s in signals:
        sd = dict(s)
        sd['flags'] = json.loads(sd['flags'])
        sd['insider_trades'] = json.loads(sd['insider_trades'])
        sd['congress_trades'] = json.loads(sd['congress_trades'])
        result['signals'].append(sd)
    return JSONResponse(result)
