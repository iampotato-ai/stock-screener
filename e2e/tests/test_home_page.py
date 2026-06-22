"""Playwright end‑to‑end test for the Momentum Scan front‑end.

Ensures the home page loads, title contains the project name, and navigation tabs are present.
"""

from e2e.tests.common import get_base_url
from playwright.sync_api import sync_playwright


def test_home_page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto(get_base_url())
        assert "Momentum Scan" in page.title()
        assert page.locator("#tab-ep").is_visible(), "EP tab should be visible"
        assert page.locator("#view-dashboard").is_visible(), "Dashboard view should be visible"
        browser.close()
