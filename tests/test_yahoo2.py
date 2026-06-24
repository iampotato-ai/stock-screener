import sys
sys.path.insert(0, 'C:/Users/91996/Documents/My Projects/stock-screener')

from app.utils.technical import fetch_historical_prices

# Test with a known symbol
symbol = "TCS"
data = fetch_historical_prices(symbol, range_str="2y")
print(f"Fetched {len(data)} rows for {symbol}")
if data:
    print("First row:", data[0])
    print("Last row:", data[-1])
else:
    print("No data returned")