"""
Watchlist API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.watchlist_service import WatchlistService

# Instantiate the service
watchlist_service = WatchlistService()


@api_bp.route('/watchlist', methods=['GET'])
def get_watchlist():
    """
    Get all watchlist sections and their items.
    Returns a list of sections, each with an 'items' list.
    """
    sections = watchlist_service.get_watchlist_sections()
    for section in sections:
        section['items'] = watchlist_service.get_watchlist_items(section['id'])
    return jsonify({"success": True, "data": sections}), 200


@api_bp.route('/watchlist/sections', methods=['POST'])
def create_watchlist_section():
    """
    Create a new watchlist section.
    Expected JSON: { "id": <section_id>, "name": "<section_name>" }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    sec_id = data.get('id')
    sec_name = data.get('name')

    if sec_id is None or not sec_name:
        return jsonify({"error": "Section id and name are required"}), 400

    try:
        watchlist_service.create_watchlist_section(sec_id, sec_name)
        return jsonify({"success": True, "message": "Section created"}), 200
    except Exception as e:
        current_app.logger.error(f"Error creating watchlist section: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/watchlist/sections/<int:sec_id>', methods=['PUT'])
def rename_watchlist_section(sec_id):
    """
    Rename a watchlist section.
    Expected JSON: { "name": "<new_section_name>" }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    sec_name = data.get('name')

    if not sec_name:
        return jsonify({"error": "Section name is required"}), 400

    try:
        watchlist_service.rename_watchlist_section(sec_id, sec_name)
        return jsonify({"success": True, "message": "Section renamed"}), 200
    except Exception as e:
        current_app.logger.error(f"Error renaming watchlist section: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/watchlist/sections/<int:sec_id>', methods=['DELETE'])
def delete_watchlist_section(sec_id):
    """
    Delete a watchlist section and all its items.
    """
    try:
        watchlist_service.delete_watchlist_section(sec_id)
        return jsonify({"success": True, "message": "Section deleted"}), 200
    except Exception as e:
        current_app.logger.error(f"Error deleting watchlist section: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/watchlist/items', methods=['POST'])
def add_watchlist_item():
    """
    Add a ticker to a watchlist section.
    Expected JSON: { "section_id": <section_id>, "ticker": "<ticker_symbol>" }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    section_id = data.get('section_id')
    ticker = data.get('ticker')

    if section_id is None or not ticker:
        return jsonify({"error": "Section id and ticker are required"}), 400

    try:
        watchlist_service.add_watchlist_item(section_id, ticker)
        return jsonify({"success": True, "message": "Item added"}), 200
    except Exception as e:
        current_app.logger.error(f"Error adding watchlist item: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/watchlist/items', methods=['DELETE'])
def delete_watchlist_item():
    """
    Remove a ticker from a watchlist section.
    Expected JSON: { "section_id": <section_id>, "ticker": "<ticker_symbol>" }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    section_id = data.get('section_id')
    ticker = data.get('ticker')

    if section_id is None or not ticker:
        return jsonify({"error": "Section id and ticker are required"}), 400

    try:
        watchlist_service.delete_watchlist_item(section_id, ticker)
        return jsonify({"success": True, "message": "Item removed"}), 200
    except Exception as e:
        current_app.logger.error(f"Error deleting watchlist item: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/watchlist/sections/reorder', methods=['PUT'])
def reorder_watchlist_sections():
    """
    Reorder watchlist sections.
    Expected JSON: { "order": [<section_id_1>, <section_id_2>, ...] }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    order = data.get('order')

    if not order or not isinstance(order, list):
        return jsonify({"error": "order (list) is required"}), 400

    try:
        watchlist_service.reorder_watchlist_sections(order)
        return jsonify({"success": True, "message": "Sections reordered"}), 200
    except Exception as e:
        current_app.logger.error(f"Error reordering watchlist sections: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/watchlist/sections/<int:section_id>/reorder', methods=['PUT'])
def reorder_watchlist_items(section_id):
    """
    Reorder items within a watchlist section.
    Expected JSON: { "stocks": [<ticker_1>, <ticker_2>, ...] }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    stocks = data.get('stocks')

    if stocks is None or not isinstance(stocks, list):
        return jsonify({"error": "stocks (list) is required"}), 400

    try:
        watchlist_service.reorder_watchlist_items(section_id, stocks)
        return jsonify({"success": True, "message": "Items reordered"}), 200
    except Exception as e:
        current_app.logger.error(f"Error reordering watchlist items: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/migrate-local-data', methods=['POST'])
def migrate_local_data():
    """
    Migrate local data (watchlists and journal entries).
    Expected JSON: { "watchlist_sections": [...], "journal": [...] }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json() or {}
    sections = data.get('watchlist_sections', [])
    journal = data.get('journal', [])

    try:
        from app.services.journal_service import journal_service

        # Migrate watchlists
        for sec in sections:
            sec_id = sec.get('id')
            sec_name = sec.get('name')
            if sec_id and sec_name:
                watchlist_service.create_watchlist_section(sec_id, sec_name)
                for idx, sym in enumerate(sec.get('stocks', [])):
                    if sym:
                        watchlist_service.add_watchlist_item(sec_id, sym)

        # Migrate journal
        for entry in journal:
            trade_id = entry.get('id')
            if trade_id:
                journal_service.create_journal_entry(entry)

        return jsonify({"success": True, "message": "Local data migrated"}), 200
    except Exception as e:
        current_app.logger.error(f"Error migrating local data: {e}")
        return jsonify({"error": "Internal server error"}), 500