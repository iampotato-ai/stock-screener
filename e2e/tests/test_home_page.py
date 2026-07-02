"""Playwright end‑to‑end test for the Momentum Scan front‑end.

Ensures the home page loads, title contains the project name, and navigation tabs are present.
"""

from .common import get_base_url, get_dashboard_url, launch_browser
from playwright.sync_api import sync_playwright


def test_landing_page():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        page.goto(get_base_url())
        assert "MomentumScan" in page.title()
        assert page.locator(".landing-header").is_visible(), "Landing page header should be visible"
        assert page.locator(".hero-section").is_visible(), "Hero section should be visible"
        assert page.locator(".terminal-container").is_visible(), "Terminal mockup should be visible"
        assert page.locator("#early-access-form").is_visible(), "Early access form should be visible"
        browser.close()


def test_home_page():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        page.goto(get_dashboard_url())
        assert "Momentum Scan" in page.title()
        assert page.locator("#tab-ep").is_visible(), "EP tab should be visible"
        assert page.locator("#view-dashboard").is_visible(), "Dashboard view should be visible"
        browser.close()
