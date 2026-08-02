"""
Insider Transactions REST API endpoints.

Provides:
- GET /api/v1/insider-transactions/<symbol> (Single stock detailed summary & transaction feed)
- GET /api/v1/insider-transactions/summary (Batch summary for screener enrichment)
"""
from flask import request, jsonify
from . import api_bp
import logging

logger = logging.getLogger(__name__)


@api_bp.route('/insider-transactions/<symbol>', methods=['GET'])
def get_stock_insider_transactions(symbol: str):
    """
    Get detailed insider transactions, net promoter buying, and badges for a stock.

    Query Parameters:
        exchange (str): Stock exchange, default 'NSE'.

    Returns:
        JSON with metrics, badges, insider_score, and recent_transactions list.
    """
    try:
        exchange = request.args.get('exchange', 'NSE').upper()
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        from app.services.insider_service import get_stock_insider_summary

        data = get_stock_insider_summary(clean_symbol, exchange=exchange)
        return jsonify(data), 200

    except Exception as e:
        logger.error("Error fetching insider transactions for %s: %s", symbol, e)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@api_bp.route('/insider-transactions/summary', methods=['GET'])
def get_batch_insider_transactions():
    """
    Get batch summary of insider transactions for a list of symbols.

    Query Parameters:
        symbols (str): Comma-separated list of symbols (e.g. 'RELIANCE,INFY,TCS').

    Returns:
        JSON dictionary mapping symbol to insider metrics summary.
    """
    try:
        symbols_raw = request.args.get('symbols', '')
        if not symbols_raw:
            return jsonify({'error': 'Comma-separated symbols parameter is required'}), 400

        symbols_list = [s.strip().upper() for s in symbols_raw.split(',') if s.strip()]

        from app.services.insider_service import get_batch_insider_summary

        summary_dict = get_batch_insider_summary(symbols_list)
        return jsonify(summary_dict), 200

    except Exception as e:
        logger.error("Error fetching batch insider transactions summary: %s", e)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500
