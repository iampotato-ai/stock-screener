import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.bull_snort_service import compute_bull_snort
from app.utils.technical import fetch_historical_prices

symbol = "RELIANCE"
data = fetch_historical_prices(symbol, range_str="2y")
print(f"Data length: {len(data)}")

# Call compute_bull_snort with the data
result = compute_bull_snort(symbol, data=data)
print(f"Result: {result}")
if result is None:
    print("compute_bull_snort returned None")
else:
    print(f"Result keys: {result.keys()}")
    print(f"Final score: {result.get('final_score')}")