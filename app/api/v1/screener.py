"""
Screener API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.screener_service import screener_service


@api_bp.route('/scan', methods=['GET'])
@api_bp.route('/screener/scan', methods=['GET'])
def get_screener_scan():
    """
    Get the latest screener scan results.
    Query parameters:
    - limit: maximum number of results to return (default: 50)
    """
    try:
        limit = request.args.get('limit', '500').strip()
        try:
            limit = int(limit) if limit.isdigit() else 500
        except ValueError:
            limit = 500

        scan_data = screener_service.get_scan_results(limit=limit, live=True, full_response=True)
        if isinstance(scan_data, dict):
            return jsonify(
                success=True,
                count=len(scan_data['stocks']),
                data=scan_data['stocks'],
                total_scanned=scan_data.get('total_scanned', len(scan_data['stocks'])),
                total_matched=scan_data.get('total_matched', len(scan_data['stocks'])),
                universe=scan_data.get('universe', [])
            )
        else:
            return jsonify(
                success=True,
                count=len(scan_data),
                data=scan_data,
                total_scanned=len(scan_data),
                total_matched=len(scan_data),
                universe=[]
            )
    except Exception as e:
        current_app.logger.error(f"Error getting screener scan: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/stock/<ticker>', methods=['GET'])
@api_bp.route('/screener/stock/<ticker>', methods=['GET'])
def get_screener_stock_detail(ticker):
    """
    Get detailed information for a specific stock from the latest screener scan.
    """
    try:
        # Clean ticker format (remove NSE: or BO: prefixes if present)
        clean_ticker = ticker.upper()
        if clean_ticker.startswith("NSE:"):
            clean_ticker = clean_ticker[4:]
        elif clean_ticker.startswith("BO:"):
            clean_ticker = clean_ticker[3:]

        detail = screener_service.get_stock_details(clean_ticker)
        if detail is None:
            return jsonify(error=f"Stock {clean_ticker} not found in latest scan"), 404

        return jsonify(
            success=True,
            data=detail
        )
    except Exception as e:
        current_app.logger.error(f"Error getting screener stock detail for {ticker}: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/screener/refresh', methods=['POST'])
def refresh_screener_data():
    """
    Trigger a refresh of screener data.
    """
    try:
        started = screener_service.refresh_screener_data()
        if started:
            return jsonify(success=True, message="Background screener refresh started."), 202
        else:
            return jsonify(error="Refresh cooldown active. Please wait before triggering another refresh."), 429
    except Exception as e:
        current_app.logger.error(f"Error refreshing screener data: {e}")
        return jsonify(error=str(e)), 500