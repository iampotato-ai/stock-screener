# Playwright configuration for Momentum Scan front‑end E2E tests
# This config tells Playwright where the app is served and which directory holds tests.
# The Flask development server runs on http://127.0.0.1:5000 by default (run.py).
# Tests are written with the Python sync API.

import os

# Base URL – overridden by CI if needed via PLAYWRIGHT_BASE_URL env var
BASE_URL = os.getenv("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:5000")

# Export configuration as a dict for the Playwright test runner (playwright test command).
# When using the Python API we import this module directly, but keeping a config file
# mirrors the typical TypeScript setup and helps IDEs.
config = {
    "testDir": "e2e",
    "use": {
        "baseURL": BASE_URL,
        "headless": True,
        "ignoreHTTPSErrors": True,
        "screenshot": "only-on-failure",
    },
    "timeout": 30000,  # per‑test timeout (ms)
}
