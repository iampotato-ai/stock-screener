"""
Market Intelligence Events API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.market_intelligence.timeline.timeline_service import TimelineService

timeline_service = TimelineService()


@api_bp.route('/events', methods=['GET'])
def get_market_events():
    """
    Get unified timeline of news and market events for a stock.
    Query parameters:
    - symbol: Stock symbol (e.g. RELIANCE or NSE:RELIANCE)
    - type: Comma-separated list of event types to return (e.g., news,dividend,earnings)
    - limit: Max number of timeline items to return (default 20)
    """
    symbol = ""
    try:
        symbol = request.args.get('symbol', '').strip()
        if not symbol:
            return jsonify(error="Symbol required"), 400

        # Strip NSE prefix if present
        if symbol.startswith("NSE:"):
            symbol = symbol[4:]
        symbol = symbol.strip().upper()

        # Mark viewed in priority queue for scheduling priority decay
        from app.services.market_intelligence.jobs.priority_queue import priority_queue
        priority_queue.mark_viewed(symbol)

        event_types_str = request.args.get('type', '').strip()
        event_types = [t.strip().lower() for t in event_types_str.split(',')] if event_types_str else None

        limit = request.args.get('limit', 20, type=int)
        grouping = request.args.get('grouping', 'date_bracket').strip().lower()
        sentiment_filter = request.args.get('sentiment', '').strip().lower() or None

        timeline = timeline_service.get_timeline_for_symbol(
            symbol,
            event_types=event_types,
            limit=limit,
            grouping=grouping,
            sentiment_filter=sentiment_filter
        )

        return jsonify(
            success=True,
            data=timeline
        )
    except Exception as e:
        current_app.logger.error(f"Error getting market events for {symbol}: {e}")
        return jsonify(error=str(e)), 500
