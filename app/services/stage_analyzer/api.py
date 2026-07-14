from flask import Blueprint, jsonify, current_app

# Blueprint for Stage Analyzer API endpoints
stage_analyzer_bp = Blueprint('stage_analyzer', __name__)

@stage_analyzer_bp.route('/stage-analyzer/results', methods=['GET'])
def get_stage_analysis_results():
    """Return the cached stage analysis results.
    The scheduler stores a dict of symbol -> analysis payload in
    ``app.config['STAGE_ANALYSIS_RESULTS']``.
    """
    results = current_app.config.get('STAGE_ANALYSIS_RESULTS', {})
    return jsonify(results)

@stage_analyzer_bp.route('/stage-analyzer/status', methods=['GET'])
def get_stage_analysis_status():
    """Return scheduler status and scheduled jobs for debugging."""
    scheduler_status = "not initialized"
    jobs_info = []
    if hasattr(current_app, 'scheduler') and current_app.scheduler is not None:
        scheduler = current_app.scheduler
        scheduler_status = "running" if scheduler.running else "stopped"
        for job in scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": str(job.next_run_time) if job.next_run_time else None
            })
    
    results = current_app.config.get('STAGE_ANALYSIS_RESULTS', {})
    return jsonify({
        "scheduler_status": scheduler_status,
        "jobs": jobs_info,
        "cached_results_count": len(results),
        "cached_keys_sample": list(results.keys())[:10]
    })

@stage_analyzer_bp.route('/stage-analyzer/history', methods=['GET'])
def get_stage_analysis_history():
    """Return historical daily stage counts for the last 30 trading dates
    reconstructed dynamically from the daily_bars database table.
    """
    try:
        from app.database import fetch_all
        # Load daily bars
        rows = fetch_all("SELECT symbol, trade_date, close FROM daily_bars ORDER BY symbol, trade_date ASC")
        if not rows:
            return jsonify({})

        # Group closing prices and dates by symbol
        symbol_data = {}
        all_dates_set = set()
        for row in rows:
            symbol = row["symbol"]
            trade_date = row["trade_date"]
            close = row["close"]
            
            # Normalize trade_date if it is datetime/date object to string format
            trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)
            
            if symbol not in symbol_data:
                symbol_data[symbol] = []
            symbol_data[symbol].append((trade_date_str, close))
            all_dates_set.add(trade_date_str)

        # Sort all unique dates and take the last 30
        sorted_dates = sorted(list(all_dates_set))
        target_dates = sorted_dates[-30:]

        # Reconstruct daily stage counts
        stage_history = {}
        for symbol, data in symbol_data.items():
            dates = [x[0] for x in data]
            closes = [x[1] for x in data]
            
            for target_date in target_dates:
                if target_date not in dates:
                    continue
                idx = dates.index(target_date)
                if idx < 4:
                    continue
                
                # Slicing up to 60 bars of history
                start_idx = max(0, idx - 60)
                sub_closes = closes[start_idx:idx+1]
                
                first_close = sub_closes[0]
                last_close = sub_closes[-1]
                growth = (last_close - first_close) / first_close if first_close != 0 else 0.0
                
                if growth > 0.10:
                    stage = "Stage 2"
                elif growth < -0.05:
                    stage = "Stage 4"
                else:
                    max_close = max(sub_closes)
                    min_close = min(sub_closes)
                    if (max_close - min_close) > 0 and (last_close - min_close) / (max_close - min_close) > 0.6:
                        stage = "Stage 3"
                    else:
                        stage = "Stage 1"
                        
                if target_date not in stage_history:
                    stage_history[target_date] = {'Stage 1': 0, 'Stage 2': 0, 'Stage 3': 0, 'Stage 4': 0, 'Unknown': 0}
                stage_history[target_date][stage] += 1
                
        return jsonify(stage_history)
    except Exception as e:
        current_app.logger.error(f"Error generating stage history: {e}")
        return jsonify({}), 500


