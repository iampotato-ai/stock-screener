"""
API endpoints for Momentum Confidence Score™
"""
from flask import jsonify, request, current_app
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

        # Try to calculate on-demand to get the full detailed analysis (including points breakdown)
        try:
            calc_result = service.calculate_score_for_stock(symbol.upper(), exchange)
            if calc_result.get('success', False):
                clean_data = {k: v for k, v in calc_result.items() if k not in ('success', 'error')}
                # Map nested pillar scores to root-level keys for API consistency
                clean_data['technical_score'] = clean_data.get('pillar_scores', {}).get('technical', 0)
                clean_data['fundamental_score'] = clean_data.get('pillar_scores', {}).get('fundamental', 0)
                clean_data['momentum_score'] = clean_data.get('pillar_scores', {}).get('momentum', 0)
                clean_data['institutional_score'] = clean_data.get('pillar_scores', {}).get('institutional', 0)
                clean_data['risk_liquidity_score'] = clean_data.get('pillar_scores', {}).get('risk_liquidity', 0)
                # swing_score is already a root-level key from the service
                clean_data.setdefault('swing_score', None)
                return jsonify(clean_data), 200
            else:
                current_app.logger.warning(f"On-demand score calculation failed for {symbol}: {calc_result.get('error')}. Falling back to cache.")
        except Exception as calc_err:
            current_app.logger.warning(f"On-demand score calculation exception for {symbol}: {calc_err}. Falling back to cache.")

        # Fallback to the database cache
        score_data = service.get_latest_score(symbol.upper(), exchange)
        if score_data is not None:
            return jsonify(score_data), 200

        return jsonify({
            'error': 'Failed to calculate score and no cached record found',
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
    Get top scoring stocks matching the active screener universe.

    Query Parameters:
        limit: Maximum number of stocks to return (default: 300)
        exchange: Stock exchange to filter by (default: 'NSE')

    Returns:
        JSON list of stocks with scores
    """
    try:
        service = _get_scoring_service()
        limit = min(int(request.args.get('limit', 300)), 500)  # Support up to 500
        exchange = request.args.get('exchange', 'NSE')

        # Get active screener symbols
        from app.services.screener_service import screener_service
        scan_results = screener_service.get_scan_results(limit=limit, live=True)
        tickers = [s['ticker'].replace("NSE:", "").replace("BSE:", "") for s in scan_results if s.get('ticker')]

        if tickers:
            from app.models import MomentumScore
            from sqlalchemy import func
            from app.extensions import db

            # Subquery to get the latest date for each symbol
            subquery = db.session.query(
                MomentumScore.symbol,
                func.max(MomentumScore.date).label('max_date')
            ).filter(
                MomentumScore.symbol.in_(tickers),
                MomentumScore.exchange == exchange
            ).group_by(
                MomentumScore.symbol
            ).subquery()

            # Query the actual score records matching the latest date
            scores = db.session.query(MomentumScore).join(
                subquery,
                (MomentumScore.symbol == subquery.c.symbol) &
                (MomentumScore.date == subquery.c.max_date)
            ).all()

            scores_by_symbol = {score.symbol: score.to_dict() for score in scores}

            top_stocks = []
            for s in scan_results:
                ticker = s.get('ticker')
                if not ticker:
                    continue
                clean_ticker = ticker.replace("NSE:", "").replace("BSE:", "")
                if clean_ticker in scores_by_symbol:
                    item = dict(scores_by_symbol[clean_ticker])
                else:
                    # Return pending/placeholder record matching screener ticker
                    item = {
                        'symbol': clean_ticker,
                        'exchange': exchange,
                        'date': None,
                        'total_score': None,
                        'swing_score': None,
                        'technical_score': None,
                        'fundamental_score': None,
                        'momentum_score': None,
                        'institutional_score': None,
                        'risk_liquidity_score': None,
                        'badges': []
                    }
                # Attach current price and day metrics from screener scan result s
                item['close'] = s.get('close')
                item['change'] = s.get('change') if s.get('change') is not None else s.get('change_pct')
                item['high'] = s.get('high')
                item['low'] = s.get('low')
                top_stocks.append(item)
        else:
            # Fallback to general top stocks if no screener results are available yet
            top_stocks = service.get_top_stocks(limit, exchange)

        # Enrich all stocks with market data (close, change, high, low)
        top_stocks = _enrich_stocks_with_market_data(top_stocks)

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


def _enrich_stocks_with_market_data(stocks: list) -> list:
    """Ensure every stock dictionary in stocks has close, change, high, and low populated.
    Falls back to querying latest daily_bars records if missing from score/scan data.
    """
    if not stocks:
        return stocks

    missing_symbols = set()
    for s in stocks:
        sym = s.get('symbol') or s.get('ticker')
        if not sym:
            continue
        clean_sym = sym.replace("NSE:", "").replace("BSE:", "")
        # Mark symbols with any missing market metric for database lookup
        if s.get('close') is None or s.get('change') is None or s.get('high') is None or s.get('low') is None:
            missing_symbols.add(clean_sym)
            missing_symbols.add(f"{clean_sym}.NS")
            missing_symbols.add(f"{clean_sym}.BO")

    if missing_symbols:
        try:
            from app.models import DailyBar
            from app.extensions import db
            subq = db.session.query(
                DailyBar.symbol,
                db.func.max(DailyBar.trade_date).label('max_date')
            ).filter(DailyBar.symbol.in_(list(missing_symbols))).group_by(DailyBar.symbol).subquery()

            bars = db.session.query(DailyBar).join(
                subq,
                (DailyBar.symbol == subq.c.symbol) & (DailyBar.trade_date == subq.c.max_date)
            ).all()

            bar_map = {}
            for b in bars:
                clean = b.symbol.replace('.NS', '').replace('.BO', '')
                bar_map[clean] = b
                bar_map[b.symbol] = b

            for s in stocks:
                sym = s.get('symbol') or s.get('ticker') or ''
                clean_sym = sym.replace("NSE:", "").replace("BSE:", "")
                bar = bar_map.get(clean_sym) or bar_map.get(f"{clean_sym}.NS") or bar_map.get(f"{clean_sym}.BO")

                if s.get('close') is None and bar and bar.close is not None:
                    s['close'] = float(bar.close)

                if s.get('change') is None:
                    if s.get('change_pct') is not None:
                        s['change'] = float(s['change_pct'])
                    elif bar and bar.price_change_pct is not None:
                        s['change'] = float(bar.price_change_pct)

                if s.get('high') is None and bar and bar.high is not None:
                    s['high'] = float(bar.high)

                if s.get('low') is None and bar and bar.low is not None:
                    s['low'] = float(bar.low)
        except Exception as err:
            current_app.logger.warning(f"Error enriching stocks with market data: {err}")

    return stocks

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

@api_bp.route('/score/calculate_all', methods=['POST'])
def trigger_calculate_all():
    """
    Trigger background calculate_all_scores process.
    """
    try:
        from app.tasks.score_calculator import calculate_all_scores, get_mcs_job_status
        import threading
        from flask import current_app

        status = get_mcs_job_status()
        if status.get("status") == "running":
            return jsonify(error="A score calculation job is already running."), 409

        app = current_app._get_current_object()
        t = threading.Thread(target=calculate_all_scores, args=(app,), kwargs={"force": True})
        t.daemon = True
        t.start()

        return jsonify(success=True, message="Background scoring calculation started."), 202
    except Exception as e:
        return jsonify(error=str(e)), 500

@api_bp.route('/score/job_status', methods=['GET'])
def get_scoring_job_status():
    """
    Get progress stats of current background scoring process.
    """
    try:
        from app.tasks.score_calculator import get_mcs_job_status
        status = get_mcs_job_status()
        return jsonify(success=True, data=status), 200
    except Exception as e:
        return jsonify(error=str(e)), 500