"""
Alert API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.alert_service import alert_service


@api_bp.route('/telegram-alert', methods=['POST'])
def send_telegram_alert():
    """
    Send a custom Telegram alert.
    Expected JSON: {
        "message": "<string>"
    }
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}
    message = data.get('message')

    if not message:
        return jsonify(error="Message is required"), 400

    try:
        success = alert_service.send_telegram_alert(message)
        if success:
            return jsonify(success=True, message="Telegram alert sent"), 200
        else:
            return jsonify(error="Failed to send Telegram alert"), 500
    except Exception as e:
        current_app.logger.error(f"Error sending telegram alert: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/watchlist-trigger', methods=['POST'])
def send_watchlist_trigger_alert():
    """
    Send a watchlist trigger alert via Telegram.
    Expected JSON: {
        "symbol": "<string>",
        "exchange": "<string>",
        "entry_price": <float>
    }
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}
    symbol = data.get('symbol')
    exchange = data.get('exchange')
    entry_price = data.get('entry_price')

    if not symbol:
        return jsonify(error="Symbol is required"), 400
    if not exchange:
        return jsonify(error="Exchange is required"), 400
    if entry_price is None:
        return jsonify(error="Entry price is required"), 400

    try:
        success = alert_service.send_watchlist_trigger_alert(symbol, exchange, float(entry_price))
        if success:
            return jsonify(success=True, message="Watchlist trigger alert sent"), 200
        else:
            return jsonify(error="Failed to send watchlist trigger alert"), 500
    except (ValueError, TypeError) as e:
        return jsonify(error=f"Invalid data type: {str(e)}"), 400
    except Exception as e:
        current_app.logger.error(f"Error sending watchlist trigger alert: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/ep-refresh-alerts', methods=['POST'])
def send_ep_refresh_alerts():
    """
    Send a batch of EP refresh alerts via Telegram.
    Expected JSON: {
        "alerts": ["<string>", "<string>", ...]
    }
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}
    alerts = data.get('alerts', [])

    if not isinstance(alerts, list):
        return jsonify(error="Alerts must be a list"), 400

    try:
        sent_count = alert_service.send_ep_refresh_alerts(alerts)
        return jsonify(
            success=True,
            message=f"Sent {sent_count} of {len(alerts)} EP refresh alerts",
            sent_count=sent_count
        ), 200
    except Exception as e:
        current_app.logger.error(f"Error sending EP refresh alerts: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/config', methods=['GET'])
def get_alert_config():
    """
    Get current alert configuration.
    """
    try:
        config = alert_service.get_alert_config()
        return jsonify(success=True, config=config), 200
    except Exception as e:
        current_app.logger.error(f"Error getting alert config: {e}")
        return jsonify(error=str(e)), 500