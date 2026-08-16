"""Multiyear Breakout REST API endpoints.

Endpoints:
- GET  /api/v1/multiyear-breakout          — return cached results (or trigger scan)
- POST /api/v1/multiyear-breakout/refresh   — force a fresh scan

Gated behind the ``ENABLE_MULTIYEAR_BREAKOUT`` feature flag.
"""

import json
import os
import logging

from flask import request, jsonify, current_app
from . import api_bp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: feature flag check
# ---------------------------------------------------------------------------

def _feature_enabled() -> bool:
    """Return True if the Multiyear Breakout feature is enabled via config flag."""
    return current_app.config.get('ENABLE_MULTIYEAR_BREAKOUT', True)


# ---------------------------------------------------------------------------
# GET  /api/v1/multiyear-breakout
# ---------------------------------------------------------------------------

@api_bp.route('/multiyear-breakout', methods=['GET'])
def get_multiyear_breakout():
    """Return cached multiyear breakout scan results.

    Query params (all optional):
        min_base_years      : int   (default: 5)
        breakout_window_days: int   (default: 10)
        force               : bool  (default: false) — bypass cache
    """
    if not _feature_enabled():
        return jsonify({"error": "Multiyear Breakout feature disabled"}), 404

    force = request.args.get('force', 'false').lower() == 'true'

    # Read filter params
    try:
        min_base_years = int(request.args.get(
            'min_base_years',
            current_app.config.get('MULTIYEAR_BREAKOUT_MIN_BASE_YEARS', 5)
        ))
        breakout_window_days = int(request.args.get(
            'breakout_window_days',
            current_app.config.get('MULTIYEAR_BREAKOUT_WINDOW_DAYS', 10)
        ))
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid parameter value: {e}"}), 400

    # Check if params match default (for cache eligibility)
    default_base = current_app.config.get('MULTIYEAR_BREAKOUT_MIN_BASE_YEARS', 5)
    default_window = current_app.config.get('MULTIYEAR_BREAKOUT_WINDOW_DAYS', 10)
    is_default = (min_base_years == default_base and breakout_window_days == default_window)

    # Serve from cache if available and not forced
    if not force:
        cache = current_app.config.get('MULTIYEAR_BREAKOUT_CACHE')
        if not cache or not cache.get('data'):
            # Try reading from disk
            cache_file = os.path.join(current_app.instance_path, 'multiyear_breakout_cache.json')
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache = json.load(f)
                        current_app.config['MULTIYEAR_BREAKOUT_CACHE'] = cache
                except Exception:
                    pass

        if cache and 'data' in cache:
            filtered_data = [
                item for item in cache['data']
                if item.get('years_below_ath', 0) >= min_base_years
            ]
            return jsonify({
                "data": filtered_data,
                "count": len(filtered_data),
                "total_scanned": cache.get('total_scanned', 1367),
                "refreshed": cache.get('refreshed'),
            }), 200

    # No cache or force — run a live scan
    return _run_scan_and_respond(min_base_years, breakout_window_days)


# ---------------------------------------------------------------------------
# POST /api/v1/multiyear-breakout/refresh
# ---------------------------------------------------------------------------

@api_bp.route('/multiyear-breakout/refresh', methods=['POST'])
def refresh_multiyear_breakout():
    """Force a fresh multiyear breakout scan.

    Triggers a live scan, updates the in-memory cache and disk cache,
    and returns results.
    """
    if not _feature_enabled():
        return jsonify({"error": "Multiyear Breakout feature disabled"}), 404

    min_base_years = current_app.config.get('MULTIYEAR_BREAKOUT_MIN_BASE_YEARS', 5)
    breakout_window_days = current_app.config.get('MULTIYEAR_BREAKOUT_WINDOW_DAYS', 10)

    # Allow overrides from JSON body
    if request.is_json:
        payload = request.get_json() or {}
        min_base_years = int(payload.get('min_base_years', min_base_years))
        breakout_window_days = int(payload.get('breakout_window_days', breakout_window_days))

    return _run_scan_and_respond(min_base_years, breakout_window_days)


# ---------------------------------------------------------------------------
# Internal: run scan and build response
# ---------------------------------------------------------------------------

def _run_scan_and_respond(min_base_years: int, breakout_window_days: int):
    """Run a live multiyear breakout scan, cache results, return JSON response."""
    from app.database import get_nse_symbols_by_marketcap
    from app.services.multiyear_breakout_service import scan_multiyear_breakouts
    import pandas as pd

    symbols = get_nse_symbols_by_marketcap(min_marketcap_inr=10_000_000_000)
    if not symbols:
        return jsonify({"data": [], "count": 0, "refreshed": None}), 200

    results = scan_multiyear_breakouts(
        symbols=symbols,
        min_base_years=min_base_years,
        breakout_window_days=breakout_window_days,
    )

    refreshed_time = pd.Timestamp.now().isoformat()
    cache_data = {
        "data": results,
        "count": len(results),
        "total_scanned": len(symbols),
        "refreshed": refreshed_time,
    }

    # Update in-memory cache
    if not current_app.config.get('TESTING'):
        current_app.config['MULTIYEAR_BREAKOUT_CACHE'] = cache_data

        # Persist to disk
        cache_file = os.path.join(current_app.instance_path, 'multiyear_breakout_cache.json')
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            logger.info("Saved Multiyear Breakout cache to disk (%d results)", len(results))
        except Exception as e:
            logger.error("Failed to save Multiyear Breakout cache to disk: %s", e)

    return jsonify(cache_data), 200
