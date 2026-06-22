"""Playwright end‑to‑end test for the IPO Momentum view.

Ensures the IPO tab activates and core UI components appear.
"""

from .common import get_base_url
from playwright.sync_api import sync_playwright


def test_ipo_view():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto(get_base_url())
        # Click IPO tab (identified by #tab-ipo)
        page.click('#tab-ipo')
        # Verify IPO view becomes visible
        assert page.locator('#view-ipo').is_visible(), "IPO view not visible"
        # Verify a key IPO workspace wrapper exists
        assert page.locator('.ipo-workspace-wrapper').is_visible(), "IPO workspace wrapper missing"
        browser.close()
