"""
fx_utils.py — Live FX rate helpers.
Caches the USD/INR rate for 30 minutes to avoid hammering Yahoo Finance.
"""
import time
import urllib.request
import json

_fx_cache: dict = {}
_FX_TTL = 30 * 60          # 30-minute cache TTL
_FALLBACK_USD_INR = 90.0   # conservative fallback if fetch fails


def fetch_usd_inr_rate() -> float:
    """
    Returns the live USD/INR exchange rate from Yahoo Finance (USDINR=X).
    Result is cached for 30 minutes. Falls back to _FALLBACK_USD_INR on error.
    """
    cache_key = 'USDINR'
    now = time.time()
    entry = _fx_cache.get(cache_key)
    if entry and (now - entry[0]) < _FX_TTL:
        return entry[1]

    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X?interval=1d&range=1d'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))

        result = data['chart']['result'][0]
        rate = float(
            result['meta'].get('regularMarketPrice') or
            result['indicators']['quote'][0]['close'][-1]
        )
        if rate and rate > 0:
            _fx_cache[cache_key] = (now, rate)
            print(f'[FX] Live USD/INR rate: {rate:.4f}')
            return rate
    except Exception as e:
        print(f'[FX] Fetch failed: {e} — using fallback {_FALLBACK_USD_INR}')

    if entry:
        print(f'[FX] Using stale cached USD/INR: {entry[1]:.4f}')
        return entry[1]
    return _FALLBACK_USD_INR
