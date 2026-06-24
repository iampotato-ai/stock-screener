"""Bull Snort filter REST API endpoints.

Endpoints are gated behind the ``ENABLE_BULL_SNORT`` feature flag. When disabled,
the routes return a 404 with a clear error message. This allows safe rollout
and quick rollback without code changes.
"""

from flask import request, jsonify, current_app
from . import api_bp

from app.services import bull_snort_service

# ---------------------------------------------------------------------------
# Helper: feature flag check
# ---------------------------------------------------------------------------
def _feature_enabled():
    """Return True if the Bull Snort feature is enabled via config flag."""
    return current_app.config.get('ENABLE_BULL_SNORT', False)

# ---------------------------------------------------------------------------
# Single-symbol evaluation
# ---------------------------------------------------------------------------
@api_bp.route('/bull_snort/single', methods=['GET'])
def bull_snort_single():
    """Evaluate Bull Snort filter for a single symbol.

    Query parameter ``symbol`` is required. Returns JSON with ``data`` key – either
    the result dict from ``compute_bull_snort`` or ``null`` when the symbol does
    not satisfy the filter. Errors use appropriate HTTP status codes.
    """
    if not _feature_enabled():
        return jsonify({"error": "Bull Snort feature disabled"}), 404

    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({"error": "Missing 'symbol' query parameter"}), 400

    result = bull_snort_service.compute_bull_snort(symbol)
    return jsonify({"data": result}), 200

# ---------------------------------------------------------------------------
# Batch screening
# ---------------------------------------------------------------------------
@api_bp.route('/bull_snort/screen', methods=['GET', 'POST'])
def bull_snort_screen():
    """Screen symbols and return the passing results.

    Supports GET (screens all NSE database symbols) and POST (screens json-specified symbols).
    Query parameters (all optional):
      vol_avg_period     : int   (default: 20)
      vol_surge_min      : float (default: 3.0)
      close_position_min : float (default: 0.65)
      min_gap_history    : float (default: 10.0)
      max_current_gap    : float (default: 5.0)
      min_marketcap_cr   : float (default: None) - if provided, filters symbols by market cap >= value in Crores INR
    """
    if not _feature_enabled():
        return jsonify({"error": "Bull Snort feature disabled"}), 404

    # Extract symbols
    payload = {}
    if request.method == 'POST':
        if not request.is_json:
            return jsonify({"error": "Request body must be JSON"}), 400
        payload = request.get_json() or {}
        symbols = payload.get('symbols')
        if not isinstance(symbols, list):
            return jsonify({"error": "'symbols' must be a list"}), 400

    # Extract threshold parameters (same for GET and POST)
    try:
        def get_param(name, default_config_name, default_val, type_fn):
            # Check query parameter first
            val = request.args.get(name)
            # If not in query parameters and request is POST, check JSON payload
            if val is None and name in payload:
                val = payload[name]
            # Fallback to config value or default
            if val is None:
                return current_app.config.get(default_config_name, default_val)
            return type_fn(val)

        vol_avg_period = get_param('vol_avg_period', 'BULL_SNORT_VOL_AVG_PERIOD', 20, int)
        vol_surge_min = get_param('vol_surge_min', 'BULL_SNORT_VOL_SURGE_MIN', 3.0, float)
        close_position_min = get_param('close_position_min', 'BULL_SNORT_CLOSE_POSITION_MIN', 0.65, float)
        min_gap_history = get_param('min_gap_history', 'BULL_SNORT_MIN_GAP_HISTORY', 10.0, float)
        max_current_gap = get_param('max_current_gap', 'BULL_SNORT_MAX_CURRENT_GAP', 5.0, float)
        # min_marketcap_cr is optional - None means no market cap filter
        min_marketcap_cr = get_param('min_marketcap_cr', 'MIN_MARKETCAP_CR', None, float)
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid parameter value: {e}"}), 400

    # For GET requests, determine symbols based on market cap filter if provided
    if request.method == 'GET':
        from app.database import get_nse_symbols_by_marketcap
        if min_marketcap_cr is not None:
            # Convert CR to INR: 1 CR = 10,000,000 INR
            min_marketcap_inr = int(min_marketcap_cr * 10_000_000)
            symbols = get_nse_symbols_by_marketcap(min_marketcap_inr=min_marketcap_inr)
        else:
            # Use default (10B INR) - no additional filtering beyond cache default
            symbols = get_nse_symbols_by_marketcap()

    # Cache optimization: If GET request and all parameters match defaults (excluding min_marketcap_cr which is optional), return cache if available
    is_default = (
        vol_avg_period == current_app.config.get('BULL_SNORT_VOL_AVG_PERIOD', 20) and
        vol_surge_min == current_app.config.get('BULL_SNORT_VOL_SURGE_MIN', 3.0) and
        close_position_min == current_app.config.get('BULL_SNORT_CLOSE_POSITION_MIN', 0.65) and
        min_gap_history == current_app.config.get('BULL_SNORT_MIN_GAP_HISTORY', 10.0) and
        max_current_gap == current_app.config.get('BULL_SNORT_MAX_CURRENT_GAP', 5.0) and
        # min_marketcap_cr is not part of default check since None means "use default cache behavior"
        min_marketcap_cr is None
    )

    if request.method == 'GET' and is_default:
        cache = current_app.config.get('BULL_SNORT_CACHE')
        if cache and 'data' in cache:
            return jsonify({"data": cache['data']}), 200

    results = bull_snort_service.screen_bull_snort(
        symbols=symbols,
        vol_avg_period=vol_avg_period,
        vol_surge_min=vol_surge_min,
        close_position_min=close_position_min,
        min_gap_history=min_gap_history,
        max_current_gap=max_current_gap
    )

    # Populate cache if default GET request yielded results and cache was empty
    # Note: We only cache when min_marketcap_cr is None (using default cache behavior)
    if request.method == 'GET' and is_default and min_marketcap_cr is None:
        import pandas as pd
        current_app.config['BULL_SNORT_CACHE'] = {
            'data': results,
            'count': len(results),
            'refreshed': pd.Timestamp.now().isoformat()
        }

    return jsonify({"data": results}), 200