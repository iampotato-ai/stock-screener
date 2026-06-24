import sys
sys.path.insert(0, 'C:/Users/91996/Documents/My Projects/stock-screener')

import logging
import time
from typing import List

import yfinance as yf

from app.database import execute_query, fetch_all

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
INR_PER_USD = 83.0               # approximate conversion rate
CAP_THRESHOLD_INR = 10_000_000_000  # 10 B INR
RATE_LIMIT_SECONDS = 0.6           # ~1.6 req/s to stay safe with Yahoo

# ----------------------------------------------------------------------
# Helper: fetch market cap from Yahoo Finance
# ----------------------------------------------------------------------
def get_market_cap_inr(ticker: str) -> int | None:
    """Return the market cap in INR for *ticker* or None on failure."""
    try:
        # Yahoo Finance uses .NS suffix for NSE stocks
        yahoo_ticker = f"{ticker}.NS"
        info = yf.Ticker(yahoo_ticker).info
        cap_usd = info.get('marketCap')
        if cap_usd is None:
            return None
        return int(cap_usd * INR_PER_USD)
    except Exception as exc:
        logging.debug(f"Yahoo fetch failed for {ticker}: {exc}")
        return None

# ----------------------------------------------------------------------
# Main routine – bulk load into nse_symbols table
# ----------------------------------------------------------------------
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    # A small static list for demonstration – replace with a full NSE list as needed.
    fallback = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR",
        "ICICIBANK", "KOTAKBANK", "AXISBANK", "ITC", "LT",
        # ... add more tickers or load from an external CSV ...
    ]

    logging.info(f"Fetching market cap for {len(fallback)} tickers (threshold ≥ {CAP_THRESHOLD_INR/1e9:.0f} B INR)")
    inserted = 0
    for ticker in fallback:
        cap = get_market_cap_inr(ticker)
        time.sleep(RATE_LIMIT_SECONDS)
        if cap is None:
            logging.debug(f"Skipping {ticker}: no cap info")
            continue
        if cap >= CAP_THRESHOLD_INR:
            execute_query(
                "INSERT OR REPLACE INTO nse_symbols (ticker, market_cap_inr) VALUES (?, ?)",
                (ticker, cap),
                commit=True,
            )
            inserted += 1
            logging.info(f"✔ {ticker} – market cap ≈ {cap/1e9:.2f} B INR")
        else:
            logging.debug(f"✗ {ticker} – cap {cap/1e9:.2f} B INR (below threshold)")

    logging.info(f"Done. Inserted/updated {inserted} symbols into nse_symbols.")

if __name__ == "__main__":
    main()
