import pytest
import sys
import os

# Ensure the root folder is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import ensemble_blend, compute_dynamic_weights

def test_ensemble_blend_identical_paths():
    # 1. Three identical paths
    kronos_path = [10.0, 11.0, 12.0, 13.0, 14.0]
    prophet_path = [10.0, 11.0, 12.0, 13.0, 14.0]
    arima_path = [10.0, 11.0, 12.0, 13.0, 14.0]
    
    weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
    
    res = ensemble_blend(kronos_path, prophet_path, arima_path, weights)
    
    assert res['ensemble_path'] == [10.0, 11.0, 12.0, 13.0, 14.0]
    assert res['divergence_score'] == 0.0
    assert res['conviction'] == 'HIGH'
    # Directional agreement matrix: all models agree on positive direction at all 4 steps
    assert res['agreement_matrix']['kronos_vs_prophet'] == 100.0
    assert res['agreement_matrix']['kronos_vs_arima'] == 100.0

def test_ensemble_blend_diverging_paths():
    # 2. Diverging paths:
    # Kronos goes up steeply: [10, 15, 20]
    # Prophet stays flat: [10, 10, 10]
    # ARIMA goes down: [10, 5, 0]
    kronos_path = [10.0, 15.0, 20.0]
    prophet_path = [10.0, 10.0, 10.0]
    arima_path = [10.0, 5.0, 0.0]
    
    weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
    res = ensemble_blend(kronos_path, prophet_path, arima_path, weights)
    
    # Blended: 0.5*[10,15,20] + 0.3*[10,10,10] + 0.2*[10,5,0] = [10.0, 11.5, 13.0]
    assert res['ensemble_path'] == [10.0, 11.5, 13.0]
    assert res['divergence_score'] > 0.0
    
    # Check direction agreement:
    # kronos: [1, 1]
    # prophet: [-1, -1] (flat triggers -1 in helper: 1 if arr[i] > arr[i-1] else -1)
    # arima: [-1, -1]
    # kronos vs prophet match: 0%
    # prophet vs arima match: 100%
    assert res['agreement_matrix']['kronos_vs_prophet'] == 0.0
    assert res['agreement_matrix']['prophet_vs_arima'] == 100.0

def test_compute_dynamic_weights_mocked(monkeypatch):
    # Mock _compute_rolling_mape to return fixed MAPE metrics
    # Kronos = 2.0%, Prophet = 4.0%, ARIMA = 8.0%
    def mock_compute_rolling_mape(ticker, model_fn, horizon):
        if "kronos" in model_fn.__name__:
            return 2.0
        elif "prophet" in model_fn.__name__:
            return 4.0
        elif "arima" in model_fn.__name__:
            return 8.0
        return 5.0
        
    monkeypatch.setattr("app._compute_rolling_mape", mock_compute_rolling_mape)
    # Clear out any existing state in weight registry
    monkeypatch.setattr("app._weight_ema_state", {})
    
    # First invocation (previous EMA state defaults to raw weight)
    weights = compute_dynamic_weights("TCS", horizon=5)
    
    # Inverse mapes: k = 1/2 = 0.5, p = 1/4 = 0.25, a = 1/8 = 0.125
    # Total = 0.5 + 0.25 + 0.125 = 0.875
    # Raw weights: k = 0.5/0.875 = 0.5714, p = 0.25/0.875 = 0.2857, a = 0.125/0.875 = 0.1429
    # Expect weights to sum to 1.0 and match raw weights (since no previous state was found)
    assert pytest.approx(sum(weights.values())) == 1.0
    assert weights['kronos'] == 0.5714
    assert weights['prophet'] == 0.2857
    assert weights['arima'] == 0.1429
