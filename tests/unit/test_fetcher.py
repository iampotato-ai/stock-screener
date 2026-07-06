"""
Unit tests for fetcher.py - stock data fetching.
Tests isolated TradingView calls and Yahoo Finance integration.
"""
import json
import math
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.services.scoring.fetcher import StockDataFetcher, fetch_stock_data, fetch_isolated_tv_data


class TestStockDataFetcher:
    """Test stock data fetching functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.fetcher = StockDataFetcher()

    def test_init(self):
        """Test fetcher initialization."""
        assert self.fetcher is not None
        assert hasattr(self.fetcher, 'tradingview_url')
        assert hasattr(self.fetcher, 'yahoo_finance_base')
        assert hasattr(self.fetcher, 'yahoo_chart_base')

    def test_get_defaults(self):
        """Test default values generation."""
        defaults = self.fetcher._get_defaults('RELIANCE', 'NSE')

        assert defaults['symbol'] == 'RELIANCE'
        assert defaults['exchange'] == 'NSE'
        assert defaults['price'] == 0.0
        assert defaults['rsi'] == 50.0  # Neutral RSI
        assert defaults['roe'] == 0.0
        assert defaults['promoter_holding_pct'] == 50.0
        assert defaults['volatility_30d'] == 0.25
        assert defaults['operator_risk'] == 'low'

    def test_apply_missing_defaults(self):
        """Test applying defaults to partial data."""
        partial_data = {
            'symbol': 'TCS',
            'exchange': 'NSE',
            'price': 3500.0,
            # Missing many other fields
        }

        result = self.fetcher._apply_missing_defaults(partial_data, 'TCS', 'NSE')

        assert result['symbol'] == 'TCS'
        assert result['exchange'] == 'NSE'
        assert result['price'] == 3500.0  # Preserved value
        assert result['rsi'] == 50.0  # Default value
        assert result['roe'] == 0.0  # Default value
        assert result['market_cap_cr'] == 0.0  # Default value

    @patch('app.services.scoring.fetcher.urllib.request.urlopen')
    def test_fetch_isolated_tv_data_success(self, mock_urlopen):
        """Test successful isolated TradingView data fetch."""
        # Mock response data
        mock_response = Mock()
        mock_response.read.return_value = b'{"data": [["NSE:RELIANCE", 2500.50, 1500000.0, 2600.0, 2400.0, 65.5, 2450.30, 2.5, 15.0, 8.0, 1000000, 900000, 950000]]}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        result = self.fetcher.fetch_isolated_tv_data(['RELIANCE'])

        assert 'RELIANCE' in result
        rel_data = result['RELIANCE']
        assert rel_data['close'] == 2500.50
        assert rel_data['RSI'] == 65.5
        assert rel_data['EMA50'] == 2450.30
        assert rel_data['market_cap_basic'] == 1500000.0

    @patch('app.services.scoring.fetcher.urllib.request.urlopen')
    def test_fetch_isolated_tv_data_dict_format(self, mock_urlopen):
        """Test successful isolated TradingView data fetch with dictionary format (production)."""
        # Mock response data in dict format: {"s": "NSE:RELIANCE", "d": [name, close, market_cap, ...]}
        mock_response = Mock()
        mock_response.read.return_value = b'{"data": [{"s": "NSE:RELIANCE", "d": ["Reliance Industries", 2500.50, 1500000.0, 2600.0, 2400.0, 65.5, 2450.30, 2.5, 15.0, 8.0, 1000000, 900000, 950000]}]}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        result = self.fetcher.fetch_isolated_tv_data(['RELIANCE'])

        assert 'RELIANCE' in result
        rel_data = result['RELIANCE']
        assert rel_data['close'] == 2500.50
        assert rel_data['RSI'] == 65.5
        assert rel_data['EMA50'] == 2450.30
        assert rel_data['market_cap_basic'] == 1500000.0

    @patch('app.services.scoring.fetcher.urllib.request.urlopen')
    def test_fetch_isolated_tv_data_empty(self, mock_urlopen):
        """Test handling of empty response from TradingView."""
        # Mock empty response
        mock_response = Mock()
        mock_response.read.return_value = b'{"data": []}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        result = self.fetcher.fetch_isolated_tv_data(['RELIANCE'])

        assert result == {}

    @patch('yfinance.Ticker')
    def test_fetch_yahoo_fundamentals_success(self, mock_ticker_class):
        """Test successful Yahoo Finance fundamentals fetch."""
        mock_ticker = MagicMock()
        mock_ticker_class.return_value = mock_ticker
        
        mock_ticker.info = {
            'returnOnEquity': 0.18,
            'returnOnAssets': 0.18,
            'debtToEquity': 0.5,
            'operatingMargins': 0.20,
            'profitMargins': 0.15,
            'operatingCashflow': 5000000000,
            'heldPercentInstitutions': 0.45
        }
        
        import pandas as pd
        mock_ticker.income_stmt = pd.DataFrame(
            {
                '2026-03-31': {
                    'Total Revenue': 100000000000,
                    'Net Income': 15000000000
                },
                '2025-03-31': {
                    'Total Revenue': 90000000000,
                    'Net Income': 12000000000
                }
            }
        )

        result = self.fetcher._fetch_yahoo_fundamentals('RELIANCE')

        assert result is not None
        assert result['quoteSummary']['result'][0]['financialData']['returnOnEquity']['raw'] == 0.18

    @patch('yfinance.Ticker')
    def test_fetch_yahoo_fundamentals_failure(self, mock_ticker_class):
        """Test handling of Yahoo Finance failure."""
        mock_ticker_class.side_effect = Exception("Network error")

        result = self.fetcher._fetch_yahoo_fundamentals('INVALID')

        assert result is None

    @patch('app.services.scoring.fetcher.StockDataFetcher.fetch_isolated_tv_data')
    @patch('app.services.scoring.fetcher.StockDataFetcher._fetch_yahoo_fundamentals')
    @patch('app.services.scoring.fetcher.StockDataFetcher._fetch_yahoo_ohlcv')
    def test_fetch_stock_data_success(self, mock_ohlcv, mock_fundamentals, mock_tv):
        """Test successful complete stock data fetch."""
        # Mock TradingView data
        mock_tv.return_value = {
            'RELIANCE': {
                'close': 2500.50,
                'market_cap_basic': 1500000000.0,  # 1.5 billion
                'price_52_week_high': 2600.0,
                'price_52_week_low': 2400.0,
                'RSI': 65.5,
                'EMA50': 2450.30,
                'Perf.1M': 15.0,
                'Perf.3M': 8.0,
                'volume': 1000000,
                'average_volume_10d_calc': 900000,
                'average_volume_30d_calc': 950000
            }
        }

        # Mock Yahoo fundamentals
        mock_fundamentals.return_value = {
            'quoteSummary': {
                'result': [{
                    'financialData': {
                        'returnOnEquity': {'raw': 0.18},
                        'debtToEquity': {'raw': 0.5},
                        'operatingMargins': {'raw': 0.20},
                        'profitMargins': {'raw': 0.15},
                        'operatingCashflow': {'raw': 5000000000}
                    },
                    'defaultKeyStatistics': {
                        'heldPercentInstitutions': {'raw': 45.0}
                    }
                }]
            }
        }

        # Mock Yahoo OHLCV
        mock_ohlcv.return_value = {
            'chart': {
                'result': [{
                    'indicators': {
                        'quote': [{
                            'close': [2400, 2450, 2500, 2550, 2500.50],
                            'high': [2410, 2460, 2510, 2560, 2510],
                            'low': [2390, 2440, 2490, 2540, 2490],
                            'volume': [800000, 850000, 900000, 950000, 1000000]
                        }]
                    }
                }]
            }
        }

        result = self.fetcher.fetch_stock_data('RELIANCE', 'NSE')

        # Check that we got data
        assert result['symbol'] == 'RELIANCE'
        assert result['exchange'] == 'NSE'
        assert result['price'] == 2500.50
        assert result['ema_50'] == 2450.30
        assert result['rsi'] == 65.5
        assert result['roe'] == 18.0
        assert result['debt_to_equity'] == 0.5
        assert result['market_cap_cr'] == 150.0  # 1500000.0 / 1e7
        assert result['operating_margin'] == 20.0
        assert not math.isnan(result['volatility_30d'])

    @patch('app.services.scoring.fetcher.StockDataFetcher.fetch_isolated_tv_data')
    def test_fetch_stock_data_fallback_to_defaults(self, mock_tv):
        """Test fallback to defaults when all data sources fail."""
        # Mock all sources to return None/empty
        mock_tv.return_value = {}

        with patch.object(self.fetcher, '_fetch_yahoo_fundamentals', return_value=None), \
             patch.object(self.fetcher, '_fetch_yahoo_ohlcv', return_value=None):

            result = self.fetcher.fetch_stock_data('UNKNOWN', 'NSE')

            # Should still return valid structure with defaults
            assert result['symbol'] == 'UNKNOWN'
            assert result['exchange'] == 'NSE'
            assert result['price'] == 0.0  # Default
            assert result['rsi'] == 50.0  # Default
            assert result['roe'] == 0.0  # Default
            assert result['market_cap_cr'] == 0.0  # Default

    @patch('app.services.scoring.fetcher.StockDataFetcher')
    def test_fetch_stock_data_convenience_function(self, mock_fetcher_class):
        """Test the convenience function."""
        mock_instance = Mock()
        mock_instance.fetch_stock_data.return_value = {'symbol': 'RELIANCE', 'price': 2500.50}
        mock_fetcher_class.return_value = mock_instance

        result = fetch_stock_data('RELIANCE', 'NSE')

        assert result['symbol'] == 'RELIANCE'
        assert result['price'] == 2500.50
        mock_fetcher_class.assert_called_once()
        mock_instance.fetch_stock_data.assert_called_once_with('RELIANCE', 'NSE', None)

    @patch('app.services.scoring.fetcher.StockDataFetcher')
    def test_fetch_isolated_tv_data_convenience_function(self, mock_fetcher_class):
        """Test the convenience function for isolated TV data."""
        mock_instance = Mock()
        mock_instance.fetch_isolated_tv_data.return_value = {'RELIANCE': {'close': 2500.50}}
        mock_fetcher_class.return_value = mock_instance

        result = fetch_isolated_tv_data(['RELIANCE'])

        assert 'RELIANCE' in result
        assert result['RELIANCE']['close'] == 2500.50
        mock_fetcher_class.assert_called_once()
        mock_instance.fetch_isolated_tv_data.assert_called_once_with(['RELIANCE'])


if __name__ == '__main__':
    pytest.main([__file__])