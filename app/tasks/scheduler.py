"""
Background worker scheduler using APScheduler.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import logging
from flask import current_app

logger = logging.getLogger(__name__)

def init_scheduler(app):
    """Initialize the background scheduler."""
    scheduler = BackgroundScheduler()

    # Add EP refresh job - runs every 30 minutes
    scheduler.add_job(
        func=refresh_ep_task,
        trigger=IntervalTrigger(minutes=30),
        id='ep_refresh_job',
        name='Refresh EP screener data every 30 minutes',
        replace_existing=True
    )

    # Add IPO refresh job - runs every hour
    scheduler.add_job(
        func=refresh_ipo_task,
        trigger=IntervalTrigger(hours=1),
        id='ipo_refresh_job',
        name='Refresh IPO data every hour',
        replace_existing=True
    )

    # Start the scheduler
    scheduler.start()
    logger.info("Background scheduler started")

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    return scheduler

def refresh_ep_task():
    """Background task to refresh EP screener data."""
    try:
        # Import here to avoid circular imports
        from app import refresh_ep_screener
        # In a real implementation, we'd need to call this within an app context
        # For now, we'll just log that the task would run
        logger.info("Background EP refresh task executed")
        # refresh_ep_screener()  # This would be called in real implementation
    except Exception as e:
        logger.error(f"Error in background EP refresh task: {e}")

def refresh_ipo_task():
    """Background task to refresh IPO data."""
    try:
        # Import here to avoid circular imports
        from app.services.ipo_service import ipo_service
        # In a real implementation, we'd need to call this within an app context
        # For now, we'll just log that the task would run
        logger.info("Background IPO refresh task executed")
        # ipo_service.refresh_ipo_metrics()  # This would be called in real implementation
    except Exception as e:
        logger.error(f"Error in background IPO refresh task: {e}")

# For direct execution (testing)
if __name__ == "__main__":
    # This would normally be called from app/__init__.py
    logging.basicConfig(level=logging.INFO)
    print("Scheduler module - would initialize background jobs when integrated with Flask app")