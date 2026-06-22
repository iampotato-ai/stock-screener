"""Playwright end‑to‑end test for the Watchlist functionality.

Ensures that we can add a stock manually to the watchlist and verify its presence in the UI.
"""

from playwright.sync_api import sync_playwright
from .common import get_base_url, launch_browser


def test_watchlist_functionality():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        
        # Load home page
        page.goto(get_base_url())
        
        # Click the Watchlist tab (data-view="watchlist")
        page.click('button[data-view="watchlist"]')
        
        # Verify Watchlist view is visible
        watch_view = page.locator("#view-watchlist")
        assert watch_view.is_visible(), "Watchlist view did not become visible"
        
        # Click "Add Ticker Manually" button to reveal input box
        page.click("#btn-add-watchlist-manual")
        
        # Check that the input box is revealed (no longer hidden)
        input_box = page.locator("#watchlist-add-box")
        assert input_box.is_visible(), "Watchlist add box not visible after toggle"
        
        # Type the ticker symbol
        input_manual = page.locator("#watchlist-manual-input")
        input_manual.fill("INFY")
        
        # Click the submit button to add the stock
        page.click("#btn-submit-watchlist-manual")
        
        # Wait for the stock row to be created and present in the DOM
        stock_row = page.locator('.watchlist-row[data-symbol="INFY"]')
        page.wait_for_selector('.watchlist-row[data-symbol="INFY"]', state="attached", timeout=5000)
        
        assert stock_row.is_visible(), "Manually added stock row not visible in watchlist"
        
        browser.close()
