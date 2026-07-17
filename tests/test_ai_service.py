import pytest
import time
import requests
from unittest.mock import patch, MagicMock
from app.services.ai_service import ai_service

def test_exponential_backoff_retry(monkeypatch):
    """Verify NIM call implements exponential backoff and retries."""
    mock_post = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": "NPST is bullish due to blowout earnings.",
                "reasoning_content": "Analyzed technical metrics first."
            }
        }]
    }

    # Side effects: Exception, Exception, mock_resp
    mock_post.side_effect = [Exception("Temporary Error"), Exception("Temporary Error 2"), mock_resp]
    monkeypatch.setattr(requests, "post", mock_post)

    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "mock-nim-key")
    ai_service.nim_circuit_breaker_until = 0.0

    # Mock time.sleep to avoid slowing down tests
    monkeypatch.setattr(time, "sleep", lambda x: None)

    res = ai_service.generate_thesis_and_reasoning("NPST", {}, [], [])
    
    assert res["thesis"] == "NPST is bullish due to blowout earnings."
    assert res["reasoning"] == "Analyzed technical metrics first."
    assert mock_post.call_count == 3

def test_circuit_breaker_on_429(monkeypatch):
    """Verify a 429 rate limit triggers the circuit breaker."""
    mock_post = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_post.return_value = mock_resp
    monkeypatch.setattr(requests, "post", mock_post)

    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "mock-nim-key")
    ai_service.nim_circuit_breaker_until = 0.0

    res = ai_service._call_nim("model", [])
    
    assert res is None
    assert ai_service.nim_circuit_breaker_until > time.time()

def test_gemini_fallback_xml_parsing(monkeypatch):
    """Verify fallback to Gemini correctly parses XML reasoning blocks."""
    mock_post = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": "<thought>\nAnalyzing financial growth metrics of NPST.\nProfit grew 250%.\n</thought>\nNPST shows strong earnings growth metrics and relative volume."
                }]
            }
        }]
    }
    mock_post.return_value = mock_resp
    monkeypatch.setattr(requests, "post", mock_post)

    # Force NIM to fail to trigger Gemini path
    monkeypatch.setattr(ai_service, "_call_nim", lambda *args, **kwargs: None)
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")

    res = ai_service.generate_thesis_and_reasoning("NPST", {}, [], [])
    
    assert "Analyzing financial growth" in res["reasoning"]
    assert "NPST shows strong earnings growth" in res["thesis"]
