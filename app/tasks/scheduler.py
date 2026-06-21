"""
Background worker scheduler using APScheduler.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import logging
import os
from flask import Flask
from app.services.model_training_service import run_ep_model_training

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


# For direct execution (testing)
if __name__ == "__main__":
    # This would normally be called from app/__init__.py
    logging.basicConfig(level=logging.INFO)
    print("Scheduler module - would initialize background jobs when integrated with Flask app")