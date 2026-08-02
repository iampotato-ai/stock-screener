"""
Signal Score API endpoint.

Provides GET /api/v1/signal-score/<symbol> for on-demand stock analysis.
"""
from flask import request, jsonify
from . import api_bp
import logging

logger = logging.getLogger(__name__)


@api_bp.route('/signal-score/<symbol>', methods=['GET'])
def get_signal_score(symbol: str):
    """
    Compute and return a full TechnicalSnapshot for a stock.

    Query Parameters:
        exchange (str): Stock exchange, default 'NSE'.
        include_ai (str): 'true'/'false' — include AI overlay (default 'true').
        range (str): Historical data range (default '6mo').

    Returns:
        JSON TechnicalSnapshot or error response.
    """
    try:
        exchange = request.args.get('exchange', 'NSE').upper()
        include_ai_str = request.args.get('include_ai', 'true').lower()
        include_ai = include_ai_str in ('true', '1', 'yes')
        range_str = request.args.get('range', '6mo')

        # Validate symbol
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        # Remove exchange prefix if present
        if clean_symbol.startswith('NSE:'):
            clean_symbol = clean_symbol[4:]
        elif clean_symbol.startswith('BO:'):
            clean_symbol = clean_symbol[3:]

        from app.services.signal_score import analyze_stock

        snapshot = analyze_stock(
            symbol=clean_symbol,
            exchange=exchange,
            include_ai=include_ai,
            range_str=range_str,
        )

        if not snapshot.get('success'):
            error_msg = snapshot.get('error', 'Unknown error')
            # Distinguish between "no data" and "service error"
            if 'Insufficient' in error_msg or 'not found' in error_msg.lower():
                return jsonify({'error': error_msg, 'symbol': clean_symbol}), 404
            return jsonify({'error': error_msg, 'symbol': clean_symbol}), 503

        return jsonify(snapshot), 200

    except Exception as e:
        logger.error("Error in signal-score endpoint for %s: %s", symbol, e)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500
