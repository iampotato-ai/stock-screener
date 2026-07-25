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
    reconstructed dynamically from the daily_bars database table using forward fill
    and incorporating the latest live stage scan cache for the current date.
    """
    try:
        from app.database import fetch_all
        from datetime import datetime
        import bisect

        # 1. Fetch live stage results cache to ensure today's counts match live telemetry exactly
        live_results = current_app.config.get('STAGE_ANALYSIS_RESULTS', {})

        # Define active symbols list (based on cache or fallback to top 300 nse symbols)
        active_symbols = set(live_results.keys())
        if not active_symbols:
            from app.database import get_nse_symbols
            try:
                mcap_rows = fetch_all("SELECT ticker FROM market_cap_cache ORDER BY market_cap_inr DESC LIMIT 300")
                if mcap_rows:
                    active_symbols = set(r["ticker"] for r in mcap_rows)
            except Exception:
                pass
            if not active_symbols:
                active_symbols = set(get_nse_symbols()[:300])

        active_list = sorted(list(active_symbols))

        # 2. Fetch daily bars only for the active symbols to ensure perfect count alignment
        rows = []
        if active_list:
            placeholders = ','.join('?' for _ in active_list)
            query = f"SELECT symbol, trade_date, close FROM daily_bars WHERE symbol IN ({placeholders}) ORDER BY symbol, trade_date ASC"
            rows = fetch_all(query, tuple(active_list))

        if not rows and not live_results:
            return jsonify({})

        symbol_data = {}
        all_dates_set = set()
        for row in rows:
            symbol = row["symbol"]
            trade_date = row["trade_date"]
            close = row["close"]
            trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)
            
            if symbol not in symbol_data:
                symbol_data[symbol] = []
            symbol_data[symbol].append((trade_date_str, close))
            all_dates_set.add(trade_date_str)

        today_str = datetime.now().strftime('%Y-%m-%d')
        if live_results:
            all_dates_set.add(today_str)

        # Extract last 30 valid weekday trading dates
        valid_dates = []
        for d in sorted(list(all_dates_set)):
            try:
                dt = datetime.strptime(d, '%Y-%m-%d')
                if dt.weekday() < 5:  # Mon-Fri
                    valid_dates.append(d)
            except ValueError:
                pass

        target_dates = valid_dates[-30:]
        if not target_dates:
            return jsonify({})

        latest_date = target_dates[-1]

        # Reconstruct daily stage counts with bisect forward-fill
        stage_history = {d: {'Stage 1': 0, 'Stage 2': 0, 'Stage 3': 0, 'Stage 4': 0, 'Unknown': 0} for d in target_dates}
        processed_latest = set()

        for symbol, data in symbol_data.items():
            dates = [x[0] for x in data]
            closes = [x[1] for x in data]
            
            for target_date in target_dates:
                # For latest_date, prefer live_results if available
                if target_date == latest_date and symbol in live_results:
                    if symbol not in processed_latest:
                        entry = live_results[symbol]
                        stg = (entry.get('score', {}) or {}).get('stage') or entry.get('stage') or 'Unknown'
                        if stg == 'mid': stg = 'Stage 1'
                        elif stg == 'early': stg = 'Stage 2'
                        elif stg == 'late': stg = 'Stage 4'
                        elif stg == 'unknown': stg = 'Unknown'
                        if stg not in stage_history[target_date]: stg = 'Unknown'
                        stage_history[target_date][stg] += 1
                        processed_latest.add(symbol)
                    continue

                # Forward-fill: find rightmost date <= target_date
                idx = bisect.bisect_right(dates, target_date) - 1
                if idx < 0:
                    continue

                if idx < 4:
                    stage_history[target_date]['Unknown'] += 1
                    continue
                
                # Slice up to 60 bars of history
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
                        
                stage_history[target_date][stage] += 1

        # For latest date, add any symbols in live_results not present in daily_bars
        if latest_date in stage_history and live_results:
            for symbol, entry in live_results.items():
                if symbol not in processed_latest:
                    stg = (entry.get('score', {}) or {}).get('stage') or entry.get('stage') or 'Unknown'
                    if stg == 'mid': stg = 'Stage 1'
                    elif stg == 'early': stg = 'Stage 2'
                    elif stg == 'late': stg = 'Stage 4'
                    elif stg == 'unknown': stg = 'Unknown'
                    if stg not in stage_history[latest_date]: stg = 'Unknown'
                    stage_history[latest_date][stg] += 1
                    processed_latest.add(symbol)
                
        return jsonify(stage_history)
    except Exception as e:
        current_app.logger.error(f"Error generating stage history: {e}")
        return jsonify({}), 500


