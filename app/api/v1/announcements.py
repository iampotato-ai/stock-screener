"""
Announcement processing API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.nlp_service import nlp_service

@api_bp.route('/announcements/process', methods=['POST'])
def process_announcement_endpoint():
    """
    Process a corporate announcement using NLP or fallback classification.
    Expected JSON: { "desc": "...", "text": "...", "attachment_url": "..." }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    desc = data.get('desc', '')
    text = data.get('text', '')
    attachment_url = data.get('attachment_url', '')

    # Basic validation
    if not desc and not text:
        return jsonify({"error": "Either desc or text must be provided"}), 400

    try:
        result = nlp_service.process_announcement(desc, text, attachment_url)
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        current_app.logger.error(f"Error processing announcement: {e}")
        return jsonify({"error": "Internal processing error"}), 500

@api_bp.route('/announcements/classify', methods=['POST'])
def classify_announcement_endpoint():
    """
    Legacy endpoint for keyword-based classification only.
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    desc = data.get('desc', '')
    text = data.get('text', '')

    from app.utils.helpers import classify_announcement
    cat, cat_name, imp, imp_name, sent, sent_name, reason = classify_announcement(desc, text)

    return jsonify({
        "success": True,
        "data": {
            "cat": cat,
            "cat_name": cat_name,
            "imp": imp,
            "imp_name": imp_name,
            "sent": sent,
            "sent_name": sent_name,
            "reason": reason
        }
    }), 200