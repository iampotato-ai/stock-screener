"""Playwright end‑to‑end test for the Intraday view.

Ensures the Intraday tab activates and core UI elements appear.
"""

from playwright.sync_api import sync_playwright
from .common import get_base_url, launch_browser


def test_intraday_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Load home page
        page.goto(get_base_url())
        # Click the Intraday tab
        page.click('button[data-view="intraday"]')
        # Verify Intraday view is visible
        intra_view = page.locator("#view-intraday")
        assert intra_view.is_visible(), "Intraday view did not become visible"
        # Check that the widgets container exists
        grid = page.locator(".intraday-grid")
        assert grid.is_visible(), "Intraday grid missing"
        # Check count widgets exist
        assert page.locator("#count-gap-go").is_visible(), "Gap & Go count missing"
        assert page.locator("#count-vwap").is_visible(), "VWAP count missing"
        browser.close()
