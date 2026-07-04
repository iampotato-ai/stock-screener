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
    """Calculate and store Momentum Confidence Scores for all NSE symbols.

    This function is intended to be scheduled as a daily background job. It:
    1. Retrieves the full list of NSE ticker symbols.
    2. Instantiates MomentumConfidenceScoreService.
    3. Calls calculate_score_for_stock for each symbol, which handles scoring,
       badge awarding, explanation creation and persists the result.
    4. Logs progress and any failures.

    Args:
        app: The Flask application instance – required for DB access and
            configuration context.
    """
    logger = logging.getLogger(__name__)
    try:
        with app.app_context():
            from app.services.scoring_service import MomentumConfidenceScoreService
            from app.database import get_nse_symbols

            service = MomentumConfidenceScoreService()
            symbols: List[str] = get_nse_symbols()
            total = len(symbols)
            logger.info(f"Starting daily Momentum Confidence Score calculation for {total} symbols")

            batch_size = int(os.getenv('DAILY_SCORE_BATCH_SIZE', '200'))
            for start in range(0, total, batch_size):
                batch = symbols[start:start + batch_size]
                for idx, symbol in enumerate(batch, start=start + 1):
                    try:
                        result = service.calculate_score_for_stock(symbol)
                        if not result.get('success', False):
                            logger.warning(f"Score calculation failed for {symbol}: {result.get('error')}")
                    except Exception as exc:
                        logger.error(f"Exception calculating score for {symbol}: {exc}")
                logger.info(f"Processed symbols {start + 1}-{min(start + batch_size, total)} of {total}")
                time.sleep(1)

            logger.info("Daily Momentum Confidence Score calculation completed")
    except Exception as outer_exc:
        logger.error(f"Error in daily score calculation job: {outer_exc}")