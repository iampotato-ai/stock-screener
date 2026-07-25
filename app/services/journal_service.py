"""
Journal service for managing trade journal entries.
"""
from typing import List, Dict, Any, Optional
from app.extensions import db
from app.models import TradeJournal
from app.utils.journal_math import compute_pnl_and_r
from app.services.journal_bias import analyze_biases as _compute_biases


class JournalService:
    """Service for journal-related operations."""

    def get_journal_entries(self, status_filter: str = '', limit: Optional[int] = None,
                           offset: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get journal entries with optional filtering and pagination."""
        query = db.session.query(TradeJournal)

        if status_filter:
            query = query.filter(db.func.lower(TradeJournal.status) == status_filter.strip().lower())

        query = query.order_by(TradeJournal.id.desc())

        if limit is not None:
            query = query.limit(limit)
            if offset is not None:
                query = query.offset(offset)

        entries = query.all()
        return [entry.to_dict() for entry in entries]

    def create_journal_entry(self, entry_data: Dict[str, Any]) -> bool:
        """
        Create a new journal entry.
        Returns True if created, False if entry with that ID already exists.
        """
        trade_id = entry_data.get('id')
        if not trade_id:
            raise ValueError("id is required")

        # Check if entry already exists
        existing = db.session.query(TradeJournal).filter(TradeJournal.id == trade_id).first()
        if existing:
            return False  # Already exists

        # Insert new entry
        new_entry = TradeJournal(
            id=trade_id,
            ticker=entry_data.get('ticker'),
            name=entry_data.get('name'),
            date=entry_data.get('date'),
            setupLabel=entry_data.get('setupLabel'),
            swingband=entry_data.get('swingband'),
            entry=entry_data.get('entry', 0.0),
            stop=entry_data.get('stop', 0.0),
            target1=entry_data.get('target1', 0.0),
            target2=entry_data.get('target2', 0.0),
            target3=entry_data.get('target3', 0.0),
            riskAmount=entry_data.get('riskAmount', 0.0),
            qty=entry_data.get('qty', 0),
            status=entry_data.get('status', 'open'),
            exitPrice=entry_data.get('exitPrice'),
            exitDate=entry_data.get('exitDate'),
            pnl=entry_data.get('pnl'),
            rAchieved=entry_data.get('rAchieved'),
            notes=entry_data.get('notes', '')
        )
        db.session.add(new_entry)
        db.session.commit()
        return True  # Created new

    def update_journal_entry(self, trade_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update an existing journal entry.
        Returns True if updated, False if entry not found.
        """
        if not trade_id:
            raise ValueError("Trade ID is required")

        # Check for ID mismatch
        if 'id' in update_data and update_data['id'] != trade_id:
            raise ValueError("Trade ID mismatch between URL and body")

        # Fetch original trade entry
        entry = db.session.query(TradeJournal).filter(TradeJournal.id == trade_id).first()
        if not entry:
            return False

        # Calculate server-side P&L and R-Achieved when exitPrice is provided
        if 'exitPrice' in update_data and update_data['exitPrice'] is not None and str(update_data['exitPrice']).strip() != '':
            entry_price = update_data.get('entry')
            if entry_price is None:
                entry_price = entry.entry or 0.0
            entry_price = float(entry_price)

            qty = update_data.get('qty')
            if qty is None:
                qty = entry.qty or 0
            qty = int(qty)

            stop = update_data.get('stop')
            if stop is None:
                stop = entry.stop or 0.0
            stop = float(stop)

            exit_price = float(update_data['exitPrice'])
            pnl, r_achieved = compute_pnl_and_r(entry_price, stop, qty, exit_price,
                                              risk_amount=update_data.get('riskAmount'))

            update_data['pnl'] = pnl
            update_data['rAchieved'] = r_achieved
            update_data['status'] = 'closed'

        # Prepare update fields
        type_map = {
            'qty': int,
            'entry': float,
            'stop': float,
            'target1': float,
            'target2': float,
            'target3': float,
            'riskAmount': float,
            'exitPrice': float,
            'pnl': float,
            'rAchieved': float
        }

        nullable_fields = {'exitPrice', 'exitDate', 'pnl', 'rAchieved', 'notes'}
        validated_updates = {}

        for key in ['status', 'exitPrice', 'exitDate', 'pnl', 'rAchieved', 'notes', 'entry', 'stop',
                   'target1', 'target2', 'target3', 'riskAmount', 'qty', 'ticker', 'name', 'date',
                   'setupLabel', 'swingband']:
            if key in update_data:
                val = update_data[key]
                if val is not None and str(val).strip() != '':
                    if key in type_map:
                        try:
                            val = type_map[key](val)
                        except (ValueError, TypeError):
                            raise ValueError(f"Invalid value type for {key}")
                else:
                    if key not in nullable_fields:
                        raise ValueError(f"{key} cannot be empty or null")
                    val = None

                validated_updates[key] = val

        if not validated_updates:
            raise ValueError("No fields to update")

        # Apply validated updates to the entry
        for key, val in validated_updates.items():
            setattr(entry, key, val)

        db.session.commit()
        return True  # Updated

    def delete_journal_entry(self, trade_id: str) -> bool:
        """
        Delete a journal entry.
        Returns True if deleted, False if entry not found.
        """
        if not trade_id:
            raise ValueError("Trade ID is required")

        entry = db.session.query(TradeJournal).filter(TradeJournal.id == trade_id).first()
        if not entry:
            return False  # Not found

        db.session.delete(entry)
        db.session.commit()
        return True  # Deleted

    def analyze_biases(self) -> Dict[str, Any]:
        """
        Run all four bias diagnostics on the current journal.

        Fetches all journal entries (open + closed) and delegates to
        journal_bias.analyze_biases() for pure-Python computation.

        Returns:
            Dict containing bias_scores, severity ratings, recommendations,
            and a plain-English summary. See journal_bias.analyze_biases()
            for the full response schema.
        """
        entries = self.get_journal_entries()
        return _compute_biases(entries)


# Singleton instance
journal_service = JournalService()