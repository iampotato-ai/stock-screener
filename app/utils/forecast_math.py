import numpy as np
import pandas as pd
from collections import deque

def _mean(lst):
    return sum(lst) / len(lst) if lst else 0.0

def _std(lst):
    if not lst:
        return 0.0
    m = sum(lst) / len(lst)
    variance = sum((x - m) ** 2 for x in lst) / len(lst)
    return variance ** 0.5

def _norm(val, lo, hi):
    """Linearly map val from [lo, hi] to [-1, +1], clamped."""
    raw = (val - lo) / ((hi - lo) / 2.0 + 1e-9) - 1.0
    return max(-1.0, min(1.0, raw))

# Configuration for forecast scoring
METRIC_WEIGHTS = {
    "s1": 0.20,
    "s2": 0.20,
    "s3": 0.25,
    "s4": 0.25,
    "s5": 0.10,
    "s6": 0.10,
}
PERCENTILE_BUFFER_SIZE = 500
ENABLE_PERCENTILE_BIAS = True  # can be toggled via app config if needed
# Circular buffer of recent weighted scores for percentile mapping
_SCORE_BUFFER = deque(maxlen=PERCENTILE_BUFFER_SIZE)
def compute_atr_pct(history, window=14):
    """Compute ATR as % of last close over `window` trading days."""
    if len(history) < window + 1:
        return 5.0  # default fallback
    tr_list = []
    for i in range(len(history) - window, len(history)):
        h_val = float(history[i]["high"])
        l_val = float(history[i]["low"])
        p_close = float(history[i-1]["close"])
        tr = max(h_val - l_val, abs(h_val - p_close), abs(l_val - p_close))
        tr_list.append(tr)
    atr = sum(tr_list) / window
    curr_close = float(history[-1]["close"])
    return (atr / curr_close) * 100 if curr_close > 0 else 5.0

def compute_forecast_metrics(forecast_list, last_close, history, extra_context=None):
    """
    Computes forecast scoring metrics, forecast bias, and confidence score.
    Returns: (ai_forecast_bias, ai_confidence_score, forecast_metrics)
    """
    if not forecast_list:
        return None, 0, {}

    # ---- Extract basic series -------------------------------------------------
    forecast_closes = [r["close"] for r in forecast_list]
    forecast_highs = [r["high"] for r in forecast_list]
    current_close = last_close

    # ---- Metric M1: Endpoint Return % ----------------------------------------
    m1_return_pct = (forecast_closes[-1] - current_close) / (current_close + 1e-5) * 100

    # ---- Metric M2: Momentum Split ------------------------------------------
    early_len = min(3, len(forecast_closes))
    late_len = min(3, len(forecast_closes))
    early_avg = _mean(forecast_closes[:early_len]) if early_len else current_close
    late_avg = _mean(forecast_closes[-late_len:]) if late_len else current_close
    m2_split_pct = (late_avg - early_avg) / (current_close + 1e-5) * 100

    # ---- Metric M3: Consistency % ------------------------------------------
    if len(forecast_closes) > 1:
        up_days = sum(1 for i in range(1, len(forecast_closes)) if forecast_closes[i] > forecast_closes[i-1])
        m3_consistency_pct = up_days / (len(forecast_closes) - 1) * 100
    else:
        m3_consistency_pct = 50.0

    # ---- Metric M4: Breakout above recent 20‑day high -----------------------
    highs = [day["high"] for day in history]
    recent_20d_high = max(highs[-21:-1]) if len(highs) >= 21 else max(highs)
    m4_breakout = max(forecast_highs) > recent_20d_high

    # ---- Metric M5: Max drawdown ------------------------------------------
    m5_drawdown_pct = (min(forecast_closes) - current_close) / (current_close + 1e-5) * 100

    # ---- Metric S6: ATR volatility signal ---------------------------------
    atr_pct = compute_atr_pct(history, window=14)
    s6 = _norm(atr_pct, 0, 5)

    # ---- Normalise individual scores ---------------------------------------
    s1 = _norm(m1_return_pct, -10, 10)
    s2 = _norm(m2_split_pct, -5, 5)
    s3 = _norm(m3_consistency_pct, 30, 70)
    s4 = 1.0 if m4_breakout else -0.2
    s5 = _norm(-m5_drawdown_pct, -8, 0)

    # ---- Weighted score using configurable METRIC_WEIGHTS -----------------
    metric_vals = {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5, "s6": s6}
    raw_score = sum(METRIC_WEIGHTS[k] * metric_vals[k] for k in METRIC_WEIGHTS)
    weighted_score = raw_score / sum(METRIC_WEIGHTS.values())
    weighted_score = max(-1.0, min(1.0, weighted_score))

    # ---- Store score in circular buffer for percentile mapping ------------
    _SCORE_BUFFER.append(weighted_score)

    # ---- Bias mapping ------------------------------------------------------
    forecast_metrics = {}
    if ENABLE_PERCENTILE_BIAS and len(_SCORE_BUFFER) >= 5:
        pct = (sum(1 for score in _SCORE_BUFFER if score < weighted_score) / len(_SCORE_BUFFER)) * 100
        if pct >= 80:
            ai_forecast_bias = "Strong Breakout"
        elif pct >= 60:
            ai_forecast_bias = "Bullish Continuation"
        elif pct >= 40:
            ai_forecast_bias = "Sideways Consolidation"
        elif pct >= 20:
            ai_forecast_bias = "Bearish Pressure"
        else:
            ai_forecast_bias = "Strong Downtrend"
        forecast_metrics["percentile"] = round(pct, 1)
    else:
        # Fallback static thresholds (unchanged behavior)
        if weighted_score > 0.40:
            ai_forecast_bias = "Strong Breakout"
        elif weighted_score > 0.15:
            ai_forecast_bias = "Bullish Continuation"
        elif weighted_score > -0.15:
            ai_forecast_bias = "Sideways Consolidation"
        elif weighted_score > -0.40:
            ai_forecast_bias = "Bearish Pressure"
        else:
            ai_forecast_bias = "Strong Downtrend"

    # ---- Confidence score (preserve original logic) -----------------------
    # Realised return std from history
    hist_closes = [float(d["close"]) for d in history]
    realised_returns = []
    horizon = len(forecast_list)
    for i in range(horizon, len(hist_closes)):
        r = (hist_closes[i] - hist_closes[i - horizon]) / (hist_closes[i - horizon] + 1e-5) * 100
        realised_returns.append(r)
    realised_std = _std(realised_returns) if len(realised_returns) >= 5 else 5.0
    normalised_return = m1_return_pct / (realised_std + 1e-5)

    # CV and flat‑forecast handling (unchanged)
    atr_for_flat = atr_pct  # Reused from above!
    fc_mean = _mean(forecast_closes)
    fc_std = _std(forecast_closes)
    cv = fc_std / (fc_mean + 1e-5)
    forecast_range_pct = (max(forecast_closes) - min(forecast_closes)) / (current_close + 1e-5) * 100
    is_flat_forecast = forecast_range_pct < atr_for_flat
    cv_weight = 0.20 if is_flat_forecast else 0.40
    cv_score = max(0.0, min(1.0, 1.0 - cv * 10.0))
    if weighted_score > 0:
        cons_score = max(0.0, min(1.0, (m3_consistency_pct - 50) / 50))
    elif weighted_score < 0:
        cons_score = max(0.0, min(1.0, (50 - m3_consistency_pct) / 50))
    else:
        cons_score = 0.0
    cons_weight = 0.50 if is_flat_forecast else 0.40
    mag_score = abs(weighted_score)
    mag_weight = 0.30 if is_flat_forecast else 0.20
    ai_confidence_score = int(max(25.0, min(92.0, (cv_weight * cv_score + cons_weight * cons_score + mag_weight * mag_score) * 100)))

    # ---- Populate metric dict (keep original keys that callers expect) ----
    forecast_metrics.update({
        "return_pct": round(m1_return_pct, 2),
        "momentum_split": round(m2_split_pct, 2),
        "consistency_pct": round(m3_consistency_pct, 2),
        "breakout_signal": bool(m4_breakout),
        "max_drawdown_pct": round(m5_drawdown_pct, 2),
        "weighted_score": round(weighted_score, 3),
        "normalised_return": round(normalised_return, 2),
        "realised_std_10d": round(realised_std, 2),
        "forecast_range_pct": round(forecast_range_pct, 2),
        "is_flat_forecast": bool(is_flat_forecast),
    })
    return ai_forecast_bias, ai_confidence_score, forecast_metrics
