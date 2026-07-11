"""
Unit tests for RSService and Relative Strength scoring.
"""
import logging
import pytest
from app.services.rs_service import rs_service, RSService
from app.utils.calculation import DEFAULT_RS_WEIGHTS


def test_service_init():
    """Test RSService initialization and configuration."""
    service = RSService()
    assert service.weights == DEFAULT_RS_WEIGHTS
    assert service.weights['3m'] == 0.40
    assert service.weights['6m'] == 0.20
    assert service.weights['9m'] == 0.20
    assert service.weights['12m'] == 0.20


def test_calculate_momentum_score():
    """Test weighted momentum score calculation."""
    service = RSService()
    returns = {
        '3m': 10.0,
        '6m': 20.0,
        '9m': 30.0,
        '12m': 40.0
    }
    # Expected: 0.4*10 + 0.2*20 + 0.2*30 + 0.2*40 = 22.0
    result = service.calculate_momentum_score(returns)
    assert result == 22.0


def test_calculate_momentum_score_partial_data():
    """Test momentum score calculation when some periods are missing."""
    service = RSService()
    returns = {
        '3m': 10.0,
        '6m': 20.0
    }
    # Weighted sum = 0.4*10 + 0.2*20 = 8.0
    # Total weight used = 0.4 + 0.2 = 0.6
    # Normalized = 8.0 / 0.6 = 13.333...
    result = service.calculate_momentum_score(returns)
    assert pytest.approx(result, 0.001) == 13.333


def test_calculate_momentum_score_no_data():
    """Test momentum score calculation with empty returns dictionary."""
    service = RSService()
    result = service.calculate_momentum_score({})
    assert result == 0.0


def test_calculate_rs_scores_empty_input_returns_empty():
    """Empty list input should return an empty list."""
    assert rs_service.calculate_rs_scores([]) == []


def test_calculate_rs_scores_single_stock_gets_rs_50():
    """A single stock in the universe cannot be ranked against peers, so it defaults to 50."""
    stocks = [{'ticker': 'AAPL', '3m': 15.0}]
    result = rs_service.calculate_rs_scores(stocks)
    assert len(result) == 1
    assert result[0]['rs_score'] == 50
    assert result[0]['has_returns_data'] is True
    assert result[0]['momentum_score'] == 15.0


def test_calculate_rs_scores_best_performer_gets_highest_rs():
    """Stock with best return gets the highest rank (99)."""
    stocks = [
        {'ticker': 'AAPL', '3m': 30.0},
        {'ticker': 'MSFT', '3m': 20.0},
        {'ticker': 'GOOGL', '3m': 10.0},
    ]
    result = rs_service.calculate_rs_scores(stocks)
    aapl = next(s for s in result if s['ticker'] == 'AAPL')
    assert aapl['rs_score'] == 99


def test_calculate_rs_scores_worst_performer_gets_lowest_rs():
    """Stock with worst return gets the lowest rank (1)."""
    stocks = [
        {'ticker': 'AAPL', '3m': 30.0},
        {'ticker': 'MSFT', '3m': 20.0},
        {'ticker': 'GOOGL', '3m': 10.0},
    ]
    result = rs_service.calculate_rs_scores(stocks)
    googl = next(s for s in result if s['ticker'] == 'GOOGL')
    assert googl['rs_score'] == 1


def test_calculate_rs_scores_range_is_1_to_99():
    """All scored stocks must have rs_score clamped within the 1-99 range."""
    # Generate 20 stocks with ascending returns
    stocks = [{'ticker': f'STK{i}', '3m': float(i)} for i in range(20)]
    result = rs_service.calculate_rs_scores(stocks)
    for stock in result:
        assert 1 <= stock['rs_score'] <= 99


def test_calculate_rs_scores_no_returns_gets_rs_0():
    """Stocks without any returns data receive rs_score = 0 and momentum_score = 0.0."""
    stocks = [
        {'ticker': 'AAPL', '3m': 30.0},
        {'ticker': 'MSFT'},  # No returns keys
    ]
    result = rs_service.calculate_rs_scores(stocks)
    msft = next(s for s in result if s['ticker'] == 'MSFT')
    assert msft['rs_score'] == 0
    assert msft['momentum_score'] == 0.0
    assert msft['has_returns_data'] is False


def test_calculate_rs_scores_tradingview_perf3m_fallback(caplog):
    """If direct return keys are absent, Perf.3M key is consumed as fallback. Perf.W emits a log."""
    stocks = [
        {'ticker': 'AAPL', 'Perf.3M': 30.0, 'Perf.W': 5.0},
        {'ticker': 'MSFT', 'Perf.3M': 10.0},
    ]
    with caplog.at_level(logging.DEBUG):
        result = rs_service.calculate_rs_scores(stocks)
    aapl = next(s for s in result if s['ticker'] == 'AAPL')
    assert aapl['rs_score'] == 99
    assert aapl['returns_used'] == {'3m': 30.0}
    # Debug log warning about Perf.W being ignored should be present
    assert any("Perf.W/Perf.1M TradingView keys" in record.message for record in caplog.records)


def test_calculate_rs_scores_preserves_input_order():
    """The output list must preserve the exact index order of the input list (no sorting)."""
    stocks = [
        {'ticker': 'MSFT', '3m': 10.0},  # Second best
        {'ticker': 'AAPL', '3m': 30.0},  # Best
        {'ticker': 'GOOGL', '3m': 5.0},  # Worst
    ]
    result = rs_service.calculate_rs_scores(stocks)
    assert [s['ticker'] for s in result] == ['MSFT', 'AAPL', 'GOOGL']


def test_calculate_rs_scores_ties_handled_correctly():
    """Stocks with equal returns receive equal RS scores based on duplicate handling."""
    stocks = [
        {'ticker': 'AAPL', '3m': 20.0},
        {'ticker': 'MSFT', '3m': 20.0},
        {'ticker': 'GOOGL', '3m': 20.0},
    ]
    result = rs_service.calculate_rs_scores(stocks)
    for stock in result:
        assert stock['rs_score'] == 67  # Average rank: 2/3 -> maps to 67


def test_get_default_weights():
    """Test getting default weights returns a copy of weights."""
    service = RSService()
    weights = service.get_default_weights()
    assert weights == DEFAULT_RS_WEIGHTS
    assert weights is not service.weights  # Should be a copy
    weights['3m'] = 0.99
    assert service.weights['3m'] == 0.40  # Original remains unchanged