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
    """
    if not _feature_enabled():
        return jsonify({"error": "Bull Snort feature disabled"}), 404

    # Extract threshold parameters (same for GET and POST)
    try:
        vol_avg_period = int(request.args.get('vol_avg_period', 20))
        vol_surge_min = float(request.args.get('vol_surge_min', 3.0))
        close_position_min = float(request.args.get('close_position_min', 0.65))
        min_gap_history = float(request.args.get('min_gap_history', 10.0))
        max_current_gap = float(request.args.get('max_current_gap', 5.0))
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid query parameter: {e}"}), 400

    if request.method == 'POST':
        if not request.is_json:
            return jsonify({"error": "Request body must be JSON"}), 400
        payload = request.get_json()
        symbols = payload.get('symbols')
        if not isinstance(symbols, list):
            return jsonify({"error": "'symbols' must be a list"}), 400
    else:
        # GET request: screen all database NSE symbols
        from app.database import get_nse_symbols
        symbols = get_nse_symbols()

    results = bull_snort_service.screen_bull_snort(
        symbols=symbols,
        vol_avg_period=vol_avg_period,
        vol_surge_min=vol_surge_min,
        close_position_min=close_position_min,
        min_gap_history=min_gap_history,
        max_current_gap=max_current_gap
    )
    return jsonify({"data": results}), 200
