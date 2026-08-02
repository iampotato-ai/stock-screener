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
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true' and os.environ.get('SCHEDULER_FORCE_START') != 'true':
        # We are in the Flask reloader process, skip initialization
        logger.debug("Scheduler not initialized in reloader process")
        return None

    scheduler = BackgroundScheduler()

    from datetime import datetime as _dt, timedelta as _td
    # Add EP refresh job - runs every 30 minutes, first run delayed 5 min after startup
    scheduler.add_job(
        func=refresh_ep_task,
        trigger=IntervalTrigger(minutes=30, start_date=_dt.now() + _td(minutes=5)),
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

    # Add Daily Pre-Market Brief job - runs daily at 08:45 AM IST
    scheduler.add_job(
        func=generate_daily_market_brief_task,
        trigger='cron',
        hour=8,
        minute=45,
        timezone='Asia/Kolkata',
        id='daily_market_brief_job',
        name='Daily Pre-Market Morning Brief synthesis at 08:45 AM IST',
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

    # One-shot startup warm-up: calculate daily Momentum Confidence Scores on server start if missed
    # Fires 20 seconds after server start in background
    scheduler.add_job(
        func=startup_momentum_score_warmup,
        trigger='date',
        run_date=datetime.now() + timedelta(seconds=20),
        id='startup_momentum_score_warmup',
        name='One-shot Momentum Confidence Score warm-up on server start',
        replace_existing=True,
        args=[app]
    )

    # Add daily_bars universe refresh job — runs at 16:15 IST after market close,
    # before the Bull Snort screen (16:05) so fresh data is available.
    # Note: Bull Snort runs at 16:05, but if daily_bars aren't ready yet the cached
    # result from the startup warmup will be served. On the next day cycle both jobs
    # fire in the correct order: bars at 16:15, screener warmup at next startup.
    # A second Bull Snort refresh is intentionally scheduled after bar refresh.
    scheduler.add_job(
        func=refresh_daily_bars_universe,
        trigger='cron',
        hour=16,
        minute=15,
        timezone='Asia/Kolkata',
        id='daily_bars_universe_refresh',
        name='Daily universe daily_bars refresh (EOD)',
        replace_existing=True,
        args=[app]
    )

    # Re-run Bull Snort AFTER the bars are fresh (16:35 IST)
    if app.config.get('ENABLE_BULL_SNORT', False):
        scheduler.add_job(
            func=refresh_bull_snort,
            trigger='cron',
            hour=16,
            minute=35,
            timezone='Asia/Kolkata',
            id='bull_snort_refresh_eod',
            name='Bull Snort post-bar refresh (EOD)',
            replace_existing=True,
            args=[app]
        )

    # Add Stage Analyzer jobs – reuses shared price cache and SMA calculations
    if app.config.get('STAGE_ANALYSIS_ENABLED', True):
        from app.services.stage_analyzer.scheduler import _run_stage_analysis_job
        scheduler.add_job(
            func=_run_stage_analysis_job,
            trigger='cron',
            hour=app.config.get('STAGE_ANALYSIS_HOUR', 16),
            minute=app.config.get('STAGE_ANALYSIS_MINUTE', 30),
            timezone='Asia/Kolkata',
            id='stage_analysis_daily',
            name='Daily Stage Analyzer run',
            replace_existing=True,
            args=[app]
        )

    # Add Fear & Greed Index periodic refresh (every 30 minutes)
    scheduler.add_job(
        func=refresh_fear_greed_task,
        trigger='interval',
        minutes=30,
        id='fear_greed_periodic_refresh',
        name='Periodic India Fear & Greed Index refresh',
        replace_existing=True,
        args=[app]
    )

    if app.config.get('STAGE_ANALYSIS_ENABLED', True):
        interval_minutes = app.config.get('STAGE_ANALYSIS_INTERVAL_MINUTES', 60)
        scheduler.add_job(
            func=_run_stage_analysis_job,
            trigger='interval',
            minutes=interval_minutes,
            id='stage_analysis_interval',
            name=f'Stage Analyzer interval ({interval_minutes} min)',
            replace_existing=True,
            args=[app],
            next_run_time=datetime.now() + timedelta(seconds=15)
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

        # One-shot startup warm-up: refresh market cap cache if empty
        # Fires 30 seconds after server start
        scheduler.add_job(
            func=startup_market_cap_warmup,
            trigger='date',
            run_date=datetime.now() + timedelta(seconds=30),
            id='startup_market_cap_warmup',
            name='One-shot Market Cap Cache warm-up on server start',
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
            conn = sqlite3.connect(db_path, timeout=60.0)
            conn.execute('PRAGMA busy_timeout = 60000')
            conn.execute('PRAGMA journal_mode = WAL')
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
    """One-shot startup job: warm up daily_bars universe & Bull Snort cache on server start
    if cache is missing OR if server was started after 16:15 IST and today's market data is missing/stale.
    """
    try:
        from datetime import datetime, timezone, timedelta
        import os
        import json

        with app.app_context():
            ist = timezone(timedelta(hours=5, minutes=30))
            now_ist = datetime.now(ist)
            today_str = now_ist.strftime("%Y-%m-%d")
            is_after_close = (now_ist.hour > 16) or (now_ist.hour == 16 and now_ist.minute >= 15)
            is_weekday = now_ist.weekday() < 5  # Mon=0..Fri=4

            cache = app.config.get('BULL_SNORT_CACHE')
            if cache is None or 'data' not in cache:
                cache_file = os.path.join(app.instance_path, 'bull_snort_cache.json')
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, 'r', encoding='utf-8') as f:
                            cache = json.load(f)
                            app.config['BULL_SNORT_CACHE'] = cache
                    except Exception:
                        cache = None

            needs_refresh = False

            if cache is None or 'data' not in cache or len(cache.get('data', [])) == 0:
                logger.info("Startup warm-up: Bull Snort cache is empty or missing. Triggering refresh...")
                needs_refresh = True
            elif is_weekday and is_after_close:
                refreshed_time = str(cache.get('refreshed', ''))
                if not refreshed_time.startswith(today_str):
                    logger.info(
                        f"Startup warm-up: Server started after 16:15 IST ({today_str}), "
                        f"but Bull Snort cache is from {refreshed_time[:10]}. Triggering update..."
                    )
                    needs_refresh = True
                else:
                    from app.models import DailyBar
                    from app.extensions import db
                    max_bar_date = db.session.query(db.func.max(DailyBar.trade_date)).scalar()
                    max_bar_str = max_bar_date.strftime('%Y-%m-%d') if hasattr(max_bar_date, 'strftime') else str(max_bar_date or '')
                    if max_bar_str < today_str:
                        logger.info(
                            f"Startup warm-up: Server started after 16:15 IST ({today_str}), "
                            f"but daily_bars latest date is {max_bar_str}. Triggering universe refresh..."
                        )
                        needs_refresh = True

            if needs_refresh:
                logger.info("Startup warm-up: Running daily_bars universe refresh...")
                refresh_daily_bars_universe(app)
                logger.info("Startup warm-up: Running Bull Snort screen refresh...")
                refresh_bull_snort(app)
                logger.info("Startup warm-up complete.")
            else:
                logger.info("Startup warm-up: Bull Snort cache and daily_bars are already up-to-date.")
    except Exception as e:
        logger.error(f"Error in startup Bull Snort cache warm-up task: {e}")


def startup_momentum_score_warmup(app: Flask):
    """One-shot startup job: check if server started after 16:30 IST on a trading day
    and calculate Momentum Confidence Scores if today's scores are missing."""
    try:
        from datetime import datetime, timezone, timedelta
        import os

        # Check feature flag or env var
        enabled = app.config.get('ENABLE_MOMENTUM_SCORE_CALCULATION', False) or (os.getenv('ENABLE_MOMENTUM_SCORE_CALCULATION', 'false').lower() == 'true')
        if not enabled:
            return

        with app.app_context():
            ist = timezone(timedelta(hours=5, minutes=30))
            now_ist = datetime.now(ist)
            today_str = now_ist.strftime("%Y-%m-%d")
            score_hour = app.config.get('DAILY_SCORE_HOUR', 16)
            score_minute = app.config.get('DAILY_SCORE_MINUTE', 30)
            is_after_score_time = (now_ist.hour > score_hour) or (now_ist.hour == score_hour and now_ist.minute >= score_minute)
            is_weekday = now_ist.weekday() < 5  # Mon..Fri

            if is_weekday and is_after_score_time:
                import sqlite3
                db_path = app.config.get('DATABASE', 'scan_history.db')
                conn = sqlite3.connect(db_path, timeout=10.0)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM momentum_scores WHERE date = ?", (today_str,))
                score_cnt = c.fetchone()[0]
                conn.close()

                if score_cnt == 0:
                    logger.info(
                        f"Startup warm-up: Server started after {score_hour}:{score_minute:02d} IST ({today_str}), "
                        f"but momentum scores are missing for today. Calculating..."
                    )
                    calculate_all_scores(app, force=True)
                    logger.info("Startup Momentum Score warm-up complete.")
                else:
                    logger.info("Startup warm-up: Momentum Confidence Scores for today are already present.")
    except Exception as e:
        logger.error(f"Error in startup Momentum Confidence Score warm-up task: {e}")


def startup_market_cap_warmup(app: Flask):
    """One-shot startup job: check if market_cap_cache table is empty on server start and fill it if needed."""
    try:
        import sqlite3
        with app.app_context():
            db_path = app.config.get('DATABASE', 'scan_history.db')
            conn = sqlite3.connect(db_path, timeout=10.0)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM market_cap_cache")
            mcc_cnt = c.fetchone()[0]
            conn.close()

            if mcc_cnt == 0:
                logger.info("Startup warm-up: market_cap_cache is empty. Refreshing market cap cache in background...")
                refresh_market_cap_cache(app)
                logger.info("Startup market cap cache warm-up complete.")
            else:
                logger.info(f"Startup warm-up: market_cap_cache has {mcc_cnt} entries, no warm-up needed.")
    except Exception as e:
        logger.error(f"Error in startup market cap cache warm-up task: {e}")



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


def refresh_daily_bars_universe(app: Flask):
    """Background task: download EOD price data for all NSE symbols (>=10B INR mktcap)
    and upsert into the daily_bars table. Runs daily at 16:15 IST so that Bull Snort
    and other features that depend on daily_bars always have fresh data."""
    try:
        with app.app_context():
            from app.database import get_nse_symbols_by_marketcap
            from app.api.v1.legacy_routes import run_historical_backfill
            from datetime import datetime, timedelta

            # Fetch symbols with mktcap >= 10B INR (same filter as Bull Snort GET endpoint)
            symbols = get_nse_symbols_by_marketcap(min_marketcap_inr=10_000_000_000)
            if not symbols:
                logger.warning("refresh_daily_bars_universe: no symbols from market_cap_cache, skipping")
                return

            today = datetime.now().strftime("%Y-%m-%d")
            # Start from 2 years ago to ensure enough history for Bull Snort (needs 230+ bars)
            start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

            logger.info(
                f"Starting EOD daily_bars universe refresh for {len(symbols)} symbols "
                f"({start} → {today})"
            )
            run_historical_backfill(symbols=symbols, start_date=start, end_date=today)
            logger.info("EOD daily_bars universe refresh complete.")
    except Exception as e:
        logger.error(f"Error in refresh_daily_bars_universe: {e}")


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


def refresh_fear_greed_task(app: Flask):
    """Background task to calculate and refresh India Fear & Greed Index."""
    try:
        with app.app_context():
            from app.services.fear_greed_service import fear_greed_service
            logger.info("Starting background Fear & Greed Index refresh...")
            computed = fear_greed_service.compute_fear_greed_index()
            fear_greed_service.save_fear_greed_snapshot(computed)
            logger.info("Background Fear & Greed Index refresh completed: Score %s (%s)", computed.get("score"), computed.get("label"))
    except Exception as e:
        logger.error(f"Error in background Fear & Greed task: {e}")


def generate_daily_market_brief_task(app: Flask):
    """Background task to synthesize and persist today's Daily Market Brief at 08:45 AM IST."""
    try:
        with app.app_context():
            from app.services.market_brief_service import market_brief_service
            logger.info("Starting scheduled Daily Market Brief generation task (08:45 AM IST)...")
            brief = market_brief_service.get_or_create_daily_brief(force_refresh=True)
            logger.info("Scheduled Daily Market Brief task completed: %s", brief.get("headline"))
    except Exception as e:
        logger.error(f"Error in background Daily Market Brief task: {e}")


# For direct execution (testing)

if __name__ == "__main__":
    # This would normally be called from app/__init__.py
    logging.basicConfig(level=logging.INFO)
    print("Scheduler module - would initialize background jobs when integrated with Flask app")