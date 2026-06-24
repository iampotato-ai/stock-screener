import sys
sys.path.insert(0, 'C:/Users/91996/Documents/My Projects/stock-screener')
import logging

logging.basicConfig(level=logging.INFO)

from app.services.bull_snort_service import screen_bull_snort
from app.database import FALLBACK_NSE_SYMBOLS

symbols = list(FALLBACK_NSE_SYMBOLS)  # Convert tuple to list
print(f"Testing {len(symbols)} symbols with parameters: vol_surge_min=2.0, max_current_gap=10.0, close_position_min=0.50")

# Parameters as requested
results = screen_bull_snort(
    symbols=symbols,
    vol_avg_period=20,
    vol_surge_min=2.0,      # requested
    close_position_min=0.50, # requested
    min_gap_history=10.0,
    max_current_gap=10.0    # requested
)

print(f"Number of results: {len(results)}")
if len(results) > 0:
    print("Results (sorted by final_score descending):")
    for i, r in enumerate(results[:20]):  # show top 20
        print(f"  {i+1}. {r['symbol']}: score {r['final_score']:.2f}")
else:
    print("No symbols passed the filter.")
    # Optional: debug one symbol to see why it fails
    from app.utils.technical import fetch_historical_prices
    import pandas as pd
    import numpy as np

    # Constants from the service
    MIN_ROWS_REQUIRED = 230
    BASE_LOOKBACK_DAYS = 126
    BASE_NO_NEW_LOW_WINDOW = 10

    symbol = "RELIANCE"
    data = fetch_historical_prices(symbol, range_str="2y")
    print(f"\nDebugging {symbol}: data length {len(data)}")
    df = pd.DataFrame(data)
    df.columns = df.columns.str.lower()
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()
    close = df["close"]
    volume = df["volume"]
    high = df["high"]
    low = df["low"]
    dma200 = close.rolling(200).mean()
    if np.isnan(dma200.iloc[-1]):
        print("DMA200 is NaN")
    else:
        # Phase 1
        gap_series = (dma200 - close) / close * 100
        max_gap_6mo = gap_series.iloc[-BASE_LOOKBACK_DAYS:].max()
        print(f"Max gap 6mo: {max_gap_6mo:.2f}% (need >=10.0)")
        dma_slope = (dma200.iloc[-1] - dma200.iloc[-21]) / 20
        norm_slope = (dma_slope / dma200.iloc[-1]) * 100
        print(f"Norm slope: {norm_slope:.4f}% (need <0)")
        # Phase 2
        current_gap = (dma200.iloc[-1] - close.iloc[-1]) / close.iloc[-1] * 100
        print(f"Current gap: {current_gap:.2f}% (need 0-10.0)")
        # Phase 4 (requested)
        today_close = close.iloc[-1]
        prev_close = close.iloc[-2]
        today_high = high.iloc[-1]
        today_low = low.iloc[-1]
        today_vol = volume.iloc[-1]
        avg_vol = volume.iloc[-(20+1):-1].mean()
        vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0.0
        is_vol_surge = vol_ratio >= 2.0
        is_positive = today_close > prev_close
        candle_range = today_high - today_low
        close_position = (today_close - today_low) / candle_range if candle_range != 0 else 0
        is_strong_close = close_position >= 0.50
        print(f"Vol ratio: {vol_ratio:.2f} (need >=2.0) -> {is_vol_surge}")
        print(f"Positive day: {is_positive}")
        print(f"Close position: {close_position:.3f} (need >=0.50) -> {is_strong_close}")
        print(f"Volume surge? {is_vol_surge}")