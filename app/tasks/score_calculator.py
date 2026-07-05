"""
Score calculator task for daily Momentum Confidence Score calculation.
This module defines a background job that iterates over all NSE symbols and
computes the Momentum Confidence Score for each stock, persisting the
results via the scoring service's database integration.
"""

import logging
import os
import time
from typing import List
from flask import Flask


def calculate_all_scores(app: Flask) -> None:
    """Calculate and store Momentum Confidence Scores for active screener symbols.

    This function is intended to be scheduled as a daily background job. It:
    1. Checks the ENABLE_MOMENTUM_SCORE_CALCULATION feature flag; exits early if disabled.
    2. Retrieves the active list of symbols from the screener service.
    3. Fetches isolated TradingView data for all symbols in batch.
    4. Instantiates MomentumConfidenceScoreService.
    5. Calls calculate_score_for_stock for each symbol, which handles scoring,
       badge awarding, explanation creation and persists the result.
    6. Logs progress, per-symbol failures, and a final success/failure summary.

    Args:
        app: The Flask application instance – required for DB access and
            configuration context.
    """
    logger = logging.getLogger(__name__)

    # Guard: do not run until real data fetching is wired up.
    # Set ENABLE_MOMENTUM_SCORE_CALCULATION=true to enable.
    if not os.getenv('ENABLE_MOMENTUM_SCORE_CALCULATION', 'false').lower() == 'true':
        logger.info(
            "Momentum score calculation is disabled "
            "(ENABLE_MOMENTUM_SCORE_CALCULATION != 'true'). Skipping."
        )
        return

    try:
        with app.app_context():
            from app.services.scoring_service import MomentumConfidenceScoreService
            from app.services.screener_service import screener_service
            from app.services.scoring.fetcher import fetch_isolated_tv_data

            service = MomentumConfidenceScoreService()

            # Get active symbols from screener (limited to 300 as per spec)
            scan_results = screener_service.get_scan_results(limit=300)
            symbols: List[str] = [s['ticker'] for s in scan_results if s.get('ticker')]
            total = len(symbols)

            logger.info(f"Starting daily Momentum Confidence Score calculation for {total} symbols from screener")

            if total == 0:
                logger.warning("No symbols found from screener, falling back to getting NSE symbols")
                # Fallback to getting NSE symbols from database
                from app.database import get_nse_symbols
                symbols = [s['ticker'] for s in get_nse_symbols()]
                total = len(symbols)
                logger.info(f"Retrieved {total} symbols from database")

            success_count = 0
            fail_count = 0
            batch_size = int(os.getenv('DAILY_SCORE_BATCH_SIZE', '200'))

            # Fetch isolated TradingView data for all symbols in batch (more efficient)
            logger.info(f"Fetching isolated TradingView data for {total} symbols in batches...")
            isolated_tv_data = {}

            # Process in batches for TradingView API to avoid too large requests
            for batch_start in range(0, total, batch_size):
                batch_end = min(batch_start + batch_size, total)
                batch_symbols = symbols[batch_start:batch_end]
                logger.debug(f"Fetching TradingView data for batch {batch_start+1}-{batch_end} of {total}")

                batch_tv_data = fetch_isolated_tv_data(batch_symbols)
                isolated_tv_data.update(batch_tv_data)

                # Small delay between batches to be respectful to the API
                if batch_end < total:
                    time.sleep(0.5)

            logger.info(f"Successfully fetched TradingView data for {len(isolated_tv_data)} symbols")

            # Process each symbol with the pre-fetched TradingView data
            for start in range(0, total, batch_size):
                batch = symbols[start:start + batch_size]
                for idx, symbol in enumerate(batch, start=start + 1):
                    try:
                        # Pass the isolated TradingView data to the scoring service
                        result = service.calculate_score_for_stock(symbol, isolated_tv_data=isolated_tv_data.get(symbol))
                        if result.get('success', False):
                            success_count += 1
                        else:
                            fail_count += 1
                            logger.warning(f"Score calculation failed for {symbol}: {result.get('error')}")
                    except Exception as exc:
                        fail_count += 1
                        logger.error(f"Exception calculating score for {symbol}: {exc}")
                logger.info(f"Processed symbols {start + 1}-{min(start + batch_size, total)} of {total}")
                time.sleep(1)  # Delay between batches to prevent overwhelming resources

            logger.info(
                f"Daily Momentum Confidence Score calculation completed: "
                f"{success_count} succeeded, {fail_count} failed out of {total} total."
            )
    except Exception as outer_exc:
        logger.error(f"Error in daily score calculation job: {outer_exc}")