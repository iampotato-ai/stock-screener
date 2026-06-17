"""
IPO API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.ipo_service import ipo_service


@api_bp.route('/ipo/listings', methods=['GET'])
def get_ipo_listings():
    """
    Get IPO listings with optional filtering and pagination.
    Query parameters:
    - exchange: filter by exchange (NSE, BSE, all)
    - days: filter by days since listing (1m, 3m, 6m, 1y, 18m, all, or number)
    - phase: filter by momentum phase (HOT, STABLE, FADING, BROKEN, all)
    - volume_alert: filter by volume alerts (ppv, vol-surge, dry-vol, all, comma-separated)
    - min_volume: minimum volume filter (e.g., 100k, 1m, all)
    - limit: maximum number of results to return
    - offset: number of results to skip
    - sort_by: field to sort by (default: listing_date)
    - order: sort order (ASC or DESC, default: DESC)
    """
    exchange_param = request.args.get('exchange', 'all').strip()
    days_param = request.args.get('days', 'all').strip()
    phase_param = request.args.get('phase', 'all').strip()
    volume_alert_param = request.args.get('volume_alert', 'all').strip()
    min_volume_param = request.args.get('min_volume', 'all').strip()
    limit = request.args.get('limit', '').strip()
    offset = request.args.get('offset', '').strip()
    sort_by = request.args.get('sort_by', 'listing_date').strip()
    order = request.args.get('order', 'desc').strip().upper()

    if order not in ['ASC', 'DESC']:
        order = 'DESC'

    try:
        result = ipo_service.get_ipo_listings(
            exchange_param=exchange_param,
            days_param=days_param,
            phase_param=phase_param,
            volume_alert_param=volume_alert_param,
            min_volume_param=min_volume_param,
            limit=int(limit) if limit.isdigit() else None,
            offset=int(offset) if offset.isdigit() else None,
            sort_by=sort_by,
            order=order
        )
        # Return in the same format as the original endpoint
        return jsonify(
            listings=result["listings"],
            total=result["total"],
            summary=result["summary"]
        )
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error getting IPO listings: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ipo/detail/<ticker>', methods=['GET'])
def get_ipo_detail(ticker):
    """
    Get detailed information for a specific IPO ticker.
    """
    try:
        # Clean ticker format (remove NSE: or BO: prefixes if present)
        clean_ticker = ticker.upper()
        if clean_ticker.startswith("NSE:"):
            clean_ticker = clean_ticker[4:]
        elif clean_ticker.startswith("BO:"):
            clean_ticker = clean_ticker[3:]

        detail = ipo_service.get_ipo_detail(clean_ticker)
        # Return detail object directly like the original endpoint
        return jsonify(detail)
    except ValueError as e:
        # Check if it's a "not found" or "not cached" error for 404
        if "not found" in str(e).lower() or "not cached" in str(e).lower():
            return jsonify(error=str(e)), 404
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error getting IPO detail for {ticker}: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ipo/refresh', methods=['POST'])
def refresh_ipo_metrics():
    """
    Trigger a refresh of IPO metrics cache.
    """
    try:
        started = ipo_service.refresh_ipo_metrics()
        if started:
            return jsonify(success=True, message="Background refresh started."), 202
        else:
            return jsonify(error="Refresh cooldown active. Please wait before triggering another refresh."), 429
    except Exception as e:
        current_app.logger.error(f"Error refreshing IPO metrics: {e}")
        return jsonify(error=str(e)), 500


# Optional debug endpoint (can be removed in production)
@api_bp.route('/ipo/debug-nse')
def debug_nse_ipo():
    """
    One-time debug route — inspect raw NSE public-past-issues field names.
    Remove or gate behind an env flag once field names are confirmed.
    """
    try:
        from app.utils.helpers import fetch_nse_past_issues
        raw = fetch_nse_past_issues()
        if not raw:
            return jsonify(error="NSE returned no data — check cookies / network"), 500
        return jsonify(
            total_count=len(raw),
            sample=raw[:3],
            keys=list(raw[0].keys()) if raw else []
        )
    except Exception as e:
        current_app.logger.error(f"Error in debug NSE IPO: {e}")
        return jsonify(error=str(e)), 500