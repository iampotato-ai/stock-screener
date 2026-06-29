"""Playwright end‑to‑end test for the Intraday view.

Ensures the Intraday tab activates and core UI elements appear.
"""

from playwright.sync_api import sync_playwright
from .common import get_dashboard_url, launch_browser


def test_intraday_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Load dashboard page
        page.goto(get_dashboard_url())
        # Click the Intraday tab
        page.click('button[data-view="intraday"]')
        # Verify Intraday view is visible
        intra_view = page.locator("#view-intraday")
        intra_view.wait_for(state="visible")
        assert intra_view.is_visible(), "Intraday view did not become visible"
        # Check that the widgets container exists
        grid = page.locator(".intraday-grid")
        grid.wait_for(state="visible")
        assert grid.is_visible(), "Intraday grid missing"
        # Check count widgets exist
        gap_go = page.locator("#count-gap-go")
        gap_go.wait_for(state="visible")
        assert gap_go.is_visible(), "Gap & Go count missing"
        vwap = page.locator("#count-vwap")
        vwap.wait_for(state="visible")
        assert vwap.is_visible(), "VWAP count missing"
        browser.close()
