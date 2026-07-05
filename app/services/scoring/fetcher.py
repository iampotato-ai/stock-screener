"""
Stock data fetcher for Momentum Confidence Score.
Implements isolated TradingView API calls and Yahoo Finance integration
to populate StockDataSchema with real market data.
"""

import json
import math
import time
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional
from datetime import datetime, date
import logging

from app.services.scoring.fetcher_utils import (
    compute_ema, compute_macd, compute_adx, compute_supertrend,
    compute_volatility, compute_yoy_growth, compute_rsi
)
from app.utils.technical import classify_technical_pattern

logger = logging.getLogger(__name__)


class StockDataFetcher:
    """
    Fetches stock data from multiple sources to populate StockDataSchema.
    Uses layered approach: TradingView (technical/basic) -> Yahoo Finance (fundamentals/OHLCV) -> DB fallback -> Defaults.
    """

    def __init__(self):
        """Initialize the stock data fetcher."""
        # These would normally come from config, but we'll use defaults for now
        self.tradingview_url = "https://scanner.tradingview.com/india/scan"
        self.yahoo_finance_base = "https://query1.finance.yahoo.com/v10/finance/quoteSummary"
        self.yahoo_chart_base = "https://query1.finance.yahoo.com/v8/finance/chart"
        self.request_timeout = 10
        self.rate_limit_delay = 0.1  # 100ms between Yahoo requests

    def fetch_stock_data(self, symbol: str, exchange: str = 'NSE',
                         isolated_tv_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetch complete stock data for a symbol using layered approach.

        Args:
            symbol: Stock symbol (e.g., 'RELIANCE')
            exchange: Stock exchange (default: 'NSE')
            isolated_tv_data: Pre-fetched TradingView data for batch efficiency

        Returns:
            Dictionary conforming to StockDataSchema
        """
        # Initialize result with defaults
        result = self._get_defaults(symbol, exchange)

        try:
            # Layer 1: Use isolated TradingView data if provided (batch efficient)
            if isolated_tv_data and symbol in isolated_tv_data:
                tv_data = isolated_tv_data[symbol]
                result.update(self._extract_technical_from_tv(tv_data))
                logger.debug(f"Used isolated TradingView data for {symbol}")
            else:
                # Fallback: individual TradingView call (less efficient)
                tv_data = self._fetch_individual_tv_data(symbol)
                if tv_data:
                    result.update(self._extract_technical_from_tv(tv_data))

            # Layer 2: Yahoo Finance fundamentals
            yahoo_fundamentals = self._fetch_yahoo_fundamentals(symbol)
            if yahoo_fundamentals:
                result.update(self._extract_fundamentals_from_yahoo(yahoo_fundamentals))

            # Layer 3: Yahoo Finance OHLCV for technical indicators
            yahoo_ohlcv = self._fetch_yahoo_ohlcv(symbol)
            if yahoo_ohlcv:
                result.update(self._extract_technical_from_ohlcv(yahoo_ohlcv))

            # Layer 4: Database fallback for price (if needed)
            # This would be implemented if we had direct DB access for price history

            # Calculate golden cross (50 EMA > 200 EMA) after merging all layers
            if result.get('ema_50') and result.get('ema_200'):
                result['golden_cross'] = float(result['ema_50']) > float(result['ema_200'])

            # Apply any missing field defaults
            result = self._apply_missing_defaults(result, symbol, exchange)

            logger.debug(f"Successfully fetched data for {symbol}")
            return result

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            # Return defaults on error to ensure scoring continues
            return self._get_defaults(symbol, exchange)

    def fetch_isolated_tv_data(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Make an isolated batch POST request to TradingView for multiple symbols.
        This avoids coupling with the main swing screener.

        Args:
            symbols: List of stock symbols to fetch (e.g., ['RELIANCE', 'TCS'])

        Returns:
            Dictionary mapping symbol to TradingView data
        """
        if not symbols:
            return {}

        try:
            # Prepare TradingView payload
            # Format symbols for TradingView (NSE:RELIANCE format)
            # Remove any existing exchange prefix to prevent double-prefixing (e.g. NSE:NSE:RELIANCE)
            cleaned_symbols = [sym.replace('NSE:', '').replace('BSE:', '').replace('BO:', '') for sym in symbols]
            tv_symbols = [f"NSE:{sym}" for sym in cleaned_symbols]

            payload = {
                "symbols": {
                    "tickers": tv_symbols,
                    "query": {
                        "types": []
                    }
                },
                "columns": [
                    "name", "close", "market_cap_basic", "price_52_week_high",
                    "price_52_week_low", "RSI", "EMA50", "Perf.W", "Perf.1M", "Perf.3M",
                    "volume", "average_volume_10d_calc", "average_volume_30d_calc"
                ]
            }

            # Make request to TradingView
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self.tradingview_url,
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )

            with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
                result_data = json.loads(response.read().decode('utf-8'))

            # Parse response
            tv_data = {}
            if 'data' in result_data:
                for item in result_data['data']:
                    clean_sym = None
                    cols = []
                    
                    if isinstance(item, dict):
                        raw_ticker = item.get('s', '')
                        clean_sym = raw_ticker.replace('NSE:', '').replace('BSE:', '')
                        cols = item.get('d', [])
                        # In the real TV response dict format, cols matches columns list:
                        # cols[0] = name, cols[1] = close, cols[2] = market_cap_basic, etc.
                        if clean_sym and cols:
                            tv_data[clean_sym] = {
                                'close': cols[1] if len(cols) > 1 else None,
                                'market_cap_basic': cols[2] if len(cols) > 2 else None,
                                'price_52_week_high': cols[3] if len(cols) > 3 else None,
                                'price_52_week_low': cols[4] if len(cols) > 4 else None,
                                'RSI': cols[5] if len(cols) > 5 else None,
                                'EMA50': cols[6] if len(cols) > 6 else None,
                                'Perf.W': cols[7] if len(cols) > 7 else None,
                                'Perf.1M': cols[8] if len(cols) > 8 else None,
                                'Perf.3M': cols[9] if len(cols) > 9 else None,
                                'volume': cols[10] if len(cols) > 10 else None,
                                'average_volume_10d_calc': cols[11] if len(cols) > 11 else None,
                                'average_volume_30d_calc': cols[12] if len(cols) > 12 else None
                            }
                    elif isinstance(item, list) and len(item) > 0:
                        sym = item[0]
                        clean_sym = sym.replace('NSE:', '').replace('BSE:', '')
                        # In the list format (used in tests), item[0] = symbol, item[1] = close, etc.
                        if clean_sym:
                            tv_data[clean_sym] = {
                                'close': item[1] if len(item) > 1 else None,
                                'market_cap_basic': item[2] if len(item) > 2 else None,
                                'price_52_week_high': item[3] if len(item) > 3 else None,
                                'price_52_week_low': item[4] if len(item) > 4 else None,
                                'RSI': item[5] if len(item) > 5 else None,
                                'EMA50': item[6] if len(item) > 6 else None,
                                'Perf.W': item[7] if len(item) > 7 else None,
                                'Perf.1M': item[8] if len(item) > 8 else None,
                                'Perf.3M': item[9] if len(item) > 9 else None,
                                'volume': item[10] if len(item) > 10 else None,
                                'average_volume_10d_calc': item[11] if len(item) > 11 else None,
                                'average_volume_30d_calc': item[12] if len(item) > 12 else None
                            }

            logger.info(f"Fetched isolated TradingView data for {len(tv_data)} symbols")
            return tv_data

        except Exception as e:
            logger.error(f"Error fetching isolated TradingView data: {e}")
            return {}

    def _fetch_individual_tv_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch TradingView data for a single symbol (fallback method)."""
        try:
            tv_data = self.fetch_isolated_tv_data([symbol])
            return tv_data.get(symbol)
        except Exception as e:
            logger.error(f"Error fetching individual TradingView data for {symbol}: {e}")
            return None

    def _fetch_yahoo_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch fundamental data from Yahoo Finance."""
        try:
            # Respect rate limit
            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

            # Yahoo Finance expects .NS suffix for NSE stocks
            yahoo_symbol = f"{symbol}.NS"
            url = f"{self.yahoo_finance_base}/{yahoo_symbol}?modules=financialData,defaultKeyStatistics,incomeStatementHistory"

            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )

            with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
                data = json.loads(response.read().decode('utf-8'))

            return data

        except Exception as e:
            logger.error(f"Error fetching Yahoo Finance fundamentals for {symbol}: {e}")
            return None

    def _fetch_yahoo_ohlcv(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch OHLCV data from Yahoo Finance for technical indicators."""
        try:
            # Respect rate limit
            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

            # Yahoo Finance expects .NS suffix for NSE stocks
            yahoo_symbol = f"{symbol}.NS"
            # Get 1 year of daily data
            url = f"{self.yahoo_chart_base}/{yahoo_symbol}?interval=1d&range=1y"

            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )

            with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
                data = json.loads(response.read().decode('utf-8'))

            return data

        except Exception as e:
            logger.error(f"Error fetching Yahoo Finance OHLCV for {symbol}: {e}")
            return None

    def _extract_technical_from_tv(self, tv_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract technical fields from TradingView data."""
        result = {}

        if not tv_data:
            return result

        # Extract basic technical data
        close = tv_data.get('close')
        if close is not None:
            result['price'] = float(close)

        ema50 = tv_data.get('EMA50')
        if ema50 is not None:
            result['ema_50'] = float(ema50)

        rsi = tv_data.get('RSI')
        if rsi is not None:
            result['rsi'] = float(rsi)

        perf_1m = tv_data.get('Perf.1M')
        perf_3m = tv_data.get('Perf.3M')
        if perf_1m is not None and perf_3m is not None:
            # momentum_acceleration = Perf.1M - Perf.3M / 3
            result['momentum_acceleration'] = float(perf_1m) - (float(perf_3m) / 3.0)

        high_52w = tv_data.get('price_52_week_high')
        low_52w = tv_data.get('price_52_week_low')
        if close is not None and high_52w is not None and high_52w > 0:
            result['price_vs_52w_high'] = float(close) / float(high_52w)
            result['price_vs_52w_high_pct'] = (float(close) / float(high_52w)) * 100.0

        # Market cap in crores
        market_cap = tv_data.get('market_cap_basic')
        if market_cap is not None:
            result['market_cap_cr'] = float(market_cap) / 1e7  # Convert to crores

        return result

    def _extract_fundamentals_from_yahoo(self, yahoo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fundamental fields from Yahoo Finance data."""
        result = {}

        if not yahoo_data or 'quoteSummary' not in yahoo_data:
            return result

        try:
            result_data = yahoo_data['quoteSummary']['result'][0]
        except (KeyError, IndexError, TypeError):
            return result

        # Extract financialData
        financial_data = result_data.get('financialData', {})
        if financial_data:
            # ROE
            roe_data = financial_data.get('returnOnEquity', {})
            if roe_data and 'raw' in roe_data:
                result['roe'] = float(roe_data['raw'])

            # ROCE (use ROE as proxy if not available)
            roce_data = financial_data.get('returnOnCapitalEmployed', {})
            if roce_data and 'raw' in roce_data:
                result['roce'] = float(roce_data['raw'])
            elif 'roe' in result:
                result['roce'] = result['roe']  # Proxy

            # Debt to Equity
            debt_eq_data = financial_data.get('debtToEquity', {})
            if debt_eq_data and 'raw' in debt_eq_data:
                # Yahoo provides debt-to-equity as decimal ratio
                result['debt_to_equity'] = float(debt_eq_data['raw'])

            # Operating Margin
            op_margin_data = financial_data.get('operatingMargins', {})
            if op_margin_data and 'raw' in op_margin_data:
                result['operating_margin'] = float(op_margin_data['raw'])

            # Net Margin
            net_margin_data = financial_data.get('profitMargins', {})
            if net_margin_data and 'raw' in net_margin_data:
                result['net_margin'] = float(net_margin_data['raw'])

            # Operating Cash Flow (convert to crores)
            ocf_data = financial_data.get('operatingCashflow', {})
            if ocf_data and 'raw' in ocf_data:
                result['operating_cash_flow'] = float(ocf_data['raw']) / 1e7  # Convert to crores

        # Extract defaultKeyStatistics
        default_stats = result_data.get('defaultKeyStatistics', {})
        if default_stats:
            # Held percent institutions (proxy for promoter holding)
            held_institutions = default_stats.get('heldPercentInstitutions', {})
            if held_institutions and 'raw' in held_institutions:
                # Promoter holding % = (100 - institutional %) approximately
                result['promoter_holding_pct'] = (100.0 - float(held_institutions['raw']))

        # Extract incomeStatementHistory for YoY growth
        income_stmt = result_data.get('incomeStatementHistory', {})
        if income_stmt and 'incomeStatementHistory' in income_stmt:
            history_list = income_stmt['incomeStatementHistory']
            if isinstance(history_list, list) and len(history_list) >= 2:
                # Extract revenue and net profit values
                revenues = []
                profits = []
                for stmt in history_list:
                    if isinstance(stmt, dict):
                        revenue = stmt.get('totalRevenue', {}).get('raw')
                        net_income = stmt.get('netIncome', {}).get('raw')
                        if revenue is not None:
                            revenues.append(float(revenue))
                        if net_income is not None:
                            profits.append(float(net_income))

                # Calculate YoY growth
                if len(revenues) >= 2:
                    result['revenue_growth_yoy'] = compute_yoy_growth(revenues)
                if len(profits) >= 2:
                    result['profit_growth_yoy'] = compute_yoy_growth(profits)

        return result

    def _extract_technical_from_ohlcv(self, yahoo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract technical indicators from Yahoo Finance OHLCV data."""
        result = {}

        if not yahoo_data or 'chart' not in yahoo_data:
            return result

        try:
            chart_result = yahoo_data['chart']['result'][0]
        except (KeyError, IndexError, TypeError):
            return result

        # Extract price data
        indicators = chart_result.get('indicators', {})
        quote = indicators.get('quote', [{}])[0] if indicators.get('quote') else {}

        raw_opens = quote.get('open', [])
        raw_highs = quote.get('high', [])
        raw_lows = quote.get('low', [])
        raw_closes = quote.get('close', [])
        raw_volumes = quote.get('volume', [])

        min_len = min(len(raw_opens), len(raw_highs), len(raw_lows), len(raw_closes), len(raw_volumes))
        history_list = []
        for i in range(min_len):
            o = raw_opens[i]
            h = raw_highs[i]
            l = raw_lows[i]
            c = raw_closes[i]
            v = raw_volumes[i]
            if o is not None and h is not None and l is not None and c is not None and v is not None:
                history_list.append({
                    'open': float(o),
                    'high': float(h),
                    'low': float(l),
                    'close': float(c),
                    'volume': float(v)
                })

        if len(history_list) < 2:
            return result

        opens = [day['open'] for day in history_list]
        closes = [day['close'] for day in history_list]
        highs = [day['high'] for day in history_list]
        lows = [day['low'] for day in history_list]
        volumes = [day['volume'] for day in history_list]

        # Calculate EMA20, EMA100, EMA200
        if len(closes) >= 20:
            ema_20_values = compute_ema(closes, 20)
            if ema_20_values and not math.isnan(ema_20_values[-1]):
                result['ema_20'] = ema_20_values[-1]

        if len(closes) >= 100:
            ema_100_values = compute_ema(closes, 100)
            if ema_100_values and not math.isnan(ema_100_values[-1]):
                result['ema_100'] = ema_100_values[-1]

        if len(closes) >= 200:
            ema_200_values = compute_ema(closes, 200)
            if ema_200_values and not math.isnan(ema_200_values[-1]):
                result['ema_200'] = ema_200_values[-1]

        # Calculate MACD
        if len(closes) >= 26:
            macd_line, signal_line, _ = compute_macd(closes)
            if macd_line and not math.isnan(macd_line[-1]):
                result['macd'] = macd_line[-1]
            if signal_line and not math.isnan(signal_line[-1]):
                result['macd_signal'] = signal_line[-1]

        # Calculate ADX
        if len(highs) >= 14 and len(lows) >= 14 and len(closes) >= 14:
            adx_values = compute_adx(highs, lows, closes)
            if adx_values and not math.isnan(adx_values[-1]):
                result['adx'] = adx_values[-1]

        # Calculate Supertrend
        if len(highs) >= 10 and len(lows) >= 10 and len(closes) >= 10:
            supertrend, direction = compute_supertrend(highs, lows, closes)
            if supertrend and not math.isnan(supertrend[-1]):
                result['supertrend'] = supertrend[-1]
            if direction and len(direction) > 0:
                result['supertrend_direction'] = direction[-1]

        # Calculate RSI
        if len(closes) >= 14:
            rsi_values = compute_rsi(closes)
            if rsi_values and not math.isnan(rsi_values[-1]):
                result['rsi'] = rsi_values[-1]  # Override TradingView RSI if Yahoo calculation available

        # Calculate volatility
        if len(closes) >= 30:
            volatility = compute_volatility(closes)
            result['volatility_30d'] = volatility

        # Calculate average daily volume
        if len(volumes) >= 30:
            avg_volume = sum(volumes[-30:]) / min(30, len(volumes))
            result['avg_daily_volume'] = int(avg_volume)

        # Volume ratio (today's volume / 30-day average)
        if len(volumes) >= 31:  # Need at least 30 days of history + today
            today_volume = volumes[-1] if volumes else 0
            avg_volume_30d = sum(volumes[-31:-1]) / 30 if len(volumes) >= 31 else 0
            if avg_volume_30d > 0:
                result['volume_ratio'] = today_volume / avg_volume_30d

        # Higher highs and higher lows (20-period)
        if len(highs) >= 20 and len(lows) >= 20:
            recent_highs = highs[-10:]
            previous_highs = highs[-20:-10]
            recent_lows = lows[-10:]
            previous_lows = lows[-20:-10]

            if max(recent_highs) > max(previous_highs):
                result['higher_highs'] = True
            if min(recent_lows) > min(previous_lows):
                result['higher_lows'] = True

        # VCP pattern and breakout detection
        pattern_result = classify_technical_pattern(history_list)
        result['has_vcp_pattern'] = pattern_result['pattern'].startswith('VCP')
        
        BREAKOUT_PATTERNS = {
            'High Tight Flag Breakout',
            'VCP Breakout (3T)',
            'Cup & Handle Breakout',
            'Long Base Breakout',
            'Resistance Breakout'
        }
        is_pattern_breakout = pattern_result.get('pattern', '') in BREAKOUT_PATTERNS
        
        # Safeguard: a fresh breakout day should not be a significant down day (e.g. <-2.5%)
        # This handles cases where a pattern is classified as breakout but the price had a heavy pullback on the day.
        is_breakout_confirmed = False
        if is_pattern_breakout:
            if len(closes) >= 2:
                day_change_pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100.0
                if day_change_pct >= -2.5:
                    is_breakout_confirmed = True
            else:
                is_breakout_confirmed = True
                
        result['is_breakout'] = is_breakout_confirmed

        # Relative strength rating (simplified - vs median of universe)
        # In a real implementation, this would compare against the peer universe
        # For now, we'll use a placeholder based on price performance
        result['relative_strength_rating'] = 50.0  # Placeholder - would be calculated vs universe

        return result

    def _get_defaults(self, symbol: str, exchange: str) -> Dict[str, Any]:
        """Get default values for StockDataSchema fields."""
        return {
            'symbol': symbol,
            'exchange': exchange,
            # Technical defaults
            'price': 0.0,
            'ema_20': 0.0,
            'ema_50': 0.0,
            'ema_100': 0.0,
            'ema_200': 0.0,
            'rsi': 50.0,  # Neutral RSI
            'macd': 0.0,
            'macd_signal': 0.0,
            'adx': 0.0,
            'supertrend': 0.0,
            'supertrend_direction': 1,  # Neutral/uptrend bias
            'price_vs_52w_high': 0.5,  # 50% of 52w high
            'higher_highs': False,
            'higher_lows': False,
            'golden_cross': False,
            # Fundamental defaults
            'revenue_growth_yoy': 0.0,
            'profit_growth_yoy': 0.0,
            'roe': 0.0,
            'roce': 0.0,
            'debt_to_equity': 0.5,  # Moderate debt
            'operating_margin': 0.0,
            'net_margin': 0.0,
            'operating_cash_flow': 0.0,
            'promoter_holding_pct': 50.0,  # Moderate promoter holding
            'promoter_pledged_pct': 0.0,
            # Momentum defaults
            'relative_strength_rating': 50.0,  # Median
            'volume_ratio': 1.0,  # Average volume
            'price_vs_52w_high_pct': 50.0,  # 50% of 52w high
            'has_vcp_pattern': False,
            'is_breakout': False,
            'momentum_acceleration': 0.0,
            # Institutional defaults (neutral)
            'mf_holding_change_pct': 0.0,
            'fii_net_buy_cr': 0.0,
            'fii_holding_pct': 0.0,
            'promoter_buy_qty': 0,
            'promoter_holding_change_pct': 0.0,
            'block_deal_count': 0,
            'block_deal_buy_ratio': 0.0,
            # Risk and Liquidity defaults
            'avg_daily_volume': 0,
            'market_cap_cr': 0.0,
            'bid_ask_spread_pct': 0.05,  # Typical spread
            'volatility_30d': 0.25,  # Typical volatility
            'circuit_history': 0,
            'operator_risk': 'low'
        }

    def _apply_missing_defaults(self, data: Dict[str, Any], symbol: str,
                                exchange: str) -> Dict[str, Any]:
        """Apply default values for any missing fields."""
        defaults = self._get_defaults(symbol, exchange)
        for key, default_value in defaults.items():
            if key not in data or data[key] is None or (isinstance(data[key], float) and math.isnan(data[key])):
                data[key] = default_value
        return data


# Convenience function for external use
def fetch_stock_data(symbol: str, exchange: str = 'NSE',
                     isolated_tv_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convenience function to fetch stock data for a single symbol.

    Args:
        symbol: Stock symbol
        exchange: Stock exchange
        isolated_tv_data: Pre-fetched TradingView data

    Returns:
        Dictionary conforming to StockDataSchema
    """
    fetcher = StockDataFetcher()
    return fetcher.fetch_stock_data(symbol, exchange, isolated_tv_data)


def fetch_isolated_tv_data(symbols: List[str]) -> Dict[str, Any]:
    """
    Convenience function to fetch isolated TradingView data for multiple symbols.

    Args:
        symbols: List of stock symbols

    Returns:
        Dictionary mapping symbol to TradingView data
    """
    fetcher = StockDataFetcher()
    return fetcher.fetch_isolated_tv_data(symbols)