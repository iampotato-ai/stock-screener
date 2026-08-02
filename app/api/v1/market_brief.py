"""
REST API endpoints for Daily Market Brief (Morning Summary Widget).
"""
from flask import jsonify, request, current_app
from . import api_bp
from app.services.market_brief_service import market_brief_service


@api_bp.route('/market-brief', methods=['GET'])
def get_daily_market_brief():
    """
    GET /api/v1/market-brief
    Returns the latest daily morning market brief summary.
    """
    try:
        force_refresh = request.args.get('force', 'false').lower() == 'true'
        brief = market_brief_service.get_or_create_daily_brief(force_refresh=force_refresh)
        return jsonify({
            "status": "success",
            "data": brief
        }), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching market brief: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@api_bp.route('/market-brief/refresh', methods=['POST'])
def refresh_daily_market_brief():
    """
    POST /api/v1/market-brief/refresh
    Force re-generates today's daily morning brief via AI or quantitative engine.
    """
    try:
        brief = market_brief_service.get_or_create_daily_brief(force_refresh=True)
        return jsonify({
            "status": "success",
            "message": "Market brief refreshed successfully",
            "data": brief
        }), 200
    except Exception as e:
        current_app.logger.error(f"Error refreshing market brief: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
