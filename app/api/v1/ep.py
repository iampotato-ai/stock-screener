"""
Episodic Pivot (EP) API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.ep_service import ep_service


@api_bp.route('/ep/today', methods=['GET'])
def get_ep_today():
    """
    Get latest EP features with optional filtering and pagination.
    Query parameters:
    - ep_type: filter by EP type (all, Growth EP, Turnaround EP, Story EP, Volume EP)
    - confidence: filter by confidence (all, HIGH, MEDIUM, LOW)
    - min_score: minimum score filter (default: 0.55)
    - min_mktcap: minimum market cap in Crores
    - max_mktcap: maximum market cap in Crores
    - exchange: filter by exchange (all, NSE, BSE)
    - limit: limit count for pagination
    - offset: offset count for pagination
    """
    ep_type = request.args.get('ep_type', 'all').strip()
    confidence = request.args.get('confidence', 'all').strip()
    min_score_raw = request.args.get('min_score', '').strip()
    min_score = float(min_score_raw) if min_score_raw else 0.55
    min_mktcap_raw = request.args.get('min_mktcap', '').strip()
    min_mktcap = float(min_mktcap_raw) if min_mktcap_raw else 0.0
    max_mktcap_raw = request.args.get('max_mktcap', '').strip()
    max_mktcap = float(max_mktcap_raw) if max_mktcap_raw else 999999.0
    exchange = request.args.get('exchange', 'all').strip()
    
    limit = request.args.get('limit', '').strip()
    offset = request.args.get('offset', '').strip()
    
    try:
        res = ep_service.get_ep_today(
            ep_type=ep_type,
            confidence=confidence,
            min_score=min_score,
            min_mktcap=min_mktcap,
            max_mktcap=max_mktcap,
            exchange=exchange,
            limit=int(limit) if limit.isdigit() else None,
            offset=int(offset) if offset.isdigit() else None
        )
        return jsonify(
            listings=res["listings"],
            total=res["total"],
            summary=res["summary"],
            latest_date=res["latest_date"],
            last_run_time=ep_service.last_refresh_datetime
        )
    except Exception as e:
        current_app.logger.error(f"Error getting EP today listings: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/sugar-babies', methods=['GET'])
def get_ep_sugar_babies():
    """Get active sugar babies listings."""
    try:
        babies = ep_service.get_ep_sugar_babies()
        return jsonify(sugar_babies=babies)
    except Exception as e:
        current_app.logger.error(f"Error getting EP sugar babies: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/sugar-babies', methods=['POST'])
def add_to_sugar_babies():
    """Add a ticker to active sugar babies list."""
    if not request.is_json:
        # Support both JSON and form data parameters
        data = request.form or {}
    else:
        data = request.get_json() or {}
        
    symbol = data.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify(error="Symbol is required"), 400
    exchange = data.get("exchange", "NSE").upper().strip()
    notes = data.get("notes", "")
    is_active = int(data.get("is_active", 1))

    try:
        ep_service.add_to_sugar_babies(symbol, exchange, notes, is_active)
        status_text = "added to" if is_active else "removed from"
        return jsonify(success=True, message=f"Symbol {status_text} Sugar Babies")
    except Exception as e:
        current_app.logger.error(f"Error adding to EP sugar babies: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/<symbol>/detail', methods=['GET'])
def get_ep_detail(symbol):
    """Get detailed information for a specific symbol."""
    try:
        detail = ep_service.get_ep_detail(symbol)
        return jsonify(detail)
    except ValueError as e:
        return jsonify(error=str(e)), 404
    except Exception as e:
        current_app.logger.error(f"Error getting EP detail for {symbol}: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/<symbol>/detail/base', methods=['GET'])
def get_ep_detail_base(symbol):
    """Fast DB-only payload: scores, fundamentals, watchlist.
    
    Also fires NSE event enrichment as a background thread so events
    will be fresher when the /events endpoint is queried shortly after.
    """
    try:
        data = ep_service.get_ep_detail_base(symbol)
        return jsonify(data)
    except ValueError as e:
        return jsonify(error=str(e)), 404
    except Exception as e:
        current_app.logger.error(f"Error getting EP detail base for {symbol}: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/<symbol>/detail/history', methods=['GET'])
def get_ep_detail_history(symbol):
    """Return 6-month OHLCV price history (Yahoo Finance, cached 15 min)."""
    try:
        data = ep_service.get_ep_detail_history(symbol)
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Error getting EP price history for {symbol}: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/<symbol>/detail/events', methods=['GET'])
def get_ep_detail_events(symbol):
    """Return corporate events from DB (no blocking network call)."""
    try:
        data = ep_service.get_ep_detail_events(symbol)
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Error getting EP events for {symbol}: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/<symbol>/detail/thesis', methods=['GET'])
def get_ep_detail_thesis(symbol):
    """Return AI thesis + reasoning. Cache-first; calls LLM only on miss."""
    feature_date = request.args.get('feature_date', '').strip() or None
    try:
        data = ep_service.get_ep_detail_thesis(symbol, feature_date=feature_date)
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Error getting EP thesis for {symbol}: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/themes', methods=['GET'])
def get_ep_themes():
    """Get EP theme groupings."""
    types_param = request.args.get("types", "").strip()
    try:
        themes = ep_service.get_ep_themes(types_param)
        return jsonify(themes=themes)
    except Exception as e:
        current_app.logger.error(f"Error getting EP themes: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/sector-rotation', methods=['GET'])
def get_ep_sector_rotation():
    """Get sector rotation details blended with watchlist counts."""
    try:
        rotation = ep_service.get_ep_sector_rotation()
        return jsonify(rotation=rotation)
    except Exception as e:
        current_app.logger.error(f"Error getting EP sector rotation: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/refresh', methods=['POST'])
def api_refresh_ep():
    """Trigger background EP features refresh."""
    try:
        started = ep_service.refresh_ep_screener()
        if started:
            return jsonify(success=True, message="Background EP refresh started.")
        else:
            return jsonify(error="Refresh cooldown active. Please wait before triggering another refresh."), 429
    except Exception as e:
        current_app.logger.error(f"Error triggering EP refresh: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/refresh/status', methods=['GET'])
def api_refresh_ep_status():
    """Get EP features refresh status with granular progress information."""
    try:
        status = ep_service.get_refresh_status()
        return jsonify(status)
    except Exception as e:
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/backtest/prepare', methods=['POST'])
def api_prep_backtest():
    """Trigger historical backfill for backtest data preparation."""
    data = request.get_json() or {}
    start_date = data.get("start_date", "2019-01-01").strip()
    end_date = data.get("end_date", "2025-12-31").strip()
    symbols_param = data.get("symbols", "").strip()

    try:
        started = ep_service.prep_backtest(start_date, end_date, symbols_param)
        if started:
            return jsonify(success=True, message="Background preparation started.")
        else:
            return jsonify(error="Preparation is already running."), 400
    except Exception as e:
        current_app.logger.error(f"Error starting backtest preparation: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/backtest/prep_status', methods=['GET'])
def api_prep_backtest_status():
    """Get status of background backtest preparation."""
    try:
        with ep_service.ep_backtest_prep_lock:
            return jsonify(ep_service.ep_backtest_prep_status)
    except Exception as e:
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/backtest', methods=['POST'])
def api_ep_backtest():
    """Run EP strategy backtest simulation."""
    try:
        from app.api.v1.legacy_routes import api_ep_backtest as legacy_backtest
        return legacy_backtest()
    except Exception as e:
        current_app.logger.error(f"Error running EP backtest: {e}")
        return jsonify(error=str(e)), 500
