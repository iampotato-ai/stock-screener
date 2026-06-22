"""Playwright end‑to‑end test for the Dashboard view.

Ensures the Dashboard tab (default) is visible and key UI components appear.
"""

from e2e.tests.common import get_base_url, launch_browser
from playwright.sync_api import sync_playwright


def test_dashboard_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Load home page (dashboard is active by default)
        page.goto(get_base_url())
        # Verify the dashboard container is visible
        assert page.locator("#view-dashboard").is_visible(), "Dashboard view not visible"
        # Verify a core dashboard element (market pulse) exists
        assert page.locator("#market-pulse").is_visible(), "Market pulse element missing"
        browser.close()
