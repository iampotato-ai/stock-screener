from flask import request, jsonify, current_app
from . import api_bp
from app.services.ai_service import ai_service

@api_bp.route('/analyze/sentiment', methods=['POST'])
def analyze_sentiment_endpoint():
    """
    Utility endpoint for financial sentiment analysis.
    Accepts JSON body: {"text": "..."}
    Returns JSON payload with sentiment, score, and summary.
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}
    text = data.get("text") or data.get("news")
    if not text:
        return jsonify(error="Missing parameter 'text' or 'news'"), 400

    try:
        result = ai_service.analyze_sentiment(text)
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error in sentiment analysis endpoint: {e}")
        return jsonify(error=str(e)), 500

@api_bp.route('/analyze/fundamentals', methods=['POST'])
def analyze_fundamentals_endpoint():
    """
    Utility endpoint for valuation, quality, and growth metric analysis.
    Accepts JSON body: {"metrics": {...}}
    Returns JSON payload with verdict, score, and summary.
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    data = request.get_json() or {}
    metrics = data.get("metrics")
    if not metrics or not isinstance(metrics, dict):
        return jsonify(error="Missing or invalid parameter 'metrics' (must be a dictionary)"), 400

    try:
        result = ai_service.analyze_fundamentals(metrics)
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error in fundamental analysis endpoint: {e}")
        return jsonify(error=str(e)), 500
