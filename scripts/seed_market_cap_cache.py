"""
One-time script to seed market_cap_cache from NSE EQUITY_L.csv.
Run from project root: python scripts/seed_market_cap_cache.py
"""
import sys
import os
import csv
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
CSV_PATH    = os.path.join(os.path.dirname(__file__), '..', 'EQUITY_L.csv')
INR_PER_USD = 83.0
BATCH_SIZE  = 50    # symbols per batch
BATCH_SLEEP = 2     # seconds between batches
# ─────────────────────────────────────────────────────────────────────────────


def main():
    import yfinance as yf
    from app import create_app
    from app.database import execute_query

    app = create_app()

    # Read EQ-series symbols from CSV
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        symbols = [
            row['SYMBOL'].strip()
            for row in reader
            if row.get(' SERIES', row.get('SERIES', '')).strip() == 'EQ'
        ]

    logger.info(f"Total EQ symbols to process: {len(symbols)}")
    sys.stdout.flush()

    with app.app_context():
        execute_query("DELETE FROM market_cap_cache", commit=True)
        logger.info("Cleared existing market_cap_cache. Starting fetch...")
        sys.stdout.flush()

        inserted = 0
        skipped  = 0
        total    = len(symbols)

        for batch_start in range(0, total, BATCH_SIZE):
            batch = symbols[batch_start: batch_start + BATCH_SIZE]

            for sym in batch:
                try:
                    fast = yf.Ticker(f"{sym}.NS").fast_info
                    cap  = getattr(fast, 'market_cap', None)
                    if cap and cap > 0:
                        execute_query(
                            "INSERT OR REPLACE INTO market_cap_cache "
                            "(ticker, market_cap_inr, fetched_at) "
                            "VALUES (?, ?, datetime('now'))",
                            (sym, int(cap)),
                            commit=True
                        )
                        inserted += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.debug(f"Skip {sym}: {e}")
                    skipped += 1

            done = min(batch_start + BATCH_SIZE, total)
            logger.info(
                f"Progress: {done}/{total} | "
                f"Inserted: {inserted} | Skipped: {skipped}"
            )
            sys.stdout.flush()
            time.sleep(BATCH_SLEEP)

        logger.info(f"✅ Done. Inserted: {inserted} | Skipped: {skipped}")
        sys.stdout.flush()


if __name__ == '__main__':
    main()