"""
API endpoints for Momentum Confidence Score™
"""
from flask import jsonify, request
from app.api.v1 import api_bp
from app.services.scoring_service import MomentumConfidenceScoreService

# Lazy-initialize the service inside the request context, not at import time.
# This prevents "Working outside of application context" errors if __init__
# ever accesses db in the future.
_scoring_service = None


def _get_scoring_service():
    """Return the module-level MomentumConfidenceScoreService, creating it on first use."""
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = MomentumConfidenceScoreService()
    return _scoring_service

@api_bp.route('/score/<string:symbol>', methods=['GET'])
def get_stock_score(symbol):
    """
    Get current Momentum Confidence Score for a stock.

    Args:
        symbol: Stock symbol (e.g., 'RELIANCE')

    Query Parameters:
        exchange: Stock exchange (default: 'NSE')

    Returns:
        JSON with score data or error message
    """
    exchange = request.args.get('exchange', 'NSE')

    try:
        service = _get_scoring_service()

        # Try the database cache first.
        score_data = service.get_latest_score(symbol.upper(), exchange)

        if score_data is not None:
            # to_dict() records have no 'success' / 'error' keys — they are
            # always valid if they exist in the DB.
            return jsonify(score_data), 200

        # No cached record found: calculate on-demand.
        calc_result = service.calculate_score_for_stock(symbol.upper(), exchange)
        if calc_result.get('success', False):
            # Strip internal-only fields before sending to client.
            clean_data = {k: v for k, v in calc_result.items() if k not in ('success', 'error')}
            return jsonify(clean_data), 200
        else:
            return jsonify({
                'error': calc_result.get('error', 'Failed to calculate score'),
                'symbol': symbol,
                'exchange': exchange
            }), 500

    except Exception as e:
        return jsonify({
            'error': str(e),
            'symbol': symbol,
            'exchange': exchange
        }), 500

@api_bp.route('/scores', methods=['GET'])
def get_top_scores():
    """
    Get top scoring stocks.

    Query Parameters:
        limit: Maximum number of stocks to return (default: 50)
        exchange: Stock exchange to filter by (default: 'NSE')

    Returns:
        JSON list of top stocks by score
    """
    try:
        service = _get_scoring_service()
        limit = min(int(request.args.get('limit', 50)), 100)  # Cap at 100
        exchange = request.args.get('exchange', 'NSE')

        top_stocks = service.get_top_stocks(limit, exchange)

        return jsonify({
            'stocks': top_stocks,
            'count': len(top_stocks),
            'exchange': exchange,
            'limit': limit
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@api_bp.route('/score/<string:symbol>/history', methods=['GET'])
def get_score_history(symbol):
    """
    Get historical scores for a stock.

    Args:
        symbol: Stock symbol

    Query Parameters:
        exchange: Stock exchange (default: 'NSE')
        days: Number of days of history to return (default: 30)

    Returns:
        JSON list of historical scores
    """
    exchange = request.args.get('exchange', 'NSE')
    days = min(int(request.args.get('days', 30)), 365)  # Cap at 1 year

    try:
        from datetime import date, timedelta
        from app.models import MomentumScore

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Query historical scores
        scores = MomentumScore.query.filter_by(
            symbol=symbol.upper(),
            exchange=exchange
        ).filter(
            MomentumScore.date >= start_date,
            MomentumScore.date <= end_date
        ).order_by(
            MomentumScore.date.desc()
        ).all()

        score_history = [score.to_dict() for score in scores]

        return jsonify({
            'symbol': symbol.upper(),
            'exchange': exchange,
            'days': days,
            'history': score_history,
            'count': len(score_history)
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e),
            'symbol': symbol,
            'exchange': exchange
        }), 500