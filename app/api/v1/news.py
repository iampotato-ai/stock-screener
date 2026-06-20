"""
News API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.news_service import news_service


@api_bp.route('/news', methods=['GET'])
def get_news():
    """
    Get news for a specific symbol.
    Query parameters:
    - symbol: Stock symbol (e.g., RELIANCE, or NSE:RELIANCE)
    """
    try:
        symbol = request.args.get('symbol', '').strip()
        if not symbol:
            return jsonify(error="Symbol required"), 400

        result = news_service.get_news_for_symbol(symbol)
        # Check if there's an error in the result
        if "error" in result:
            return jsonify(error=result["error"]), 400

        return jsonify(
            success=True,
            data=result
        )
    except Exception as e:
        current_app.logger.error(f"Error getting news for {symbol}: {e}")
        return jsonify(error=str(e)), 500