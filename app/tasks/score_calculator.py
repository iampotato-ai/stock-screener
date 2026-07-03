"""
Score calculator task for daily Momentum Confidence Score calculation.
This module defines a background job that iterates over all NSE symbols and
computes the Momentum Confidence Score for each stock, persisting the
results via the scoring service's database integration.
"""

import logging
from typing import List

from flask import Flask

# Import inside functions to avoid circular imports when module is loaded.


def calculate_all_scores(app: Flask) -> None:
    """Calculate and store Momentum Confidence Scores for all NSE symbols.

    This function is intended to be scheduled as a daily background job. It:
    1. Retrieves the full list of NSE ticker symbols.
    2. Instantiates :class:`MomentumConfidenceScoreService`.
    3. Calls ``calculate_score_for_stock`` for each symbol, which handles
       mock‑data generation, scoring, badge awarding, explanation creation and
       persists the result via ``_save_score_to_db``.
    4. Logs progress and any failures.

    Args:
        app: The Flask application instance – required for DB access and
            configuration context.
    """
    logger = logging.getLogger(__name__)
    try:
        # Ensure we have an application context for DB operations.
        with app.app_context():
            from app.services.scoring_service import MomentumConfidenceScoreService
            from app.database import get_nse_symbols

            service = MomentumConfidenceScoreService()
            symbols: List[str] = get_nse_symbols()
            total = len(symbols)
            logger.info(f"Starting daily Momentum Confidence Score calculation for {total} symbols")

            for idx, symbol in enumerate(symbols, start=1):
                try:
                    # The service defaults to exchange='NSE' if not provided.
                    result = service.calculate_score_for_stock(symbol)
                    if not result.get('success', False):
                        logger.warning(
                            f"Score calculation failed for {symbol}: {result.get('error')}"
                        )
                except Exception as exc:
                    logger.error(f"Exception calculating score for {symbol}: {exc}")

                # Periodic progress log – helps monitor long runs.
                if idx % 50 == 0 or idx == total:
                    logger.info(f"Processed {idx}/{total} symbols")

            logger.info("Daily Momentum Confidence Score calculation completed")
    except Exception as outer_exc:
        # Capture any unexpected failure that prevents the job from completing.
        logger.error(f"Error in daily score calculation job: {outer_exc}")
