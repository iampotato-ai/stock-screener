"""Playwright end‑to‑end test for the Watchlist view.

Ensures the Watchlist tab activates and core UI elements appear.
"""

from playwright.sync_api import sync_playwright
from .common import get_base_url


def test_watchlist_view():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        # Load home page
        page.goto(get_base_url())
        # Click the Watchlist tab (data-view="watchlist")
        page.click('button[data-view="watchlist"]')
        # Verify Watchlist view is visible
        watch_view = page.locator("#view-watchlist")
        assert watch_view.is_visible(), "Watchlist view did not become visible"
        # Check that the watchlist workspace grid exists
        grid = page.locator(".watchlist-workspace-grid")
        assert grid.is_visible(), "Watchlist workspace grid missing"
        browser.close()
