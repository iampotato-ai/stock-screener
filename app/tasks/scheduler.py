"""
Background worker scheduler using APScheduler.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import logging
import os
import urllib.request
import json
import time
from flask import Flask
from app.services.model_training_service import run_ep_model_training
from app.tasks.score_calculator import calculate_all_scores

logger = logging.getLogger(__name__)

def init_scheduler(app: Flask):
    """Initialize the background scheduler."""
    # Check if we are running in testing environment
    if app.config.get('TESTING', False) or os.environ.get('PYTEST_CURRENT_TEST'):
        logger.info("Background tasks are disabled during testing")
        return None

    # Check if background tasks are enabled via feature flag (read from Flask config)
    if not app.config.get('ENABLE_BACKGROUND_TASKS', True):
        logger.info("Background tasks are disabled via feature flag")
        return None

    # Prevent double initialization in Flask debug mode
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        # We are in the Flask reloader process, skip initialization
        logger.debug("Scheduler not initialized in reloader process")
        return None

    scheduler = BackgroundScheduler()

    # Add EP refresh job - runs every 30 minutes
    scheduler.add_job(
        func=refresh_ep_task,
        trigger=IntervalTrigger(minutes=30),
        id='ep_refresh_job',
        name='Refresh EP screener data every 30 minutes',
        replace_existing=True,
        args=[app]  # Pass app for context
    )

    # Add IPO refresh job - runs every hour
    scheduler.add_job(
        func=refresh_ipo_task,
        trigger=IntervalTrigger(hours=1),
        id='ipo_refresh_job',
        name='Refresh IPO data every hour',
        replace_existing=True,
        args=[app]  # Pass app for context
    )

    # Add EP model training job - runs daily at configured hour/minute (gated behind feature flag)
    if app.config.get('EP_MODEL_TRAINING_ENABLED', False):
        scheduler.add_job(
            func=run_ep_model_training,
            trigger='cron',
            hour=app.config.get('EP_MODEL_TRAIN_HOUR', 16),
            minute=app.config.get('EP_MODEL_TRAIN_MINUTE', 0),
            timezone='Asia/Kolkata',
            id='ep_model_training',
            name='Daily EP scoring model training',
            replace_existing=True,
            args=[app]
        )

    # One-shot startup warm-up: fill any missing IPO metrics cache entries
    # Fires 10 seconds after server start, in the background, without blocking requests.
    from datetime import datetime, timedelta
    scheduler.add_job(
        func=startup_ipo_cache_warmup,
        trigger='date',
        run_date=datetime.now() + timedelta(seconds=10),
        id='startup_ipo_warmup',
        name='One-shot IPO metrics cache warm-up on server start',
        replace_existing=True,
        args=[app]
    )

    # One-shot startup warm-up: fill Bull Snort cache if empty
    # Fires 15 seconds after server start, in the background, without blocking requests.
    if app.config.get('ENABLE_BULL_SNORT', False):
        scheduler.add_job(
            func=startup_bull_snort_warmup,
            trigger='date',
            run_date=datetime.now() + timedelta(seconds=15),
            id='startup_bull_snort_warmup',
            name='One-shot Bull Snort cache warm-up on server start',
            replace_existing=True,
            args=[app]
        )

    # Add Bull Snort refresh job - runs daily at 16:05 (gated behind feature flag)
    if app.config.get('ENABLE_BULL_SNORT', False):
        scheduler.add_job(
            func=refresh_bull_snort,
            trigger='cron',
            hour=16,
            minute=5,
            timezone='Asia/Kolkata',
            id='bull_snort_refresh',
            name='Daily Bull Snort screener refresh',
            replace_existing=True,
            args=[app]
        )

    # Add Daily Momentum Confidence Score calculation job - runs after market close
    scheduler.add_job(
        func=calculate_all_scores,
        trigger='cron',
        hour=app.config.get('DAILY_SCORE_HOUR', 16),
        minute=app.config.get('DAILY_SCORE_MINUTE', 30),
        timezone='Asia/Kolkata',
        id='daily_momentum_score_job',
        name='Daily Momentum Confidence Score calculation',
        replace_existing=True,
        args=[app]
    )

    # Add market cap refresh job - runs daily at configured hour (gated behind feature flag)
    if app.config.get('ENABLE_MARKET_CAP_CACHE', True):
        scheduler.add_job(
            func=refresh_market_cap_cache,
            trigger='cron',
            hour=app.config.get('MARKET_CAP_REFRESH_HOUR', 3),
            minute=0,
            timezone='Asia/Kolkata',
            id='market_cap_refresh',
            name='Daily market cap cache refresh',
            replace_existing=True,
            args=[app]
        )

    # Add Market Intelligence Ingestion job
    scheduler.add_job(
        func=ingest_market_intelligence_task,
        trigger=IntervalTrigger(minutes=app.config.get('NEWS_REFRESH_MINUTES', 60)),
        id='mi_ingest_job',
        name='Refresh Market Intelligence news and events',
        replace_existing=True,
        args=[app]
    )

    # Start the scheduler
    scheduler.start()
    logger.info("Background scheduler started")

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    # Store scheduler on app for potential future access
    app.scheduler = scheduler

    return scheduler


def refresh_ep_task(app: Flask):
    """Background task to refresh EP screener data."""
    try:
        # Import here to avoid circular imports
        with app.app_context():
            from app import refresh_ep_screener
            refresh_ep_screener()
            logger.info("EP refresh task completed successfully")
    except Exception as e:
        logger.error(f"Error in background EP refresh task: {e}")


def refresh_ipo_task(app: Flask):
    """Background task to refresh IPO data."""
    try:
        # Import here to avoid circular imports
        with app.app_context():
            from app.services.ipo_service import ipo_service
            ipo_service.refresh_ipo_metrics()
            logger.info("IPO refresh task completed successfully")
    except Exception as e:
        logger.error(f"Error in background IPO refresh task: {e}")


def startup_ipo_cache_warmup(app: Flask):
    """One-shot startup job: fill any IPO listings missing from the metrics cache."""
    try:
        import sqlite3
        import os
        with app.app_context():
            db_path = app.config.get('DATABASE', 'scan_history.db')
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM ipo_listings "
                "WHERE ticker NOT IN (SELECT ticker FROM ipo_metrics_cache)"
            )
            missing_cnt = c.fetchone()[0]
            conn.close()
            if missing_cnt > 0:
                logger.info(
                    f"Startup warm-up: IPO metrics cache is missing {missing_cnt} entries. "
                    "Refreshing..."
                )
                from app import refresh_ipo_metrics
                refresh_ipo_metrics()
                logger.info("Startup IPO cache warm-up complete.")
    except Exception as e:
        logger.error(f"Error in startup IPO cache warm-up: {e}")


def startup_bull_snort_warmup(app: Flask):
    """One-shot startup job: warm up Bull Snort cache on server start if it is missing."""
    try:
        with app.app_context():
            cache = app.config.get('BULL_SNORT_CACHE')
            if cache is None or 'data' not in cache:
                logger.info("Startup warm-up: Bull Snort cache is empty. Refreshing...")
                refresh_bull_snort(app)
                logger.info("Startup Bull Snort cache warm-up complete.")
    except Exception as e:
        logger.error(f"Error in startup Bull Snort cache warm-up task: {e}")


def refresh_bull_snort(app: Flask):
    """Background task to run Bull Snort screening and cache results."""
    try:
        with app.app_context():
            from app.database import get_nse_symbols
            from app.services.bull_snort_service import screen_bull_snort
            import pandas as pd
            symbols = get_nse_symbols()
            results = screen_bull_snort(
                symbols,
                vol_avg_period=app.config.get('BULL_SNORT_VOL_AVG_PERIOD', 20),
                vol_surge_min=app.config.get('BULL_SNORT_VOL_SURGE_MIN', 3.0),
                close_position_min=app.config.get('BULL_SNORT_CLOSE_POSITION_MIN', 0.65),
                min_gap_history=app.config.get('BULL_SNORT_MIN_GAP_HISTORY', 10.0),
                max_current_gap=app.config.get('BULL_SNORT_MAX_CURRENT_GAP', 5.0),
                allow_yfinance=True
            )
            cache_data = {
                'data': results,
                'count': len(results),
                'refreshed': pd.Timestamp.now().isoformat()
            }
            app.config['BULL_SNORT_CACHE'] = cache_data
            
            # Save cache to instance folder for persistence across restarts
            cache_file = os.path.join(app.instance_path, 'bull_snort_cache.json')
            try:
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=2)
                logger.info("Saved Bull Snort cache to disk")
            except Exception as e:
                logger.error(f"Failed to save Bull Snort cache to disk: {e}")

            logger.info(f"Bull Snort background screen completed: {len(results)} signals found")
    except Exception as e:
        logger.error(f"Error in background Bull Snort refresh task: {e}")


def refresh_market_cap_cache(app: Flask):
    """Background task to refresh market cap cache for NSE symbols."""
    try:
        with app.app_context():
            from app.database import get_nse_symbols, execute_query
            logger.info("Starting market cap cache refresh...")
            # Clear the cache table
            execute_query("DELETE FROM market_cap_cache", commit=True)
            # Get all NSE symbols
            symbols = get_nse_symbols()
            logger.info(f"Fetching market cap for {len(symbols)} symbols")
            inserted = 0
            import yfinance as yf
            for sym in symbols:
                try:
                    ticker = yf.Ticker(f"{sym}.NS")
                    info = ticker.info or {}
                    mkt_cap_raw = info.get('marketCap', 0)
                    # yfinance returns marketCap in the currency of the security (INR for NSE)
                    market_cap_inr = int(mkt_cap_raw)
                    # Insert into cache
                    execute_query(
                        "INSERT OR REPLACE INTO market_cap_cache (ticker, market_cap_inr, fetched_at) VALUES (?, ?, datetime('now'))",
                        (sym, market_cap_inr),
                        commit=True
                    )
                    inserted += 1
                    # Gentle rate limit
                    time.sleep(0.05)
                except Exception as e:
                    logger.warning(f"Failed to fetch market cap for {sym}: {e}")
                    continue
            logger.info(f"Market cap cache refresh completed. Inserted/updated {inserted} symbols.")
    except Exception as e:
        logger.error(f"Error in background market cap refresh task: {e}")


def ingest_market_intelligence_task(app: Flask):
    """Background task to fetch news and events for high-priority symbols."""
    try:
        with app.app_context():
            from app.services.market_intelligence.jobs.priority_queue import priority_queue
            from app.services.market_intelligence.services.news_service import NewsService
            from app.services.market_intelligence.services.event_service import EventService
            
            logger.info("Starting background Market Intelligence ingestion task...")
            
            news_service = NewsService()
            event_service = EventService()
            
            # Fetch priority queue symbols
            symbols = priority_queue.get_all_priority_symbols()
            
            # Limit background polling to avoid rate limits
            limit = 20
            target_symbols = symbols[:limit]
            
            logger.info(f"Priority symbols target for this run: {target_symbols}")
            
            for sym in target_symbols:
                try:
                    new_news = news_service.ingest_news_for_symbol(sym)
                    new_events = event_service.ingest_events_for_symbol(sym)
                    logger.info(f"Ingested {sym}: Added {new_news} news articles, {new_events} corporate events.")
                    # Gentle sleep to respect rate limits
                    time.sleep(0.5)
                except Exception as sym_err:
                    logger.warning(f"Error fetching data for priority symbol {sym}: {sym_err}")
                    
            logger.info("Background Market Intelligence ingestion task completed.")
    except Exception as e:
        logger.error(f"Error in background Market Intelligence task: {e}")


# For direct execution (testing)
if __name__ == "__main__":
    # This would normally be called from app/__init__.py
    logging.basicConfig(level=logging.INFO)
    print("Scheduler module - would initialize background jobs when integrated with Flask app")