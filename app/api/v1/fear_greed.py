"""
India Fear & Greed Index API Endpoints.
"""
from flask import jsonify, current_app
from . import api_bp
from app.services.fear_greed_service import fear_greed_service


@api_bp.route('/fear-greed-index', methods=['GET'])
def get_fear_greed_index():
    """
    Get the latest India Fear & Greed Index.
    If no snapshot is in DB, computes one on the fly.
    """
    try:
        latest = fear_greed_service.get_latest_fear_greed()
        if not latest:
            # Compute live and persist
            computed = fear_greed_service.compute_fear_greed_index()
            fear_greed_service.save_fear_greed_snapshot(computed)
            latest = fear_greed_service.get_latest_fear_greed() or computed

        return jsonify(success=True, data=latest), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching Fear & Greed index: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/fear-greed-index/refresh', methods=['POST'])
def refresh_fear_greed_index():
    """
    Force a refresh of the India Fear & Greed Index snapshot.
    """
    try:
        computed = fear_greed_service.compute_fear_greed_index()
        fear_greed_service.save_fear_greed_snapshot(computed)
        latest = fear_greed_service.get_latest_fear_greed() or computed
        return jsonify(success=True, message="Fear & Greed index refreshed", data=latest), 200
    except Exception as e:
        current_app.logger.error(f"Error refreshing Fear & Greed index: {e}")
        return jsonify(error=str(e)), 500
