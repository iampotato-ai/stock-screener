"""
Journal API endpoints.
"""
from flask import request, jsonify, current_app
from . import api_bp
from app.services.journal_service import journal_service


@api_bp.route('/journal', methods=['GET'])
def get_journal():
    """
    Get journal entries with optional filtering and pagination.
    Query parameters:
    - status: filter by status (e.g., 'open', 'closed')
    - limit: maximum number of entries to return
    - offset: number of entries to skip
    """
    status_filter = request.args.get('status', '').strip()
    limit = request.args.get('limit', '').strip()
    offset = request.args.get('offset', '').strip()

    # Convert limit and offset to int if provided
    limit_int = int(limit) if limit.isdigit() else None
    offset_int = int(offset) if offset.isdigit() else None

    try:
        journal_entries = journal_service.get_journal_entries(
            status_filter=status_filter,
            limit=limit_int,
            offset=offset_int
        )
        if request.path.startswith('/api/v1'):
            return jsonify(success=True, data=journal_entries)
        else:
            return jsonify(journal_entries)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error getting journal: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/journal', methods=['POST'])
def create_journal_entry():
    """
    Create a new journal entry.
    Expected JSON: journal entry object with all required fields.
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    entry_data = request.get_json() or {}

    if not entry_data.get('id'):
        return jsonify(error="id is required"), 400

    try:
        is_created = journal_service.create_journal_entry(entry_data)
        if is_created:
            if request.path.startswith('/api/v1'):
                return jsonify(success=True, message="Journal entry created"), 201
            else:
                return jsonify(success=True, message="Journal entry created"), 200
        else:
            return jsonify(error="Journal entry with this ID already exists"), 409
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error creating journal entry: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/journal/<trade_id>', methods=['PUT'])
def update_journal_entry(trade_id):
    """
    Update an existing journal entry.
    Expected JSON: journal entry object with fields to update.
    """
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json"), 400

    update_data = request.get_json() or {}

    # Add the trade_id to the data for validation in service
    if 'id' not in update_data:
        update_data['id'] = trade_id

    try:
        is_updated = journal_service.update_journal_entry(trade_id, update_data)
        if is_updated:
            return jsonify(success=True, message="Journal entry updated"), 200
        else:
            return jsonify(error="Journal entry not found"), 404
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error updating journal entry: {e}")
        return jsonify(error=str(e)), 500


@api_bp.route('/journal/<trade_id>', methods=['DELETE'])
def delete_journal_entry(trade_id):
    """
    Delete a journal entry.
    """
    try:
        is_deleted = journal_service.delete_journal_entry(trade_id)
        if is_deleted:
            return jsonify(success=True, message="Journal entry deleted"), 200
        else:
            return jsonify(error="Journal entry not found"), 404
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        current_app.logger.error(f"Error deleting journal entry: {e}")
        return jsonify(error=str(e)), 500