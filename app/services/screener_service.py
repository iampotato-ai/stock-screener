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

    def _get_local_stage_analysis(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Attempt to calculate stage classification locally using daily_bars table to avoid HTTP requests.
        
        Tries the plain ticker first, then falls back to .NS and .BO suffix variants to handle
        mismatches between screener ticker format (plain) and daily_bars storage format (suffixed).
        """
        try:
            from app.models import DailyBar
            from app.services.stage_analyzer.engine import analyze

            # Try the ticker as-is first, then with exchange suffixes (daily_bars may store RUBICON.NS)
            candidate_symbols = [ticker, f"{ticker}.NS", f"{ticker}.BO"]
            bars = []
            for sym in candidate_symbols:
                bars = db.session.query(DailyBar).filter(
                    DailyBar.symbol == sym
                ).order_by(DailyBar.trade_date.asc()).all()
                if bars:
                    break  # Use whichever format has data

            if len(bars) >= 5:
                history = [{
                    "date": bar.trade_date.strftime('%Y-%m-%d') if hasattr(bar.trade_date, 'strftime') else str(bar.trade_date),
                    "open": float(bar.open or 0.0),
                    "high": float(bar.high or 0.0),
                    "low": float(bar.low or 0.0),
                    "close": float(bar.close or 0.0),
                    "volume": int(bar.volume or 0)
                } for bar in bars]
                
                closes = [day["close"] for day in history]
                sma21 = sum(closes[-21:]) / 21 if len(closes) >= 21 else None
                sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
                stock_data = {"ticker": ticker, "history": history, "SMA21": sma21, "SMA50": sma50}
                return analyze(stock_data)
            elif bars:
                current_app.logger.debug(
                    f"Stage analysis skipped for {ticker}: only {len(bars)} bars available (need >=5)"
                )
        except Exception as e:
            current_app.logger.warning(f"Failed local stage analyzer query for {ticker}: {e}")
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
                    # expose RS rating under the UI‑expected key and enrich with Stage info
                    from flask import has_app_context
                    stage_results = current_app.config.get('STAGE_ANALYSIS_RESULTS', {}) if has_app_context() else {}
                    for stock in results:
                        stock['relative_strength_rating'] = stock.get('rs_score')
                        ticker = stock.get('clean_ticker') or stock.get('ticker') or stock.get('symbol', '')
                        if ticker.startswith("NSE:"):
                            ticker = ticker[4:]
                        elif ticker.startswith("BO:"):
                            ticker = ticker[3:]
                        ticker = ticker.upper()
                        
                        analysis = stage_results.get(ticker)
                        if analysis and 'score' in analysis:
                            stock['stage_label'] = analysis['score'].get('stage', 'Unknown')
                        else:
                            # Lazy-load stage analysis locally from daily_bars (never make blocking network requests)
                            inline_analysis = self._get_local_stage_analysis(ticker)
                            if inline_analysis:
                                if has_app_context():
                                    stage_results[ticker] = inline_analysis
                                stock['stage_label'] = inline_analysis['score'].get('stage', 'Unknown')
                            else:
                                stock['stage_label'] = 'Unknown'
                    
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
            # expose RS rating under the UI‑expected key and enrich with Stage info
            from flask import has_app_context
            stage_results = current_app.config.get('STAGE_ANALYSIS_RESULTS', {}) if has_app_context() else {}
            for stock in results:
                stock['relative_strength_rating'] = stock.get('rs_score')
                ticker = stock.get('clean_ticker') or stock.get('ticker') or stock.get('symbol', '')
                if ticker.startswith("NSE:"):
                    ticker = ticker[4:]
                elif ticker.startswith("BO:"):
                    ticker = ticker[3:]
                ticker = ticker.upper()
                
                analysis = stage_results.get(ticker)
                if analysis and 'score' in analysis:
                    stock['stage_label'] = analysis['score'].get('stage', 'Unknown')
                else:
                    # Lazy-load stage analysis locally from daily_bars (never make blocking network requests)
                    inline_analysis = self._get_local_stage_analysis(ticker)
                    if inline_analysis:
                        if has_app_context():
                            stage_results[ticker] = inline_analysis
                        stock['stage_label'] = inline_analysis['score'].get('stage', 'Unknown')
                    else:
                        stock['stage_label'] = 'Unknown'
            
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