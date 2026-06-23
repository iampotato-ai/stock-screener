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
@api_bp.route('/bull_snort/screen', methods=['POST'])
def bull_snort_screen():
    """Screen a list of symbols and return the passing results.

    Expects a JSON body with ``symbols`` as a list of ticker strings. Returns a
    JSON object with ``data`` containing the list of result dicts.
    """
    if not _feature_enabled():
        return jsonify({"error": "Bull Snort feature disabled"}), 404

    if not request.is_json:
        return jsonify({"error": "Request body must be JSON"}), 400
    payload = request.get_json()
    symbols = payload.get('symbols')
    if not isinstance(symbols, list):
        return jsonify({"error": "'symbols' must be a list"}), 400

    results = bull_snort_service.screen_bull_snort(symbols)
    return jsonify({"data": results}), 200
