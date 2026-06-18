"""
Watchlist service for managing watchlist sections, items, and EP watchlist.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.extensions import db
from app.models import WatchlistSection, WatchlistItem, EpWatchlist, EpFeature


class WatchlistService:
    """Service for watchlist-related operations."""

    # Regular watchlist methods
    def get_watchlist_sections(self) -> List[Dict[str, Any]]:
        """Get all watchlist sections ordered by position and id."""
        sections = db.session.query(WatchlistSection).order_by(WatchlistSection.position.asc(), WatchlistSection.id.asc()).all()
        return [{"id": sec.id, "name": sec.name} for sec in sections]

    def create_watchlist_section(self, sec_id: int, sec_name: str) -> None:
        """Create or replace a watchlist section."""
        sec = db.session.query(WatchlistSection).filter(WatchlistSection.id == str(sec_id)).first()
        if sec:
            sec.name = sec_name
        else:
            sec = WatchlistSection(id=str(sec_id), name=sec_name)
            db.session.add(sec)
        db.session.commit()

    def rename_watchlist_section(self, sec_id: int, sec_name: str) -> None:
        """Rename a watchlist section."""
        sec = db.session.query(WatchlistSection).filter(WatchlistSection.id == str(sec_id)).first()
        if sec:
            sec.name = sec_name
            db.session.commit()

    def delete_watchlist_section(self, sec_id: int) -> None:
        """Delete a watchlist section and its items."""
        sec = db.session.query(WatchlistSection).filter(WatchlistSection.id == str(sec_id)).first()
        if sec:
            db.session.delete(sec)
            db.session.commit()

    def get_watchlist_items(self, section_id: int) -> List[str]:
        """Get all ticker strings in a watchlist section ordered by position and id."""
        items = db.session.query(WatchlistItem).filter(WatchlistItem.section_id == str(section_id)).order_by(WatchlistItem.position.asc(), WatchlistItem.id.asc()).all()
        return [item.ticker for item in items]

    def add_watchlist_item(self, section_id: int, ticker: str) -> None:
        """Add a ticker to a watchlist section."""
        ticker_upper = ticker.upper().strip()
        existing = db.session.query(WatchlistItem).filter(
            WatchlistItem.section_id == str(section_id),
            WatchlistItem.ticker == ticker_upper
        ).first()
        
        if not existing:
            # Get max position
            max_pos_row = db.session.query(db.func.max(WatchlistItem.position)).filter(
                WatchlistItem.section_id == str(section_id)
            ).first()
            max_pos = max_pos_row[0] if max_pos_row and max_pos_row[0] is not None else 0
            
            new_item = WatchlistItem(
                section_id=str(section_id),
                ticker=ticker_upper,
                position=max_pos + 1
            )
            db.session.add(new_item)
            db.session.commit()

    def delete_watchlist_item(self, section_id: int, ticker: str) -> None:
        """Remove a ticker from a watchlist section."""
        db.session.query(WatchlistItem).filter(
            WatchlistItem.section_id == str(section_id),
            WatchlistItem.ticker == ticker.upper().strip()
        ).delete(synchronize_session=False)
        db.session.commit()

    def reorder_watchlist_sections(self, order: List[int]) -> None:
        """Reorder watchlist sections based on the provided list of section IDs."""
        for idx, sec_id in enumerate(order):
            sec = db.session.query(WatchlistSection).filter(WatchlistSection.id == str(sec_id)).first()
            if sec:
                sec.position = idx
        db.session.commit()

    def reorder_watchlist_items(self, section_id: int, order: List[str]) -> None:
        """Reorder items within a watchlist section based on the provided list of ticker symbols."""
        for idx, ticker in enumerate(order):
            item = db.session.query(WatchlistItem).filter(
                WatchlistItem.section_id == str(section_id),
                WatchlistItem.ticker == ticker.upper().strip()
            ).first()
            if item:
                item.position = idx
        db.session.commit()

    # EP Watchlist methods - replicating original logic from app.py
    def get_active_ep_watchlist(self) -> List[Dict[str, Any]]:
        """Get all active EP watchlist entries with original column set."""
        items = db.session.query(EpWatchlist).filter(EpWatchlist.status == 'ACTIVE').order_by(EpWatchlist.catalyst_date.desc()).all()
        # Ensure we return only the expected columns in the dict format
        cols = [
            'id', 'symbol', 'exchange', 'catalyst_date', 'ep_type', 'status', 'trigger_type',
            'entry_price', 'stop_price', 'target_price', 'entry_date', 'days_on_watch', 'notes', 'ep_score'
        ]
        
        result = []
        for item in items:
            d = item.to_dict()
            # Filter dict keys to only include those in cols
            filtered_d = {k: d.get(k) for k in cols}
            result.append(filtered_d)
        return result

    def add_to_ep_watchlist(self, symbol: str, exchange: str, stop_price: Any, notes: str) -> bool:
        """
        Add a symbol to the EP watchlist or update existing active entry.
        Mirrors the original app.py add_to_ep_watchlist() function.
        """
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")
        exchange = (exchange or "NSE").upper().strip()
        notes = notes or ""

        # Process stop_price
        if stop_price is not None and stop_price != "":
            try:
                stop_price = float(stop_price)
            except (ValueError, TypeError):
                raise ValueError("Invalid stop price")
        else:
            stop_price = None

        existing = db.session.query(EpWatchlist).filter(
            EpWatchlist.symbol == symbol,
            EpWatchlist.status == 'ACTIVE'
        ).first()

        if existing:
            # Update existing active entry
            existing.stop_price = stop_price
            existing.notes = notes
            existing.updated_at = datetime.utcnow()
            db.session.commit()
            return False  # Updated existing
        else:
            # Fetch ep_type and ep_score from ep_features
            feat = db.session.query(EpFeature).filter(EpFeature.symbol == symbol).order_by(EpFeature.feature_date.desc()).first()

            if feat:
                ep_type = feat.ep_type
                ep_score = feat.ep_score
                catalyst_date = feat.feature_date
            else:
                ep_type = "Manual"
                ep_score = 0.55
                catalyst_date = datetime.now().date()

            entry_price = None
            
            # Insert new entry
            new_entry = EpWatchlist(
                symbol=symbol,
                exchange=exchange,
                catalyst_date=catalyst_date,
                ep_type=ep_type,
                status='ACTIVE',
                ep_score=ep_score,
                entry_price=entry_price,
                stop_price=stop_price,
                notes=notes,
                catalyst_close=entry_price
            )
            db.session.add(new_entry)
            db.session.commit()
            return True  # Added new

    def remove_from_ep_watchlist(self, symbol: str) -> None:
        """Remove a symbol from the active EP watchlist."""
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")
        
        items = db.session.query(EpWatchlist).filter(
            EpWatchlist.symbol == symbol,
            EpWatchlist.status == 'ACTIVE'
        ).all()
        
        for item in items:
            item.status = 'REMOVED'
            item.updated_at = datetime.utcnow()
        db.session.commit()

    def trigger_ep_watchlist(self, symbol: str) -> Dict[str, Any]:
        """
        Get the entry price and exchange for an active EP watchlist trigger.
        Mirrors the original app.py trigger_ep_watchlist() function.
        Returns a dict with success and message.
        """
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")

        item = db.session.query(EpWatchlist).filter(
            EpWatchlist.symbol == symbol,
            EpWatchlist.status == 'ACTIVE'
        ).first()

        if not item:
            raise ValueError("No active watchlist entry found for this symbol")

        today_price = item.entry_price
        today_date = datetime.now().date()

        item.status = 'TRIGGERED'
        item.trigger_type = 'MANUAL'
        item.entry_price = today_price
        item.entry_date = today_date
        item.updated_at = datetime.utcnow()
        db.session.commit()

        # The original returns a JSON with success and message.
        return {"success": True, "message": "Watchlist entry marked as TRIGGERED"}

    def increment_ep_watchlist_days(self) -> None:
        """Increment days_on_watch for all active EP watchlist items and expire old ones."""
        active_items = db.session.query(EpWatchlist).filter(EpWatchlist.status == 'ACTIVE').all()
        today_date = datetime.now().date()
        for item in active_items:
            item.days_on_watch = (item.days_on_watch or 0) + 1
            item.last_incremented_date = today_date
            if item.days_on_watch > 20:
                item.status = 'EXPIRED'
            item.updated_at = datetime.utcnow()
        db.session.commit()


# Singleton instance
watchlist_service = WatchlistService()