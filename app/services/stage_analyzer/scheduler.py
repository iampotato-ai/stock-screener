"""
Stage Analyzer Scheduler Jobs

Core background worker functions for Stage Analyzer.
Runs periodic stage‑analysis for all NSE symbols and stores the
latest results in the Flask app config (in‑memory cache).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

from flask import Flask

from app.database import get_nse_symbols
from app.services.stage_analyzer.engine import analyze
from app.utils.technical import fetch_historical_prices

logger = logging.getLogger(__name__)


def _run_stage_analysis_job(app: Flask) -> None:
    """
    Pull the list of NSE symbols (limited to the top 300 by market cap for efficiency),
    run the Stage Analyzer ``analyze`` pipeline on each in parallel, and store the
    latest result in an in‑memory cache.

    The cache lives under ``app.config['STAGE_ANALYSIS_RESULTS']`` as a
    dict mapping ticker symbols to the analysis payload.
    """
    try:
        with app.app_context():
            # Get top 300 symbols by market cap to keep dashboard snappy and representative
            from app.database import fetch_all
            symbols = []
            try:
                rows = fetch_all("SELECT ticker FROM market_cap_cache ORDER BY market_cap_inr DESC LIMIT 300")
                if rows:
                    symbols = [row["ticker"] for row in rows]
            except Exception as e:
                logger.warning("Failed to query market_cap_cache for Stage Analyzer: %s", e)

            if not symbols:
                symbols = get_nse_symbols()[:300]

            logger.info("Stage Analyzer – processing %d symbols in parallel", len(symbols))

            if "STAGE_ANALYSIS_RESULTS" not in app.config:
                app.config["STAGE_ANALYSIS_RESULTS"] = {}
            results = app.config["STAGE_ANALYSIS_RESULTS"]

            from concurrent.futures import ThreadPoolExecutor

            def process_symbol(symbol: str) -> None:
                try:
                    # Fetch historical price data using shared cache
                    history = fetch_historical_prices(symbol)
                    if not history:
                        return
                    # Compute SMA21 and SMA50 if enough data
                    closes = [day["close"] for day in history]
                    sma21 = sum(closes[-21:]) / 21 if len(closes) >= 21 else None
                    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
                    stock_data = {"ticker": symbol, "history": history, "SMA21": sma21, "SMA50": sma50}
                    analysis = analyze(stock_data)
                    results[symbol] = analysis
                except Exception as e:
                    logger.warning("Stage analysis failed for %s: %s", symbol, e)

            # Fetch and analyze in parallel using a thread pool
            with ThreadPoolExecutor(max_workers=15) as executor:
                executor.map(process_symbol, symbols)

            logger.info(
                "Stage Analyzer – completed %d analyses (cached at %s)",
                len(results),
                datetime.now(timezone.utc).isoformat(),
            )
    except Exception as exc:
        logger.error("Unexpected error in Stage Analyzer scheduler job: %s", exc)
