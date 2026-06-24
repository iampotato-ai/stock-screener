import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import numpy as np
from app.utils.technical import fetch_historical_prices

# Constants from the service
MIN_ROWS_REQUIRED = 230
DEFAULT_VOL_AVG_PERIOD = 20
DEFAULT_VOL_SURGE_MIN = 3.0
DEFAULT_CLOSE_POSITION_MIN = 0.65
DEFAULT_MIN_GAP_HISTORY = 10.0
DEFAULT_MAX_CURRENT_GAP = 5.0
BASE_LOOKBACK_DAYS = 126  # 6 months of trading days
BASE_NO_NEW_LOW_WINDOW = 10  # Phase 2: no new low in last N sessions

symbol = "RELIANCE"
data = fetch_historical_prices(symbol, range_str="2y")
print(f"Data length: {len(data)}")

# Convert list of dicts to pandas DataFrame
df = pd.DataFrame(data)
df.columns = df.columns.str.lower()  # Normalize to lowercase
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date')
df = df.sort_index()  # Ensure chronological order

close = df["close"]
volume = df["volume"]
high = df["high"]
low = df["low"]
dma200 = close.rolling(200).mean()

print(f"Latest close: {close.iloc[-1]:.2f}")
print(f"DMA200: {dma200.iloc[-1]:.2f}")
print(f"Is DMA200 NaN? {np.isnan(dma200.iloc[-1])}")

# Phase 1 – deep downtrend & DMA still declining
gap_series = (dma200 - close) / close * 100
max_gap_6mo = gap_series.iloc[-BASE_LOOKBACK_DAYS :].max()
print(f"Max gap (6mo): {max_gap_6mo:.2f}%")
print(f"Min gap history required: {DEFAULT_MIN_GAP_HISTORY}%")
print(f"Passes max_gap_6mo >= min_gap_history? {max_gap_6mo >= DEFAULT_MIN_GAP_HISTORY}")

dma_slope = (dma200.iloc[-1] - dma200.iloc[-21]) / 20
norm_slope = (dma_slope / dma200.iloc[-1]) * 100
print(f"DMA200 slope (20-day): {dma_slope:.4f}")
print(f"Normalized slope: {norm_slope:.4f}%")
print(f"Norm slope < 0? {norm_slope < 0}")  # We require norm_slope < 0

# Phase 2 – base formation
recent_lows = low.iloc[-(BASE_NO_NEW_LOW_WINDOW + 1) : -1]
print(f"Recent lows (last {BASE_NO_NEW_LOW_WINDOW} days): {recent_lows.values}")
print(f"Min of recent lows: {recent_lows.min():.2f}")
print(f"Today's low: {low.iloc[-1]:.2f}")
print(f"Today's low >= min recent lows? {low.iloc[-1] >= recent_lows.min()}")

current_gap = (dma200.iloc[-1] - close.iloc[-1]) / close.iloc[-1] * 100
print(f"Current gap (DMA200 - close)/close * 100: {current_gap:.2f}%")
print(f"Current gap between 0 and {DEFAULT_MAX_CURRENT_GAP}%? {0 <= current_gap <= DEFAULT_MAX_CURRENT_GAP}")

# Phase 3 – accumulation score (we'll skip the detailed calculation for now)
# But we can compute it if needed

# Phase 4 – candlestick breakout
today_close = close.iloc[-1]
prev_close = close.iloc[-2]
today_high = high.iloc[-1]
today_low = low.iloc[-1]
today_vol = volume.iloc[-1]
avg_vol = volume.iloc[-(DEFAULT_VOL_AVG_PERIOD + 1) : -1].mean()
vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0.0
is_vol_surge = vol_ratio >= DEFAULT_VOL_SURGE_MIN
is_positive = today_close > prev_close
candle_range = today_high - today_low
if candle_range == 0:
    close_position = 0
else:
    close_position = (today_close - today_low) / candle_range
is_strong_close = close_position >= DEFAULT_CLOSE_POSITION_MIN

print(f"Today's close: {today_close:.2f}")
print(f"Previous close: {prev_close:.2f}")
print(f"Today's high: {today_high:.2f}")
print(f"Today's low: {today_low:.2f}")
print(f"Today's volume: {today_vol}")
print(f"Average volume ({DEFAULT_VOL_AVG_PERIOD} days): {avg_vol:.0f}")
print(f"Volume ratio: {vol_ratio:.2f}")
print(f"Is volume surge? {is_vol_surge} (>= {DEFAULT_VOL_SURGE_MIN})")
print(f"Is positive day? {is_positive} (today_close > prev_close)")
print(f"Candle range: {candle_range:.2f}")
print(f"Close position (close-low)/(high-low): {close_position:.3f}")
print(f"Is strong close? {is_strong_close} (>= {DEFAULT_CLOSE_POSITION_MIN})")

# Now, let's see which condition fails
print("\n--- Failure checklist ---")
if np.isnan(dma200.iloc[-1]):
    print("FAIL: DMA200 is NaN")
if max_gap_6mo < DEFAULT_MIN_GAP_HISTORY:
    print(f"FAIL: max_gap_6mo ({max_gap_6mo:.2f}%) < min_gap_history ({DEFAULT_MIN_GAP_HISTORY}%)")
if norm_slope >= 0:
    print(f"FAIL: norm_slope ({norm_slope:.4f}%) >= 0 (need negative slope)")
if low.iloc[-1] < recent_lows.min():
    print(f"FAIL: today's low ({low.iloc[-1]:.2f}) < min recent lows ({recent_lows.min():.2f})")
if not (0 <= current_gap <= DEFAULT_MAX_CURRENT_GAP):
    print(f"FAIL: current_gap ({current_gap:.2f}%) not in [0, {DEFAULT_MAX_CURRENT_GAP}]")
if not is_vol_surge:
    print(f"FAIL: volume ratio ({vol_ratio:.2f}) < surge min ({DEFAULT_VOL_SURGE_MIN})")
if not is_positive:
    print(f"FAIL: not a positive day (today_close {today_close:.2f} <= prev_close {prev_close:.2f})")
if candle_range == 0:
    print("FAIL: candle range is zero")
if not is_strong_close:
    print(f"FAIL: close position ({close_position:.3f}) < min close position ({DEFAULT_CLOSE_POSITION_MIN})")