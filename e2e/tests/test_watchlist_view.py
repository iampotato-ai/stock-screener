"""Playwright end‑to‑end test for the Watchlist view.

Ensures the Watchlist tab activates and core UI elements appear.
"""

from playwright.sync_api import sync_playwright
from .common import get_dashboard_url, launch_browser


def test_watchlist_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Load dashboard page
        page.goto(get_dashboard_url())
        # Click the Watchlist tab (data-view="watchlist")
        page.click('button[data-view="watchlist"]')
        # Verify Watchlist view is visible
        watch_view = page.locator("#view-watchlist")
        watch_view.wait_for(state="visible")
        assert watch_view.is_visible(), "Watchlist view did not become visible"
        # Check that the watchlist workspace grid exists
        grid = page.locator(".watchlist-workspace-grid")
        grid.wait_for(state="visible")
        assert grid.is_visible(), "Watchlist workspace grid missing"
        browser.close()
