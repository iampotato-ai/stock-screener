"""
Financial and technical indicator calculation utilities for Momentum Confidence Score.
Contains pure-Python functions for computing EMA, MACD, ADX, SuperTrend, volatility,
and YoY growth calculations without external dependencies.
"""

import math
from typing import List, Tuple, Optional


def compute_ema(prices: List[float], period: int) -> List[float]:
    """
    Compute Exponential Moving Average (EMA) for a series of prices.

    Args:
        prices: List of price values (oldest to newest)
        period: EMA period (e.g., 20 for 20-day EMA)

    Returns:
        List of EMA values (same length as prices, with NaN for insufficient data)
    """
    if len(prices) < period:
        return [float('nan')] * len(prices)

    # Calculate multiplier
    multiplier = 2.0 / (period + 1)

    # Initialize EMA list
    ema_values = [float('nan')] * len(prices)

    # Find first non-NaN value to start calculation
    start_idx = None
    for i in range(len(prices)):
        if not math.isnan(prices[i]):
            start_idx = i
            break

    # If all values are NaN, return all NaN
    if start_idx is None:
        return ema_values

    # If we don't have enough non-NaN values after start_idx, return all NaN
    non_nan_count = sum(1 for i in range(start_idx, len(prices)) if not math.isnan(prices[i]))
    if non_nan_count < period:
        return ema_values

    # Calculate SMA for first period non-NaN values starting from start_idx
    # Collect the first 'period' non-NaN values
    valid_prices = []
    for i in range(start_idx, len(prices)):
        if not math.isnan(prices[i]):
            valid_prices.append(prices[i])
        if len(valid_prices) >= period:
            break

    if len(valid_prices) < period:
        return ema_values

    sma = sum(valid_prices[:period]) / period
    # Find the index of the period-th non-NaN value
    valid_count = 0
    sma_idx = start_idx
    for i in range(start_idx, len(prices)):
        if not math.isnan(prices[i]):
            valid_count += 1
            if valid_count == period:
                sma_idx = i
                break

    ema_values[sma_idx] = sma

    # Calculate EMA for remaining values
    for i in range(sma_idx + 1, len(prices)):
        if not math.isnan(ema_values[i-1]):
            if not math.isnan(prices[i]):
                ema_values[i] = (prices[i] * multiplier) + (ema_values[i-1] * (1 - multiplier))
            else:
                ema_values[i] = ema_values[i-1]  # If price is NaN, EMA stays the same
        else:
            ema_values[i] = float('nan')

    return ema_values


def compute_macd(prices: List[float], fast_period: int = 12, slow_period: int = 26,
                 signal_period: int = 9) -> Tuple[List[float], List[float], List[float]]:
    """
    Compute MACD (Moving Average Convergence Divergence) line, signal line, and histogram.

    Args:
        prices: List of price values (oldest to newest)
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
        signal_period: Signal line EMA period (default: 9)

    Returns:
        Tuple of (macd_line, signal_line, histogram) lists
    """
    if len(prices) < slow_period:
        na_list = [float('nan')] * len(prices)
        return na_list, na_list, na_list

    # Calculate fast and slow EMAs
    ema_fast = compute_ema(prices, fast_period)
    ema_slow = compute_ema(prices, slow_period)

    # Calculate MACD line (fast EMA - slow EMA)
    macd_line = []
    for i in range(len(prices)):
        if math.isnan(ema_fast[i]) or math.isnan(ema_slow[i]):
            macd_line.append(float('nan'))
        else:
            macd_line.append(ema_fast[i] - ema_slow[i])

    # Calculate signal line (EMA of MACD line)
    signal_line = compute_ema(macd_line, signal_period)

    # Calculate histogram (MACD line - signal line)
    histogram = []
    for i in range(len(prices)):
        if math.isnan(macd_line[i]) or math.isnan(signal_line[i]):
            histogram.append(float('nan'))
        else:
            histogram.append(macd_line[i] - signal_line[i])

    return macd_line, signal_line, histogram


def compute_adx(highs: List[float], lows: List[float], closes: List[float],
                period: int = 14) -> List[float]:
    """
    Compute ADX (Average Directional Index) using Wilder's method.

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of close prices
        period: ADX period (default: 14)

    Returns:
        List of ADX values
    """
    if len(highs) < period + 1:
        return [float('nan')] * len(highs)

    # Calculate True Range (TR)
    tr_values = [float('nan')] * len(highs)
    for i in range(1, len(highs)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        tr_values[i] = max(high_low, high_close, low_close)

    # Calculate Directional Movement (+DM and -DM)
    plus_dm = [float('nan')] * len(highs)
    minus_dm = [float('nan')] * len(highs)

    for i in range(1, len(highs)):
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]

        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        else:
            plus_dm[i] = 0.0

        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
        else:
            minus_dm[i] = 0.0

    # Smoothed TR, +DM, -DM using Wilder's smoothing (similar to EMA but with 1/period)
    def wilders_smoothing(values, period):
        """Apply Wilder's smoothing (similar to EMA with alpha = 1/period)"""
        if len(values) < period:
            return [float('nan')] * len(values)

        smoothed = [float('nan')] * len(values)
        # First value is simple average
        smoothed[period-1] = sum(values[1:period+1]) / period

        # Subsequent values
        for i in range(period, len(values)):
            if not math.isnan(smoothed[i-1]) and not math.isnan(values[i]):
                smoothed[i] = (smoothed[i-1] * (period - 1) + values[i]) / period
            else:
                smoothed[i] = float('nan')
        return smoothed

    tr_smoothed = wilders_smoothing(tr_values, period)
    plus_dm_smoothed = wilders_smoothing(plus_dm, period)
    minus_dm_smoothed = wilders_smoothing(minus_dm, period)

    # Calculate Directional Indicators (+DI and -DI)
    plus_di = [float('nan')] * len(highs)
    minus_di = [float('nan')] * len(highs)
    dx = [float('nan')] * len(highs)

    for i in range(len(highs)):
        if not math.isnan(tr_smoothed[i]) and tr_smoothed[i] != 0:
            plus_di[i] = (plus_dm_smoothed[i] / tr_smoothed[i]) * 100
            minus_di[i] = (minus_dm_smoothed[i] / tr_smoothed[i]) * 100

            if plus_di[i] + minus_di[i] != 0:
                dx[i] = abs(plus_di[i] - minus_di[i]) / (plus_di[i] + minus_di[i]) * 100

    # Calculate ADX (smoothed DX)
    adx = compute_ema(dx, period)  # Using EMA for simplicity (Wilder's smoothing is similar)

    return adx


def compute_supertrend(highs: List[float], lows: List[float], closes: List[float],
                       period: int = 10, multiplier: float = 3.0) -> Tuple[List[float], List[int]]:
    """
    Compute Supertrend indicator.

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of close prices
        period: ATR period (default: 10)
        multiplier: Multiplier for ATR (default: 3.0)

    Returns:
        Tuple of (supertrend_values, supertrend_direction) where direction is 1 for uptrend, -1 for downtrend
    """
    if len(highs) < period:
        na_list = [float('nan')] * len(highs)
        dir_list = [0] * len(highs)
        return na_list, dir_list

    # Calculate ATR (Average True Range)
    atr_values = compute_atr(highs, lows, closes, period)

    # Calculate basic upper and lower bands
    basic_ub = [0.0] * len(highs)
    basic_lb = [0.0] * len(highs)

    for i in range(len(highs)):
        if not math.isnan(atr_values[i]):
            basic_ub[i] = (highs[i] + lows[i]) / 2 + multiplier * atr_values[i]
            basic_lb[i] = (highs[i] + lows[i]) / 2 - multiplier * atr_values[i]
        else:
            basic_ub[i] = float('nan')
            basic_lb[i] = float('nan')

    # Initialize final bands
    final_ub = [float('nan')] * len(highs)
    final_lb = [float('nan')] * len(highs)

    # Calculate final upper and lower bands
    for i in range(len(highs)):
        if i == 0:
            final_ub[i] = basic_ub[i]
            final_lb[i] = basic_lb[i]
        else:
            if not math.isnan(basic_ub[i]) and not math.isnan(final_ub[i-1]) and not math.isnan(closes[i-1]):
                if basic_ub[i] < final_ub[i-1] or closes[i-1] > final_ub[i-1]:
                    final_ub[i] = basic_ub[i]
                else:
                    final_ub[i] = final_ub[i-1]
            else:
                final_ub[i] = basic_ub[i]

            if not math.isnan(basic_lb[i]) and not math.isnan(final_lb[i-1]) and not math.isnan(closes[i-1]):
                if basic_lb[i] > final_lb[i-1] or closes[i-1] < final_lb[i-1]:
                    final_lb[i] = basic_lb[i]
                else:
                    final_lb[i] = final_lb[i-1]
            else:
                final_lb[i] = basic_lb[i]

    # Calculate Supertrend
    supertrend = [float('nan')] * len(highs)
    direction = [0] * len(highs)  # 1 for uptrend, -1 for downtrend

    for i in range(len(highs)):
        if i == 0:
            supertrend[i] = final_ub[i]
            direction[i] = 1  # Start with uptrend
        else:
            if not math.isnan(supertrend[i-1]) and not math.isnan(final_ub[i]) and not math.isnan(final_lb[i]) and not math.isnan(closes[i]):
                if supertrend[i-1] == final_ub[i-1]:
                    if closes[i] <= final_ub[i]:
                        supertrend[i] = final_ub[i]
                        direction[i] = -1
                    else:
                        supertrend[i] = final_lb[i]
                        direction[i] = 1
                else:  # supertrend[i-1] == final_lb[i-1]
                    if closes[i] >= final_lb[i]:
                        supertrend[i] = final_lb[i]
                        direction[i] = 1
                    else:
                        supertrend[i] = final_ub[i]
                        direction[i] = -1
            else:
                supertrend[i] = final_ub[i] if not math.isnan(final_ub[i]) else final_lb[i]
                direction[i] = 1 if not math.isnan(final_ub[i]) else -1

    return supertrend, direction


def compute_atr(highs: List[float], lows: List[float], closes: List[float],
                period: int = 14) -> List[float]:
    """
    Compute Average True Range (ATR).

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of close prices
        period: ATR period (default: 14)

    Returns:
        List of ATR values
    """
    if len(highs) < period + 1:
        return [float('nan')] * len(highs)

    # Calculate True Range
    tr_values = [float('nan')] * len(highs)
    for i in range(1, len(highs)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        tr_values[i] = max(high_low, high_close, low_close)

    # Calculate ATR using Wilder's smoothing
    def wilders_smoothing(values, period):
        """Apply Wilder's smoothing"""
        if len(values) < period:
            return [float('nan')] * len(values)

        smoothed = [float('nan')] * len(values)
        # First value is simple average
        smoothed[period-1] = sum(values[1:period+1]) / period

        # Subsequent values
        for i in range(period, len(values)):
            if not math.isnan(smoothed[i-1]) and not math.isnan(values[i]):
                smoothed[i] = (smoothed[i-1] * (period - 1) + values[i]) / period
            else:
                smoothed[i] = float('nan')
        return smoothed

    return wilders_smoothing(tr_values, period)


def compute_volatility(prices: List[float], period: int = 30) -> float:
    """
    Calculate annualized volatility based on log returns.

    Args:
        prices: List of price values (oldest to newest)
        period: Lookback period for volatility calculation (default: 30 days)

    Returns:
        Annualized volatility as decimal (e.g., 0.25 for 25%)
    """
    if len(prices) < period + 1:
        return 0.0

    # Calculate log returns
    log_returns = []
    for i in range(1, len(prices)):
        if prices[i-1] > 0 and prices[i] > 0:
            log_returns.append(math.log(prices[i] / prices[i-1]))
        else:
            log_returns.append(0.0)

    # Use last 'period' returns
    if len(log_returns) < period:
        returns_to_use = log_returns
    else:
        returns_to_use = log_returns[-period:]

    if len(returns_to_use) < 2:
        return 0.0

    # Calculate standard deviation of returns
    mean_return = sum(returns_to_use) / len(returns_to_use)
    variance = sum((r - mean_return) ** 2 for r in returns_to_use) / len(returns_to_use)
    std_dev = math.sqrt(variance) if variance >= 0 else 0.0

    # Annualize (assuming 252 trading days per year)
    annualized_vol = std_dev * math.sqrt(252)

    return annualized_vol


def compute_yoy_growth(values: List[float]) -> float:
    """
    Calculate Year-over-Year growth percentage from a list of annual values.

    Args:
        values: List of annual values (oldest to newest, e.g., yearly revenue)

    Returns:
        YoY growth as decimal (e.g., 0.18 for 18% growth)
    """
    if len(values) < 2:
        return 0.0

    # Get most recent and year-ago values
    recent = values[-1]
    year_ago = values[-2]

    if year_ago == 0:
        return 0.0

    return (recent - year_ago) / year_ago


def compute_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    Compute Relative Strength Index (RSI).

    Args:
        prices: List of price values (oldest to newest)
        period: RSI period (default: 14)

    Returns:
        List of RSI values (0-100)
    """
    if len(prices) < period + 1:
        return [float('nan')] * len(prices)

    # Calculate price changes
    deltas = [0.0] * len(prices)
    for i in range(1, len(prices)):
        deltas[i] = prices[i] - prices[i-1]

    # Separate gains and losses
    gains = [0.0 if d < 0 else d for d in deltas]
    losses = [0.0 if d > 0 else -d for d in deltas]

    # Calculate average gains and losses
    avg_gain = sum(gains[1:period+1]) / period
    avg_loss = sum(losses[1:period+1]) / period

    # Initialize RSI list
    rsi_values = [float('nan')] * len(prices)

    # Calculate first RSI
    if avg_loss == 0:
        rsi_values[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_values[period] = 100.0 - (100.0 / (1.0 + rs))

    # Calculate remaining RSI values using Wilder's smoothing
    for i in range(period + 1, len(prices)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi_values[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi_values


def classify_technical_pattern(history: dict) -> dict:
    """
    Classify technical pattern based on price history.
    Simplified implementation - in practice this would be more sophisticated.

    Args:
        history: Dictionary containing 'highs', 'lows', 'closes', 'volumes' lists

    Returns:
        Dictionary with 'pattern' key indicating detected pattern
    """
    # Simplified pattern classification
    # In a real implementation, this would analyze price action for VCP, breakout, etc.

    closes = history.get('closes', [])
    volumes = history.get('volumes', [])

    if len(closes) < 20:
        return {'pattern': 'NO_PATTERN', 'confidence': 0.0}

    # Simple heuristic: if price is making higher highs and higher lows with increasing volume
    # and is near recent highs, suggest VCP or breakout
    recent_closes = closes[-20:]
    recent_volumes = volumes[-20:] if len(volumes) >= 20 else volumes

    # Check for higher highs and higher lows
    higher_highs = max(recent_closes[-10:]) > max(recent_closes[-20:-10]) if len(recent_closes) >= 20 else False
    higher_lows = min(recent_closes[-10:]) > min(recent_closes[-20:-10]) if len(recent_closes) >= 20 else False

    # Check for volume expansion
    avg_volume_recent = sum(recent_volumes[-5:]) / 5 if len(recent_volumes) >= 5 else 0
    avg_volume_previous = sum(recent_volumes[-10:-5]) / 5 if len(recent_volumes) >= 10 else 0
    volume_expanding = avg_volume_recent > avg_volume_previous if avg_volume_previous > 0 else False

    # Check if near recent highs
    recent_high = max(recent_closes)
    current_price = closes[-1] if closes else 0
    near_high = current_price >= (recent_high * 0.9) if recent_high > 0 else False

    if higher_highs and higher_lows and volume_expanding and near_high:
        return {'pattern': 'VCP_BREAKOUT', 'confidence': 0.8}
    elif higher_highs and higher_lows:
        return {'pattern': 'VCP', 'confidence': 0.6}
    elif near_high and volume_expanding:
        return {'pattern': 'BREAKOUT', 'confidence': 0.7}
    else:
        return {'pattern': 'NO_PATTERN', 'confidence': 0.0}