"""Tests for EP scoring model integration and fallback behavior."""

import builtins
import types
import pytest

# Import the service module after ensuring the project root is on sys.path.
import sys
sys.path.append('C:/Users/91996/Documents/My Projects/stock-screener')

from app.services import ep_service

def test_compute_ep_score_fallback_when_model_missing(monkeypatch):
    """If the model cannot be loaded, compute_ep_score should fall back to the original logic."""
    # Force _load_ep_model to raise FileNotFoundError
    def raise_error():
        raise FileNotFoundError("model not found")
    monkeypatch.setattr(ep_service, "_load_ep_model", lambda: raise_error())

    # Use known inputs and compare with the original hand‑crafted calculation.
    neglect = 0.5
    catalyst = 0.8
    repricing = 0.7
    liquidity = True
    fundamentals = True
    # Expected fallback value (same as original function before modifications)
    expected = 0.715  # 0.25*0.5 + 0.35*0.8 + 0.30*0.7 + 0.10*1.0 = 0.715
    result = ep_service.compute_ep_score(neglect, catalyst, repricing, liquidity_ok=liquidity, has_fundamentals=fundamentals)
    assert result == expected

def test_predict_ep_score_uses_model(monkeypatch):
    """When a model is present, predict_ep_score should call the model's predict_proba."""
    # Mock a simple model that returns a fixed probability.
    class DummyModel:
        def predict_proba(self, X):
            return [[0.4, 0.6]]
    dummy_manifest = {"feature_order": ["neglect_score", "catalyst_score", "repricing_score", "liquidity_ok", "has_fundamentals"]}
    monkeypatch.setattr(ep_service, "_MODEL", DummyModel())
    monkeypatch.setattr(ep_service, "_MANIFEST", dummy_manifest)
    # No need to load model; call directly.
    features = {
        "neglect_score": 0.5,
        "catalyst_score": 0.8,
        "repricing_score": 0.7,
        "liquidity_ok": 1,
        "has_fundamentals": 1,
    }
    prob = ep_service.predict_ep_score(features)
    assert prob == 0.6
