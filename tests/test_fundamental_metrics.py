import pytest
from app.api.v1.legacy_routes import compute_extra_fields
import app.api.v1.legacy_routes as lr

def test_compute_extra_fields_calculation():
    # Set up mock stock with exact fields
    stock = {
        "name": "TESTSTOCK",
        "sector": "Technology Services",
        "market_cap_basic": 1000000000.0,
        "price_earnings_ttm": 20.0,
        "price_book_fq": 2.5,
        "price_sales_ratio": 4.0,
        "gross_margin_ttm": 50.0,
        "ebitda_margin_ttm": 25.0,
        "return_on_equity_fq": 15.0,
        "return_on_capital_employed_fq": 18.0,
        "return_on_assets_fq": 5.0,
        "debt_to_equity_fq": 0.5,
        "current_ratio_fq": 1.8,
        "quick_ratio_fq": 1.2,
        "price_earnings_growth_ttm": 0.8,
        "total_revenue_yoy_growth_ttm": 12.0,
        "total_revenue_qoq_growth_fq": 4.0,
        "net_income_yoy_growth_ttm": 15.0,
        "total_revenue_cagr_5y": 14.0,
        "net_income_cagr_5y": 16.0,
        "ebitda_yoy_growth_ttm": 18.0,
        "free_cash_flow_margin_ttm": 20.0,
        "net_margin_ttm": 10.0,
        "free_cash_flow_ttm": 200000000.0,
        "net_income_ttm": 100000000.0
    }

    # Temporarily disable simulated data to verify pure math calculations
    original_sim = lr.ENABLE_SIMULATED_DATA
    lr.ENABLE_SIMULATED_DATA = False

    try:
        compute_extra_fields(stock)

        # 1. Earnings Yield
        assert stock["earnings_yield"] == pytest.approx(5.0)

        # 2. Graham Multiplier
        assert stock["graham_multiplier"] == pytest.approx(50.0)

        # 3. CFO / EBITDA
        assert stock["cfo_ebitda"] == pytest.approx(80.0)

        # 4. CFO / PAT
        assert stock["cfo_pat"] == pytest.approx(200.0)

        # 5. Asset Turnover
        assert stock["asset_turnover"] == pytest.approx(0.5)

        # 6. Financial Leverage
        assert stock["financial_leverage"] == pytest.approx(3.0)

        # 7. Operating Leverage
        assert stock["operating_leverage"] == pytest.approx(1.5)

        # 8. Extra fields extracted correctly
        assert stock["current_ratio"] == 1.8
        assert stock["quick_ratio"] == 1.2
        assert stock["peg_ratio"] == 0.8
        assert stock["revenue_growth_yoy"] == 12.0
        assert stock["revenue_growth_qoq"] == 4.0
        assert stock["profit_growth"] == 15.0
        assert stock["revenue_growth_5y"] == 14.0
        assert stock["net_income_cagr_5y"] == 16.0
        assert stock["ebitda_cagr_3y"] == 18.0
        assert stock["fcf_margin"] == 20.0
        assert stock["net_margin"] == 10.0

    finally:
        lr.ENABLE_SIMULATED_DATA = original_sim

def test_compute_extra_fields_simulation():
    # Test simulation fallback generation when input fields are empty/None
    stock = {
        "name": "SIMSTOCK",
        "sector": "Banking",
        "market_cap_basic": 5000000000.0,
    }

    original_sim = lr.ENABLE_SIMULATED_DATA
    lr.ENABLE_SIMULATED_DATA = True

    try:
        compute_extra_fields(stock)

        # Check that simulated values are generated and valid
        assert stock["pe_ratio"] is not None
        assert stock["earnings_yield"] is not None
        assert stock["peg_ratio"] is not None
        assert stock["ev_ebitda"] is not None
        assert stock["pb_ratio"] is not None
        assert stock["graham_multiplier"] is not None
        assert stock["roe"] is not None
        assert stock["roce"] is not None
        assert stock["roa"] is not None
        assert stock["current_ratio"] is not None
        assert stock["quick_ratio"] is not None
        assert stock["debt_to_equity"] is not None
        assert stock["asset_turnover"] is not None
        assert stock["financial_leverage"] is not None
        assert stock["revenue_growth_qoq"] is not None
        assert stock["revenue_growth_yoy"] is not None
        assert stock["revenue_growth_5y"] is not None
        assert stock["profit_growth"] is not None
        assert stock["ebitda_cagr_3y"] is not None
        assert stock["net_income_cagr_5y"] is not None
        assert stock["operating_leverage"] is not None
        assert stock["wc_intensity"] is not None

    finally:
        lr.ENABLE_SIMULATED_DATA = original_sim
