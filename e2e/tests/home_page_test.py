"""Playwright end‑to‑end test for the Momentum Scan front‑end.

The Flask development server must be running (e.g. `python run.py`).
This test verifies that the home page loads, the title contains the
project name, and the navigation tabs are present.
"""

import time
import sys
from subprocess import Popen
from pathlib import Path

from playwright.sync_api import sync_playwright

# Helper to start the Flask dev server in the background for the test run.
# It is started with the same command used for local development.
def _start_server():
    # Use the project's run.py entry point.
    proc = Popen([sys.executable, "run.py"], cwd=Path.cwd())
    # Give the server a moment to bind the socket.
    time.sleep(3)
    return proc


def test_home_page():
    server = _start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("http://127.0.0.1:5000/")
            # Verify page title.
            assert "Momentum Scan" in page.title()

            # Verify navigation tabs exist (at least the EP tab we care about).
            ep_tab = page.locator("#tab-ep")
            assert ep_tab.is_visible(), "EP tab should be visible on the navigation bar"

            # Optionally, check that the dashboard view is the default active view.
            dashboard = page.locator("#view-dashboard")
            assert dashboard.is_visible(), "Dashboard view should be visible on initial load"

            browser.close()
    finally:
        # Shut down the Flask server.
        server.terminate()
        server.wait()
")