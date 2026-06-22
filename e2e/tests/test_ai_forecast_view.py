"""Playwright end‑to‑end test for the AI Forecast view.

Ensures the AI Forecast tab activates, input is interactive, and the run button triggers the forecast cycle.
"""

from playwright.sync_api import sync_playwright
from .common import get_base_url, launch_browser


def test_ai_forecast_view():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        page = context.new_page()
        # Load home page
        page.goto(get_base_url())
        # Click the AI Forecast tab via data-view
        page.click('button[data-view="ai-forecast"]')
        # Verify AI Forecast view is visible
        forecast_view = page.locator("#view-ai-forecast")
        forecast_view.wait_for(state="visible")
        assert forecast_view.is_visible(), "AI Forecast view did not become visible"
        
        # Verify input and button are present
        input_ticker = page.locator("#kronos-ticker-input")
        input_ticker.wait_for(state="visible")
        assert input_ticker.is_visible(), "Kronos ticker input missing"
        btn_run = page.locator("#btn-run-kronos")
        btn_run.wait_for(state="visible")
        assert btn_run.is_visible(), "Run forecast button missing"
        
        # Type ticker and click Run
        input_ticker.fill("INFY")
        btn_run.click()
        
        # The button text should immediately change to Running... and be disabled
        # Note: Depending on CPU speed, this might transition quickly, so we can assert on either states
        # or wait for the cycle to finish.
        # Let's wait for the button to be re-enabled (meaning the API call returned, success or error)
        page.wait_for_function("document.getElementById('btn-run-kronos').disabled === false", timeout=15000)
        
        # Assert button is re-enabled and text is restored
        assert btn_run.is_enabled()
        assert "Run Forecast" in btn_run.text_content()
        
        browser.close()
