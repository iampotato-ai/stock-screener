"""Playwright end‑to‑end test for the Bull Snort Screener view.

Ensures the Bull Snort tab loads, the Bull Snort workspace becomes active, and key UI elements are present.
"""

from playwright.sync_api import sync_playwright
from .common import get_dashboard_url, launch_browser


def test_bull_snort_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Load dashboard page
        page.goto(get_dashboard_url())
        # Click Bull Snort tab
        page.click("#tab-bull-snort")
        # Bull Snort view should become visible
        view = page.locator("#view-bull-snort")
        view.wait_for(state="visible")
        assert view.is_visible(), "Bull Snort view not visible"
        
        # Verify that parameters and run button exist
        assert page.locator("#bs-vol-period").is_visible(), "Vol period select missing"
        assert page.locator("#bs-vol-surge").is_visible(), "Vol surge input missing"
        assert page.locator("#bs-min-gap").is_visible(), "Min gap input missing"
        assert page.locator("#bs-max-gap").is_visible(), "Max gap input missing"
        assert page.locator("#bs-close-pos").is_visible(), "Min Close Position input missing"
        assert page.locator("#btn-run-bull-snort").is_visible(), "Run screen button missing"
        
        browser.close()
