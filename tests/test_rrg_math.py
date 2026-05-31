import pytest
from rrg_math import compute_jdk_rs, compute_quadrant

@pytest.mark.parametrize(
    "sector_return, bench_return, expected_rs",
    [
        # 1. Standard positive returns
        (10.0, 5.0, 104.76190476190476),
        # 2. Both returns equal
        (5.0, 5.0, 100.0),
        # 3. Negative returns
        (-10.0, -5.0, 94.73684210526316),
        # 4. Sector down, bench flat
        (-5.0, 0.0, 95.0),
        # 5. Sector up, bench down
        (5.0, -5.0, 110.52631578947368),
        # 6. Benchmark return is -100% (denom = 0.0 guard)
        (10.0, -100.0, 100.0),
        # 7. Missing inputs fallback
        (None, None, 100.0),
    ]
)
def test_compute_jdk_rs(sector_return, bench_return, expected_rs):
    rs = compute_jdk_rs(sector_return, bench_return)
    assert pytest.approx(rs) == expected_rs

@pytest.mark.parametrize(
    "jdk_rs, rs_momentum, expected_quadrant",
    [
        # 1. RS >= 100, Momentum >= 0 -> Leading
        (105.0, 1.2, "Leading"),
        (100.0, 0.0, "Leading"),
        # 2. RS >= 100, Momentum < 0 -> Weakening
        (102.5, -0.5, "Weakening"),
        (100.0, -0.01, "Weakening"),
        # 3. RS < 100, Momentum < 0 -> Lagging
        (98.0, -1.5, "Lagging"),
        (99.9, -0.01, "Lagging"),
        # 4. RS < 100, Momentum >= 0 -> Improving
        (97.5, 0.5, "Improving"),
        (99.9, 0.0, "Improving"),
        (0.0, 10.0, "Improving"),
    ]
)
def test_compute_quadrant(jdk_rs, rs_momentum, expected_quadrant):
    quad = compute_quadrant(jdk_rs, rs_momentum)
    assert quad == expected_quadrant
