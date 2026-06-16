"""
Journal service for managing trade journal entries.
"""
from typing import List, Dict, Any, Optional
from app.database import get_db
from journal_math import compute_pnl_and_r


class JournalService:
    """Service for journal-related operations."""

    def get_journal_entries(self, status_filter: str = '', limit: Optional[int] = None,
                           offset: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get journal entries with optional filtering and pagination."""
        conn = get_db()
        try:
            c = conn.cursor()

            query = """
                SELECT id, ticker, name, date, setupLabel, swingband, entry, stop,
                       target1, target2, target3, riskAmount, qty, status,
                       exitPrice, exitDate, pnl, rAchieved, notes
                FROM trade_journal
            """
            where_clauses = []
            params = []

            if status_filter:
                where_clauses.append("LOWER(status) = ?")
                params.append(status_filter.strip().lower())

            if where_clauses:
                query += f" WHERE {' AND '.join(where_clauses)}"

            query += " ORDER BY id DESC"

            if limit is not None:
                try:
                    limit_val = int(limit)
                    query += " LIMIT ?"
                    params.append(limit_val)
                    if offset is not None:
                        try:
                            offset_val = int(offset)
                            query += " OFFSET ?"
                            params.append(offset_val)
                        except ValueError:
                            pass
                except ValueError:
                    pass

            c.execute(query, tuple(params))
            rows = c.fetchall()

            cols = ['id', 'ticker', 'name', 'date', 'setupLabel', 'swingband', 'entry', 'stop',
                    'target1', 'target2', 'target3', 'riskAmount', 'qty', 'status',
                    'exitPrice', 'exitDate', 'pnl', 'rAchieved', 'notes']
            return [dict(zip(cols, r)) for r in rows]
        finally:
            pass

    def create_journal_entry(self, entry_data: Dict[str, Any]) -> bool:
        """
        Create a new journal entry.
        Returns True if created, False if entry with that ID already exists.
        """
        trade_id = entry_data.get('id')
        if not trade_id:
            raise ValueError("id is required")

        conn = get_db()
        try:
            c = conn.cursor()

            # Check if entry already exists
            c.execute("SELECT id FROM trade_journal WHERE id = ?", (trade_id,))
            if c.fetchone():
                return False  # Already exists

            # Insert new entry
            c.execute("""
                INSERT OR IGNORE INTO trade_journal (
                    id, ticker, name, date, setupLabel, swingband, entry, stop,
                    target1, target2, target3, riskAmount, qty, status,
                    exitPrice, exitDate, pnl, rAchieved, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id, entry_data.get('ticker'), entry_data.get('name'), entry_data.get('date'),
                entry_data.get('setupLabel'), entry_data.get('swingband'), entry_data.get('entry', 0.0),
                entry_data.get('stop', 0.0), entry_data.get('target1', 0.0), entry_data.get('target2', 0.0),
                entry_data.get('target3', 0.0), entry_data.get('riskAmount', 0.0), entry_data.get('qty', 0),
                entry_data.get('status', 'open'), entry_data.get('exitPrice'), entry_data.get('exitDate'),
                entry_data.get('pnl'), entry_data.get('rAchieved'), entry_data.get('notes', '')
            ))
            conn.commit()
            return True  # Created new
        finally:
            pass

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

        conn = get_db()
        try:
            c = conn.cursor()

            # Calculate server-side P&L and R-Achieved when exitPrice is provided
            if 'exitPrice' in update_data and update_data['exitPrice'] is not None and str(update_data['exitPrice']).strip() != '':
                # Fetch original trade fields
                c.execute("SELECT entry, qty, stop FROM trade_journal WHERE id = ?", (trade_id,))
                orig = c.fetchone()
                if orig:
                    entry_price, qty, stop = orig

                    entry_val = update_data.get('entry')
                    if entry_val is None:
                        entry_val = entry_price or 0.0
                    entry_price = float(entry_val)

                    qty_val = update_data.get('qty')
                    if qty_val is None:
                        qty_val = qty or 0
                    qty = int(qty_val)

                    stop_val = update_data.get('stop')
                    if stop_val is None:
                        stop_val = stop or 0.0
                    stop = float(stop_val)

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

            fields = []
            params = []
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
                        val = None

                    fields.append(f"{key} = ?")
                    params.append(val)

            if not fields:
                raise ValueError("No fields to update")

            params.append(trade_id)
            query = f"UPDATE trade_journal SET {', '.join(fields)} WHERE id = ?"
            c.execute(query, tuple(params))

            if c.rowcount == 0:
                return False  # Not found

            conn.commit()
            return True  # Updated
        finally:
            pass

    def delete_journal_entry(self, trade_id: str) -> bool:
        """
        Delete a journal entry.
        Returns True if deleted, False if entry not found.
        """
        if not trade_id:
            raise ValueError("Trade ID is required")

        conn = get_db()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM trade_journal WHERE id = ?", (trade_id,))
            conn.commit()

            if c.rowcount == 0:
                return False  # Not found
            return True  # Deleted
        finally:
            pass


# Singleton instance
journal_service = JournalService()