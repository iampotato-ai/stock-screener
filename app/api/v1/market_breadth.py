"""
Market breadth API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.market_breadth_service import market_breadth_service


@api_bp.route('/breadth-snapshot', methods=['POST'])
def save_breadth_snapshot():
    """
    Save a market breadth snapshot.
    Expected JSON: {
        "advances": <int>,
        "declines": <int>,
        "unchanged": <int>,
        "pct_sma21": <float>,
        "pct_sma50": <float>,
        "pct_52high": <float>,
        "avg_recommend": <float>,
        "regime_score": <int>,
        "regime_band": "<string>"
    }
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}

    # Validate required fields
    required_fields = ['advances', 'declines', 'unchanged', 'pct_sma21', 'pct_sma50',
                      'pct_52high', 'avg_recommend', 'regime_score', 'regime_band']
    for field in required_fields:
        if field not in data:
            return jsonify(error=f"Field '{field}' is required"), 400

    try:
        market_breadth_service.save_breadth_snapshot(
            advances=int(data['advances']),
            declines=int(data['declines']),
            unchanged=int(data['unchanged']),
            pct_sma21=float(data['pct_sma21']),
            pct_sma50=float(data['pct_sma50']),
            pct_52high=float(data['pct_52high']),
            avg_recommend=float(data['avg_recommend']),
            regime_score=int(data['regime_score']),
            regime_band=str(data['regime_band'])
        )
        return jsonify(success=True, message="Breadth snapshot saved"), 200
    except (ValueError, TypeError) as e:
        return jsonify(error=f"Invalid data type: {str(e)}"), 400
    except Exception as e:
        current_app.logger.error(f"Error saving breadth snapshot: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/breadth-history', methods=['GET'])
def get_breadth_history():
    """
    Get market breadth history.
    Query parameters:
    - limit: number of records to return (default: 30)
    """
    try:
        limit = request.args.get('limit', '30')
        try:
            limit_int = int(limit)
        except ValueError:
            limit_int = 30

        history = market_breadth_service.get_breadth_history(limit=limit_int)
        return jsonify(history=history)
    except Exception as e:
        current_app.logger.error(f"Error getting breadth history: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/breadth-latest', methods=['GET'])
def get_latest_breadth_snapshot():
    """
    Get the most recent market breadth snapshot.
    """
    try:
        snapshot = market_breadth_service.get_latest_breadth_snapshot()
        if snapshot:
            return jsonify(snapshot)
        else:
            return jsonify(error="No breadth data available"), 404
    except Exception as e:
        current_app.logger.error(f"Error getting latest breadth snapshot: {e}")
        return jsonify(error=str(e)), 500