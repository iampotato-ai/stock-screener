"""Playwright end‑to‑end test for the Screener view.

Ensures the Screener tab activates and core UI elements appear.
"""

from playwright.sync_api import sync_playwright
from e2e.tests.common import get_base_url


def test_screener_view():
    with sync_playwright() as p:
        # Launch Chromium (headless by default as per config)
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        # Home page loads
        page.goto(get_base_url())
        # Click the Screener tab via data-view attribute
        page.click('button[data-view="screener"]')
        # Verify Screener workspace is visible
        screener_view = page.locator("#view-screener")
        assert screener_view.is_visible(), "Screener view should be visible"
        # Verify a representative stat card exists (e.g., total trades)
        assert page.locator("#card-total").is_visible(), "Stat card '#card-total' missing"
        browser.close()
