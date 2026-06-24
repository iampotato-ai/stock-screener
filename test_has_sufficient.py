import sys
sys.path.insert(0, 'C:/Users/91996/Documents/My Projects/stock-screener')

from app.services.bull_snort_service import _has_sufficient_history
from app.utils.technical import fetch_historical_prices

symbol = "RELIANCE"
data = fetch_historical_prices(symbol, range_str="2y")
print(f"Data length: {len(data)}")
result = _has_sufficient_history(symbol, data)
print(f"_has_sufficient_history returned: {result}")

# Also test without data argument (should fetch inside)
result2 = _has_sufficient_history(symbol)
print(f"_has_sufficient_history (without data) returned: {result2}")