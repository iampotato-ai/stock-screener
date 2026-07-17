#!/usr/bin/env python
"""
Universe-wide historical backfill script.
Runs the historical EP detection algorithm over the universe of stocks,
reusing the local daily_bars cache to prevent yfinance rate-limiting.
"""

import os
import sys
import argparse

# Insert workspace root to allow local module imports
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, basedir)

def main():
    parser = argparse.ArgumentParser(description="Universe-wide Historical EP Backfill")
    parser.add_argument(
        "--start-date", 
        type=str, 
        default="2019-01-01", 
        help="Start date for backfill in YYYY-MM-DD format (default: 2019-01-01)"
    )
    parser.add_argument(
        "--end-date", 
        type=str, 
        default="2026-07-14", 
        help="End date for backfill in YYYY-MM-DD format (default: 2026-07-14)"
    )
    parser.add_argument(
        "--symbols", 
        type=str, 
        default=None, 
        help="Optional comma-separated list of symbols to backfill. If omitted, backfills the entire database universe."
    )
    args = parser.parse_args()

    symbols_list = None
    if args.symbols:
        symbols_list = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print(f"[*] Starting universe backfill from {args.start_date} to {args.end_date}...")
    if symbols_list:
        print(f"[*] Target symbols: {', '.join(symbols_list)}")
    else:
        print("[*] Target: Entire database universe")

    # Import backfill runner from app
    from app.api.v1.legacy_routes import run_historical_backfill, ep_backtest_prep_status

    try:
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
