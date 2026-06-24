import sys
sys.path.insert(0, 'C:/Users/91996/Documents/My Projects/stock-screener')

from unittest.mock import patch
from app.services.bull_snort_service import screen_bull_snort
from tests.unit.test_bull_snort_service import make_df

def test_screen_bull_snort_skip_insufficient_data():
    symbols = ["SKIP", "PASS"]  # SKIP will have insufficient data, PASS sufficient

    def mock_fetch(symbol, range_str="2y"):
        if symbol == "SKIP":
            return make_df(100)  # insufficient data
        else:  # PASS
            return make_df(300)  # sufficient data

    with patch("app.services.bull_snort_service.fetch_historical_prices", side_effect=mock_fetch) as mock_fetch, \
         patch("app.services.bull_snort_service.compute_bull_snort", return_value={"symbol": "TEST", "final_score": 85}) as mock_compute:
        results = screen_bull_snort(symbols)
        print(f"Results: {results}")
        print(f"Number of results: {len(results)}")
        print(f"fetch_historical_prices called {mock_fetch.call_count} times")
        print(f"compute_bull_snort called {mock_compute.call_count} times")
        # We expect fetch_historical_prices to be called twice (once for each symbol)
        # We expect compute_bull_snort to be called only once (for PASS)
        assert mock_fetch.call_count == 2, f"Expected fetch_historical_prices to be called 2 times, but was called {mock_fetch.call_count} times"
        assert mock_compute.call_count == 1, f"Expected compute_bull_snort to be called 1 time, but was called {mock_compute.call_count} times"
        assert len(results) == 1, f"Expected 1 result, but got {len(results)}"
        print("All assertions passed!")

if __name__ == "__main__":
    test_screen_bull_snort_skip_insufficient_data()