"""Playwright end‑to‑end test for the RRG Rotation view.

Ensures the RRG tab activates and core UI elements appear.
"""

from e2e.tests.common import get_base_url
from playwright.sync_api import sync_playwright


def test_rrg_view():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto(get_base_url())
        # Click the RRG tab via data-view attribute
        page.click('button[data-view="rrg"]')
        # Verify RRG view is visible
        assert page.locator('#view-rrg').is_visible(), "RRG view not visible"
        # Verify a core RRG container exists
        assert page.locator('.rrg-container').is_visible(), "RRG container missing"
        browser.close()
