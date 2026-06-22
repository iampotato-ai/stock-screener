"""Playwright end‑to‑end test for the Screener view.

Ensures the Screener tab activates and core UI elements appear.
"""

from playwright.sync_api import sync_playwright
from .common import get_base_url, launch_browser


def test_screener_view():
    with sync_playwright() as p:
        # Launch Chromium (headless by default as per config)
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Home page loads
        page.goto(get_base_url())
        # Click the Screener tab via data-view attribute
        page.click('button[data-view="screener"]')
        # Verify Screener workspace is visible
        screener_view = page.locator("#view-screener")
        screener_view.wait_for(state="visible")
        assert screener_view.is_visible(), "Screener view should be visible"
        # Verify a representative stat card exists (e.g., total trades)
        card_total = page.locator("#card-total")
        card_total.wait_for(state="visible")
        assert card_total.is_visible(), "Stat card '#card-total' missing"
        browser.close()
