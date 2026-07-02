"""Playwright end‑to‑end test for the MomentumScan Landing Page.

Ensures that the landing page interactive elements work correctly.
"""

from playwright.sync_api import sync_playwright
from .common import get_base_url, launch_browser


def test_landing_page_interactions():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        
        # Load landing page
        page.goto(get_base_url())
        
        # Verify page title
        assert "MomentumScan" in page.title()
        
        # Verify hero badge and bento grid are present
        assert page.locator(".hero-badge").is_visible()
        assert page.locator("#market-intel-bento").is_visible()
        
        # Verify interactive tabs in the Scan Gallery
        # Find Strong Swing tab button and click it
        strong_swing_tab = page.locator('button[data-scan="strong-swing"]')
        assert strong_swing_tab.is_visible()
        strong_swing_tab.click()
        
        # Verify active class shifted
        page.wait_for_selector('button[data-scan="strong-swing"].active')
        assert "active" in strong_swing_tab.get_attribute("class")
        
        # Verify waitlist registration form submission
        email_input = page.locator("#early-access-email")
        submit_btn = page.locator("#early-access-btn")
        success_msg = page.locator("#early-access-success")
        
        assert email_input.is_visible()
        assert submit_btn.is_visible()
        
        # Enter mock email and submit
        email_input.fill("trader_test@momentumscan.in")
        submit_btn.click()
        
        # Verify success message appears
        success_msg.wait_for(state="visible", timeout=3000)
        assert success_msg.is_visible()
        assert "trader_test@momentumscan.in" in success_msg.text_content()
        
        browser.close()
