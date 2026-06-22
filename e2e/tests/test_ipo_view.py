"""Playwright end‑to‑end test for the IPO Momentum view.

Ensures the IPO tab activates and core UI components appear.
"""

from .common import get_base_url, launch_browser
from playwright.sync_api import sync_playwright


def test_ipo_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        page.goto(get_base_url())
        # Click IPO tab (identified by #tab-ipo)
        page.click('#tab-ipo')
        # Verify IPO view becomes visible
        view = page.locator('#view-ipo')
        view.wait_for(state="visible")
        assert view.is_visible(), "IPO view not visible"
        # Verify a key IPO workspace wrapper exists
        wrapper = page.locator('.ipo-workspace-wrapper')
        wrapper.wait_for(state="visible")
        assert wrapper.is_visible(), "IPO workspace wrapper missing"
        browser.close()
