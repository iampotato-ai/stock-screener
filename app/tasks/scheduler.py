"""
Background worker scheduler using APScheduler.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import logging
import os
from flask import Flask

logger = logging.getLogger(__name__)

def init_scheduler(app: Flask):
    """Initialize the background scheduler."""
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

# For direct execution (testing)
if __name__ == "__main__":
    # This would normally be called from app/__init__.py
    logging.basicConfig(level=logging.INFO)
    print("Scheduler module - would initialize background jobs when integrated with Flask app")