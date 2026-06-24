import sys
sys.path.insert(0, 'C:/Users/91996/Documents/My Projects/stock-screener')

from app.services.bull_snort_service import screen_bull_snort
from app.database import get_nse_symbols

# Get the fallback symbols (the ones used when the database is empty)
# But note: the endpoint uses get_nse_symbols() which returns the fallback if the database is empty.
# However, in our case, the database might not be empty? We don't know.
# Let's just use the fallback list from the database module for consistency.
from app.database import FALLBACK_NSE_SYMBOLS

symbols = list(FALLBACK_NSE_SYMBOLS)  # Convert tuple to list
print(f"Testing {len(symbols)} symbols: {symbols}")

# We'll use the default parameters
results = screen_bull_snort(
    symbols=symbols,
    vol_avg_period=20,
    vol_surge_min=3.0,
    close_position_min=0.65,
    min_gap_history=10.0,
    max_current_gap=5.0
)

print(f"Number of results: {len(results)}")
if len(results) > 0:
    print("First few results:")
    for i, r in enumerate(results[:5]):
        print(f"  {i+1}. {r['symbol']}: score {r['final_score']}")
else:
    print("No symbols passed the Bull Snort filter.")
    # Let's check why by testing one symbol in detail (we already did RELIANCE and TCS)