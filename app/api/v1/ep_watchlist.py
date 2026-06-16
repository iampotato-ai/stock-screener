"""
EP Watchlist API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.watchlist_service import watchlist_service


@api_bp.route('/ep/watchlist', methods=['GET'])
def get_ep_watchlist():
    """
    Get all active EP watchlist entries.
    Returns a JSON with key 'watchlist' containing the list of entries.
    """
    try:
        watchlist = watchlist_service.get_active_ep_watchlist()
        return jsonify(watchlist=watchlist)
    except Exception as e:
        current_app.logger.error(f"Error getting EP watchlist: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/watchlist', methods=['POST'])
def add_to_ep_watchlist():
    """
    Add a symbol to the EP watchlist or update existing active entry.
    Expected JSON: {
        "symbol": "<stock_symbol>",
        "exchange": "<exchange>",   # optional, defaults to NSE
        "stop_price": <float>,      # optional
        "notes": "<notes>"          # optional
    }
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}
    symbol = data.get("symbol")
    exchange = data.get("exchange")
    stop_price = data.get("stop_price")
    notes = data.get("notes")

    if not symbol:
        return jsonify(error="Symbol is required"), 400

    try:
        is_new = watchlist_service.add_to_ep_watchlist(symbol, exchange, stop_price, notes)
        if is_new:
            return jsonify(success=True, message="Added to watchlist")
        else:
            return jsonify(success=True, message="Updated existing active watchlist entry")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error adding to EP watchlist: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/watchlist/remove', methods=['POST'])
def remove_from_ep_watchlist():
    """
    Remove a symbol from the active EP watchlist.
    Expected JSON: { "symbol": "<stock_symbol>" }
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}
    symbol = data.get("symbol")

    if not symbol:
        return jsonify(error="Symbol is required"), 400

    try:
        watchlist_service.remove_from_ep_watchlist(symbol)
        return jsonify(success=True, message="Removed symbol from active watchlist")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error removing from EP watchlist: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep/watchlist/trigger', methods=['POST'])
def trigger_ep_watchlist():
    """
    Get the entry price and exchange for an active EP watchlist trigger.
    Expected JSON: { "symbol": "<stock_symbol>" }
    Returns JSON with success and message.
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}
    symbol = data.get("symbol")

    if not symbol:
        return jsonify(error="Symbol is required"), 400

    try:
        result = watchlist_service.trigger_ep_watchlist(symbol)
        return jsonify(result)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error triggering EP watchlist: {e}")
        return jsonify(error=str(e)), 500