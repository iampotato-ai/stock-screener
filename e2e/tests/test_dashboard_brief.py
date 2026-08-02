"""Playwright end-to-end test for the Daily Market Brief widget.
"""
from .common import get_dashboard_url, launch_browser
from playwright.sync_api import sync_playwright


def test_daily_market_brief_widget():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        
        # Load dashboard page
        page.goto(get_dashboard_url())
        
        # Verify the market brief widget container exists and is visible
        widget = page.locator("#market-brief-widget")
        widget.wait_for(state="visible", timeout=10000)
        assert widget.is_visible(), "Daily Market Brief widget container not visible"
        
        # Wait for brief card content inside widget
        card = widget.locator(".brief-card")
        card.wait_for(state="visible", timeout=10000)
        assert card.is_visible(), "Market brief card content not visible"
        
        browser.close()
