#!/usr/bin/env python
"""
Universe-wide historical backfill script.
Runs the historical EP detection algorithm over the universe of stocks,
reusing the local daily_bars cache to prevent yfinance rate-limiting.

Usage examples:
  # Full NSE universe backfill (all symbols in daily_bars + watchlist)
  python scripts/run_universe_backfill.py

  # Bull Snort universe: NSE symbols with mktcap >= 10B INR (default filter)
  python scripts/run_universe_backfill.py --mktcap-filter

  # Specific symbols only
  python scripts/run_universe_backfill.py --symbols RELIANCE,TCS,INFY

  # Custom date range
  python scripts/run_universe_backfill.py --start-date 2024-01-01 --end-date 2026-07-27
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

# Insert workspace root to allow local module imports
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, basedir)


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    two_years_ago = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    parser = argparse.ArgumentParser(description="Universe-wide Historical EP / daily_bars Backfill")
    parser.add_argument(
        "--start-date",
        type=str,
        default="2019-01-01",
        help=f"Start date for backfill in YYYY-MM-DD format (default: 2019-01-01)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=today,
        help=f"End date for backfill in YYYY-MM-DD format (default: today = {today})"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Optional comma-separated list of symbols to backfill. Ignored if --mktcap-filter is set."
    )
    parser.add_argument(
        "--mktcap-filter",
        action="store_true",
        default=False,
        help=(
            "Screen symbols from market_cap_cache with mktcap >= 10B INR "
            "(same filter used by Bull Snort GET /api/v1/bull_snort/screen). "
            "Use this to do a full Bull Snort universe refresh."
        )
    )
    args = parser.parse_args()

    # Resolve symbol list
    from app import create_app
    app = create_app()

    symbols_list = None
    with app.app_context():
        if args.mktcap_filter:
            from app.database import get_nse_symbols_by_marketcap
            symbols_list = get_nse_symbols_by_marketcap(min_marketcap_inr=10_000_000_000)
            print(f"[*] Market cap filter applied: {len(symbols_list)} symbols (>= 10B INR / >= 1000 Cr)")
        elif args.symbols:
            symbols_list = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
            print(f"[*] Target symbols: {', '.join(symbols_list)}")
        else:
            print("[*] Target: Entire database universe (symbols in daily_bars + watchlist + IPO listings)")

    print(f"[*] Starting universe backfill from {args.start_date} to {args.end_date}...")

    # Import backfill runner from app
    from app.api.v1.legacy_routes import run_historical_backfill, ep_backtest_prep_status

    try:
        with app.app_context():
            run_historical_backfill(
                symbols=symbols_list,
                start_date=args.start_date,
                end_date=args.end_date
            )
        print("[+] Backfill completed successfully.")
        status = ep_backtest_prep_status
        print(f"    - Total processed: {status.get('processed', 0)}")
        if status.get('error'):
            print(f"    - Warnings/Errors: {status.get('error')}")
    except Exception as e:
        print(f"[-] Critical failure during backfill: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
