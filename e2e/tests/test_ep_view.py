"""Playwright end‑to‑end test for the EP Screener view.

Ensures the EP tab loads, the EP workspace becomes active, and key UI elements are present.
"""

from playwright.sync_api import sync_playwright
from .common import get_dashboard_url, launch_browser


def test_ep_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Load dashboard page
        page.goto(get_dashboard_url())
        # Click EP tab
        page.click("#tab-ep")
        # EP view should become visible
        view = page.locator("#view-ep")
        view.wait_for(state="visible")
        assert view.is_visible(), "EP view not visible"
        # Wait for the EP badge element to be attached (it may stay hidden if count is zero)
        page.wait_for_selector("#ep-high-count", state="attached", timeout=5000)
        badge = page.locator("#ep-high-count")
        # Ensure badge element exists in DOM
        assert badge.count() == 1, "EP badge element missing"
        browser.close()
