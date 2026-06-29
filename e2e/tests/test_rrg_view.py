"""Playwright end‑to‑end test for the RRG Rotation view.

Ensures the RRG tab activates and core UI elements appear.
"""

from .common import get_dashboard_url, launch_browser
from playwright.sync_api import sync_playwright


def test_rrg_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        page.goto(get_dashboard_url())
        # Click the RRG tab via data-view attribute
        page.click('button[data-view="rrg"]')
        # Verify RRG view is visible
        view = page.locator('#view-rrg')
        view.wait_for(state="visible")
        assert view.is_visible(), "RRG view not visible"
        # Verify a core RRG container exists
        container = page.locator('.rrg-container')
        container.wait_for(state="visible")
        assert container.is_visible(), "RRG container missing"
        browser.close()
