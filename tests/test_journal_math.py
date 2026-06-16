import pytest
from app.utils.journal_math import compute_pnl_and_r

@pytest.mark.parametrize(
    "entry, stop, qty, exit_price, risk_amount, expected_pnl, expected_r",
    [
        # 1. Simple profit target hit
        (100.0, 90.0, 10, 110.0, None, 100.0, 1.0),
        # 2. Stopped out long trade
        (100.0, 90.0, 10, 90.0, None, -100.0, -1.0),
        # 3. Stopped out with slippage (gap down exit)
        (100.0, 90.0, 10, 85.0, None, -150.0, -1.5),
        # 4. Explicit risk amount override
        (100.0, 90.0, 10, 120.0, 50.0, 200.0, 4.0),
        # 5. Breakeven exit
        (100.0, 90.0, 10, 100.0, None, 0.0, 0.0),
        # 6. Stop not provided (defaults to risk = 1.0)
        (100.0, None, 10, 110.0, None, 100.0, 100.0),
        # 7. Zero qty
        (100.0, 90.0, 0, 110.0, None, 0.0, 0.0),
        # 8. Same entry and stop (risk defaults to 0.0)
        (100.0, 100.0, 10, 110.0, None, 100.0, 0.0),
        # 9. None exit price or inputs (type casting fallbacks)
        (None, None, None, None, None, 0.0, 0.0),
    ]
)
def test_compute_pnl_and_r(entry, stop, qty, exit_price, risk_amount, expected_pnl, expected_r):
    pnl, r = compute_pnl_and_r(entry, stop, qty, exit_price, risk_amount)
    assert pnl == expected_pnl
    assert r == expected_r
