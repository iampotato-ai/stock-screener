import os
import sys
import time
import logging

# Reconfigure stdout/stderr to utf-8 to prevent Windows cp1252 charmap encoding errors
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure root directory is in pythonpath
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if basedir not in sys.path:
    sys.path.insert(0, basedir)

os.environ["TOKENIZERS_PARALLELISM"] = "false"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("run_all_jobs")

def main():
    print("=" * 65)
    print("      RUNNING ALL MOMENTUMSCAN BACKGROUND & SCHEDULER JOBS")
    print("=" * 65)

    from app import create_app
    app = create_app('development')

    results = []

    def run_job(name, func, *args, **kwargs):
        print(f"\n>>> [STARTING] {name}")
        sys.stdout.flush()
        t0 = time.time()
        status = "SUCCESS"
        error_msg = None
        try:
            func(*args, **kwargs)
        except Exception as e:
            status = "FAILED"
            error_msg = str(e)
            logger.error(f"Job '{name}' failed: {e}", exc_info=True)
        
        elapsed = round(time.time() - t0, 2)
        status_icon = "[OK]" if status == "SUCCESS" else "[FAIL]"
        print(f"<<< [COMPLETED] {name} | {status_icon} {status} | Time: {elapsed}s")
        sys.stdout.flush()
        results.append({
            "job": name,
            "status": status,
            "duration": f"{elapsed}s",
            "error": error_msg
        })

    from app.tasks.scheduler import (
        refresh_ep_task,
        refresh_ipo_task,
        startup_ipo_cache_warmup,
        startup_bull_snort_warmup,
        startup_momentum_score_warmup,
        startup_market_cap_warmup,
        refresh_bull_snort,
        ingest_market_intelligence_task,
        refresh_fear_greed_task,
        refresh_multiyear_breakout_task,
    )
    from app.services.stage_analyzer.scheduler import _run_stage_analysis_job
    from app.services.model_training_service import run_ep_model_training
    from app.tasks.score_calculator import calculate_all_scores

    # 1. India Fear & Greed Index Refresh
    run_job("1. India Fear & Greed Index Refresh", refresh_fear_greed_task, app)

    # 3. EP Screener Refresh
    run_job("3. EP Screener Data Refresh", refresh_ep_task, app)

    # 4. IPO Metrics Refresh
    run_job("4. IPO Metrics Refresh", refresh_ipo_task, app)

    # 5. Startup IPO Cache Warmup
    run_job("5. Startup IPO Cache Warmup", startup_ipo_cache_warmup, app)

    # 6. Startup Market Cap Cache Warmup
    run_job("6. Startup Market Cap Cache Warmup", startup_market_cap_warmup, app)

    # 7. Startup Bull Snort Warmup
    run_job("7. Startup Bull Snort Warmup", startup_bull_snort_warmup, app)

    # 8. Startup Momentum Score Warmup
    run_job("8. Startup Momentum Score Warmup", startup_momentum_score_warmup, app)

    # 9. Market Intelligence Ingestion
    run_job("9. Market Intelligence Ingestion", ingest_market_intelligence_task, app)

    # 10. Stage Analyzer Screen
    run_job("10. Stage Analyzer Scan", _run_stage_analysis_job, app)

    # 11. EP Model Training
    run_job("11. EP Model Training (Dry Run)", run_ep_model_training, app)

    # 12. Bull Snort Screen Refresh
    run_job("12. Bull Snort Screen Refresh", refresh_bull_snort, app)

    # 13. Momentum Confidence Score Calculation
    run_job("13. Momentum Confidence Score Calculation", calculate_all_scores, app, force=True)

    # 14. Multiyear Breakout Scanner
    run_job("14. Multiyear Breakout Scanner", refresh_multiyear_breakout_task, app)

    print("\n" + "=" * 65)
    print("                    ALL JOBS EXECUTION SUMMARY")
    print("=" * 65)
    success_cnt = sum(1 for r in results if r["status"] == "SUCCESS")
    fail_cnt = sum(1 for r in results if r["status"] == "FAILED")
    
    for r in results:
        status_str = "[OK] SUCCESS" if r["status"] == "SUCCESS" else f"[FAIL] FAILED ({r['error']})"
        print(f"• {r['job']:<42} | {r['duration']:<8} | {status_str}")
    
    print("-" * 65)
    print(f"Total Jobs Run: {len(results)} | Succeeded: {success_cnt} | Failed: {fail_cnt}")
    print("=" * 65)

if __name__ == '__main__':
    main()
