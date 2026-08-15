"""
run_today_jobs.py — Run all missed EOD background jobs for today.
Usage: python run_today_jobs.py
"""

import sys
import time
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("run_today_jobs")


def banner(title):
    line = "=" * 60
    print(f"\n{line}\n>>>  {title}\n{line}")


def run_job(label, fn, *args, **kwargs):
    banner(label)
    t0 = time.time()
    try:
        fn(*args, **kwargs)
        elapsed = time.time() - t0
        print(f"OK  {label} -- completed in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"FAILED  {label} -- failed after {elapsed:.1f}s: {e}")


# Bootstrap Flask app
from run import app  # uses the canonical create_app() entry point

with app.app_context():

    from app.tasks.scheduler import (
        refresh_ep_task,
        refresh_ipo_task,
        refresh_daily_bars_universe,
        refresh_bull_snort,
        refresh_fear_greed_task,
        refresh_multiyear_breakout_task,
    )
    from app.tasks.score_calculator import calculate_all_scores

    # 1. EP Screener Refresh
    run_job("EP Screener Refresh", refresh_ep_task, app)

    # 2. Daily Bars Universe Refresh (feeds Bull Snort & Stage Analyzer)
    run_job("Daily Bars Universe Refresh (EOD)", refresh_daily_bars_universe, app)

    # 3. Bull Snort Screen
    if app.config.get("ENABLE_BULL_SNORT", False):
        run_job("Bull Snort Screen (EOD)", refresh_bull_snort, app)
    else:
        print("\nSKIP  Bull Snort -- ENABLE_BULL_SNORT=False")

    # 4. Stage Analyzer
    if app.config.get("STAGE_ANALYSIS_ENABLED", True):
        from app.services.stage_analyzer.scheduler import _run_stage_analysis_job
        run_job("Stage Analyzer", _run_stage_analysis_job, app)
    else:
        print("\nSKIP  Stage Analyzer -- STAGE_ANALYSIS_ENABLED=False")

    # 5. Momentum Confidence Scores
    run_job("Momentum Confidence Scores", calculate_all_scores, app, force=True)

    # 6. Fear & Greed Index
    run_job("Fear & Greed Index", refresh_fear_greed_task, app)

    # 7. IPO Metrics Refresh
    run_job("IPO Metrics Refresh", refresh_ipo_task, app)

    # 8. Multiyear Breakout Scanner
    if app.config.get("ENABLE_MULTIYEAR_BREAKOUT", True):
        run_job("Multiyear Breakout Scanner", refresh_multiyear_breakout_task, app)
    else:
        print("\nSKIP  Multiyear Breakout -- ENABLE_MULTIYEAR_BREAKOUT=False")

    # Summary
    banner("ALL JOBS DONE")
    print("All scheduled EOD jobs for today have been executed.")
