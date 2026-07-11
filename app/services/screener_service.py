"""
Screener service for managing stock screening operations.
"""
import time
import threading
from datetime import date
from typing import List, Dict, Any, Optional
from flask import current_app
from app.models import ScanPriceLog, ScanHistory
from app.extensions import db
import requests
from app.services.rs_service import rs_service


class ScreenerService:
    """Service for stock screening-related operations."""

    def __init__(self):
        self.refresh_lock = threading.Lock()
        self.last_refresh_time = 0.0

    def _get_latest_scan_date(self) -> Optional[date]:
        """Get the latest scan date from ScanHistory using SQLAlchemy."""
        try:
            latest_date_result = db.session.query(ScanHistory.date).order_by(
                ScanHistory.date.desc()
            ).first()
            return latest_date_result[0] if latest_date_result else None
        except Exception as e:
            current_app.logger.error(f"Error getting latest scan date: {e}")
            return None

    def get_scan_results(self, limit: int = 500, live: bool = False, full_response: bool = False) -> Any:
        """
        Get the latest scan results.
        If live is True, performs a live scan via TradingView.
        Otherwise, returns latest scan results from the database.

        Args:
            limit: Maximum number of results to return
            live: Whether to perform a live scan
            full_response: Whether to return full response metadata including universe and counts

        Returns:
            List of stock dictionaries from the scan, or a dict containing metadata if full_response is True.
        """
        if live:
            try:
                from app.api.v1.legacy_routes import scan_stocks
                response = scan_stocks()
                response_data = response.get_json()
                if response_data and 'stocks' in response_data:
                    results = []
                    for s in response_data['stocks']:
                        s['setup_label'] = s.get('setupLabel', '')
                        results.append(s)
                    
                    # Calculate RS scores for live scan results
                    results = rs_service.calculate_rs_scores(results)
                    # expose RS rating under the UI‑expected key
                    for stock in results:
                        stock['relative_strength_rating'] = stock.get('rs_score')
                    
                    if full_response:
                        return {
                            'stocks': results[:limit],
                            'total_scanned': response_data.get('total_scanned', len(results)),
                            'total_matched': response_data.get('total_matched', len(results)),
                            'universe': response_data.get('universe', [])
                        }
                    return results[:limit]
            except Exception as e:
                current_app.logger.error(f"Error performing live scan: {e}")
                # Fall back to database results if live scan fails

        try:
            from app.database import get_latest_scan_results
            scan_results = get_latest_scan_results(limit)
            
            # Convert sqlite3.Row objects to dictionaries and clean keys
            results = []
            for r in scan_results:
                stock = dict(r)
                stock['clean_ticker'] = stock.get('ticker', '')
                stock['setup_label'] = stock.get('setupLabel', '')
                results.append(stock)
            
            # Calculate RS scores for database results
            results = rs_service.calculate_rs_scores(results)
            # expose RS rating under the UI‑expected key
            for stock in results:
                stock['relative_strength_rating'] = stock.get('rs_score')
            
            if full_response:
                return {
                    'stocks': results,
                    'total_scanned': len(results),
                    'total_matched': len(results),
                    'universe': []
                }
            return results
        except Exception as e:
            current_app.logger.error(f"Error getting scan results: {e}")
            if full_response:
                return {
                    'stocks': [],
                    'total_scanned': 0,
                    'total_matched': 0,
                    'universe': []
                }
            return []

    def get_stock_details(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a specific stock.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary containing stock details or None if not found
        """
        try:
            # Clean ticker format (remove NSE: or BO: prefixes if present)
            clean_ticker = ticker.upper()
            if clean_ticker.startswith("NSE:"):
                clean_ticker = clean_ticker[4:]
            elif clean_ticker.startswith("BO:"):
                clean_ticker = clean_ticker[3:]
            
            # Get latest scan data for this ticker
            from app.database import get_stock_details
            stock_data = get_stock_details(clean_ticker)
            
            if stock_data:
                # Convert to dict and add computed fields
                stock = dict(stock_data)
                stock['clean_ticker'] = stock.get('ticker', '')
                # expose RS rating under UI key for detail view
                stock['relative_strength_rating'] = stock.get('rs_score')
                # Ensure price data is present; otherwise treat as not found
                if not stock.get('price_data'):
                    return None
                return stock
            return None
        except Exception as e:
            current_app.logger.error(f"Error getting stock details for {ticker}: {e}")
            return None

    def refresh_screener_data(self) -> bool:
        """
        Trigger a refresh of screener data.
        
        Returns:
            True if refresh was started, False if cooldown active or refresh in progress
        """
        # Acquire lock to prevent concurrent refreshes
        if not self.refresh_lock.acquire(blocking=False):
            return False
        try:
            current_time = time.time()
            # Cooldown check – only if we have a real numeric timestamp
            if isinstance(current_time, (int, float)):
                if current_time - self.last_refresh_time < 60:  # 1 minute cooldown
                    return False
                # Record start time for cooldown tracking
                self.last_refresh_time = current_time
            # Define background refresh task
            def refresh_task():
                try:
                    from app.api.v1.legacy_routes import refresh_ep_screener
                    refresh_ep_screener()
                    current_app.logger.info("Screener data refresh completed")
                except Exception as e:
                    # On failure, allow retry by resetting timestamp
                    self.last_refresh_time = 0.0
                    current_app.logger.error(f"Error refreshing EP screener: {e}")
            # Launch in a daemon thread
            thread = threading.Thread(target=refresh_task, daemon=True)
            thread.start()
            return True
        finally:
            # Release lock irrespective of outcome
            self.refresh_lock.release()


# Singleton instance
screener_service = ScreenerService()