"""Unit tests for Multiyear Breakout REST API endpoints."""

from unittest.mock import patch


def test_get_multiyear_breakout_cached(flask_app):
    """GET /api/v1/multiyear-breakout returns cached data if available."""
    client = flask_app.test_client()
    sample_data = [
        {
            "symbol": "ABC",
            "current_price": 520.0,
            "prior_ath_price": 500.0,
            "prior_ath_date": "2017-03-15",
            "breakout_date": "2024-08-10",
            "years_below_ath": 7.4,
            "pct_above_ath": 4.0,
            "volume_confirmed": True,
            "consolidation_range_pct": 50.0,
            "market_cap_cr": 15000.0,
            "sector": "Industrials",
            "rs_vs_nifty": 0.05,
        }
    ]

    flask_app.config['MULTIYEAR_BREAKOUT_CACHE'] = {
        'data': sample_data,
        'count': 1,
        'refreshed': '2024-08-15T16:45:00',
    }

    response = client.get('/api/v1/multiyear-breakout')
    assert response.status_code == 200
    res = response.get_json()
    assert res['count'] == 1
    assert len(res['data']) == 1
    assert res['data'][0]['symbol'] == 'ABC'


def test_get_multiyear_breakout_scan(flask_app):
    """GET /api/v1/multiyear-breakout with force=true triggers live scan."""
    flask_app.config['MULTIYEAR_BREAKOUT_CACHE'] = None
    client = flask_app.test_client()

    with patch('app.database.get_nse_symbols_by_marketcap', return_value=['MOCK_SYM']):
        with patch('app.services.multiyear_breakout_service.scan_multiyear_breakouts', return_value=[]):
            response = client.get('/api/v1/multiyear-breakout?force=true')
            assert response.status_code == 200
            res = response.get_json()
            assert 'data' in res
            assert res['count'] == 0


def test_post_multiyear_breakout_refresh(flask_app):
    """POST /api/v1/multiyear-breakout/refresh forces scan and updates cache."""
    client = flask_app.test_client()

    mock_result = [{
        "symbol": "XYZ",
        "current_price": 1200.0,
        "prior_ath_price": 1100.0,
        "years_below_ath": 5.2,
    }]

    with patch('app.database.get_nse_symbols_by_marketcap', return_value=['XYZ']):
        with patch('app.services.multiyear_breakout_service.scan_multiyear_breakouts', return_value=mock_result):
            response = client.post('/api/v1/multiyear-breakout/refresh', json={
                'min_base_years': 5,
                'breakout_window_days': 10,
            })
            assert response.status_code == 200
            res = response.get_json()
            assert res['count'] == 1
            assert res['data'][0]['symbol'] == 'XYZ'


def test_feature_flag_disabled(flask_app):
    """Returns 404 when ENABLE_MULTIYEAR_BREAKOUT is False."""
    client = flask_app.test_client()
    orig = flask_app.config.get('ENABLE_MULTIYEAR_BREAKOUT')
    flask_app.config['ENABLE_MULTIYEAR_BREAKOUT'] = False
    try:
        response = client.get('/api/v1/multiyear-breakout')
        assert response.status_code == 404

        response_post = client.post('/api/v1/multiyear-breakout/refresh')
        assert response_post.status_code == 404
    finally:
        flask_app.config['ENABLE_MULTIYEAR_BREAKOUT'] = orig
