---
name: gen-test
description: Scaffolds a pytest file for a given Flask endpoint.
disable-model-invocation: true
---
# Usage
/gen-test GET /api/v1/top-momentum
# What it does
1. Parses method and path.
2. Creates tests/test_<sanitized_path>.py with a Flask test client.
3. Includes placeholder assertions (status 200, JSON shape).
# Example output for the command above
```python
"""Test GET /api/v1/top-momentum – returns the top‑5 momentum picks."""
import json
from app import create_app

def test_top_momentum():
    app = create_app('testing')
    client = app.test_client()
    resp = client.get("/api/v1/top-momentum")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
    assert len(data) == 5
    for item in data:
        assert "symbol" in item and "change" in item
```