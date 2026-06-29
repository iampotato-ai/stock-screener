"""Playwright end‑to‑end test for the Dashboard view.

Ensures the Dashboard tab (default) is visible and key UI components appear.
"""

from .common import get_dashboard_url, launch_browser
from playwright.sync_api import sync_playwright


def test_dashboard_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Load dashboard page
        page.goto(get_dashboard_url())
        # Verify the dashboard container is visible
        view = page.locator("#view-dashboard")
        view.wait_for(state="visible")
        assert view.is_visible(), "Dashboard view not visible"
        # Verify a core dashboard element (market pulse) exists
        pulse = page.locator("#market-pulse")
        pulse.wait_for(state="visible")
        assert pulse.is_visible(), "Market pulse element missing"
        browser.close()
