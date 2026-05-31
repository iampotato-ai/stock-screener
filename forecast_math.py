import numpy as np
import pandas as pd

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

def compute_forecast_metrics(forecast_list, last_close, history):
    """
    Computes forecast scoring metrics, forecast bias, and confidence score.
    Returns: (ai_forecast_bias, ai_confidence_score, forecast_metrics)
    """
    if not forecast_list:
        return None, 0, {}

    forecast_closes = [r["close"] for r in forecast_list]
    forecast_highs  = [r["high"] for r in forecast_list]
    current_close   = last_close

    # ── M1: Endpoint Return % ──────────────────────────────────────────
    m1_return_pct = (forecast_closes[-1] - current_close) / (current_close + 1e-5) * 100

    # ── M2: Momentum Split (early vs late 3 bars) ──────────────────────
    early_len = min(3, len(forecast_closes))
    late_len = min(3, len(forecast_closes))
    early_avg = np.mean(forecast_closes[:early_len]) if early_len > 0 else current_close
    late_avg  = np.mean(forecast_closes[-late_len:]) if late_len > 0 else current_close
    m2_split_pct = (late_avg - early_avg) / (current_close + 1e-5) * 100

    # ── M3: Day-by-Day Consistency % ──────────────────────────────────
    if len(forecast_closes) > 1:
        up_days = sum(
            1 for i in range(1, len(forecast_closes))
            if forecast_closes[i] > forecast_closes[i-1]
        )
        m3_consistency_pct = up_days / (len(forecast_closes) - 1) * 100
    else:
        m3_consistency_pct = 50.0

    # ── M4: Breakout Above 20d Recent High ────────────────────────────
    highs = [day["high"] for day in history]
    recent_20d_high = max(highs[-21:-1]) if len(highs) >= 21 else max(highs)
    m4_breakout = max(forecast_highs) > recent_20d_high

    # ── M5: Max Drawdown During Forecast Window ────────────────────────
    m5_drawdown_pct = (min(forecast_closes) - current_close) / (current_close + 1e-5) * 100

    # ── [TWEAK 2] Realised return std from history ──────────────
    hist_closes = [float(d["close"]) for d in history]
    realised_returns = []
    horizon = len(forecast_list)
    for i in range(horizon, len(hist_closes)):
        r = (hist_closes[i] - hist_closes[i - horizon]) / (hist_closes[i - horizon] + 1e-5) * 100
        realised_returns.append(r)
    realised_std = float(np.std(realised_returns)) if len(realised_returns) >= 5 else 5.0
    normalised_return = m1_return_pct / (realised_std + 1e-5)

    # ── Weighted Score [-1, +1] ────────────────────────────────────────
    def _norm(val, lo, hi):
        """Linearly map val from [lo, hi] to [-1, +1], clamped."""
        return float(np.clip((val - lo) / ((hi - lo) / 2 + 1e-9) - 1, -1, 1))

    s1 = _norm(m1_return_pct,     -10,  10)   # endpoint direction  (30%)
    s2 = _norm(m2_split_pct,       -5,   5)   # momentum quality    (25%)
    s3 = _norm(m3_consistency_pct,  30,  70)  # day consistency     (20%)
    s4 = 1.0 if m4_breakout else -0.2         # breakout signal     (15%)
    s5 = _norm(-m5_drawdown_pct,   -8,   0)   # inverse of drawdown (10%)

    weighted_score = (0.30 * s1 + 0.25 * s2 + 0.20 * s3
                      + 0.15 * s4 + 0.10 * s5)

    # ── 5-Label Bias ───────────────────────────────────────────────────
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

    # ── [TWEAK 3] Dampened cv_score for flat forecasts ─────────────────
    atr_pct = compute_atr_pct(history)
    fc_mean = np.mean(forecast_closes)
    fc_std  = np.std(forecast_closes)
    cv      = fc_std / (fc_mean + 1e-5)
    forecast_range_pct = (max(forecast_closes) - min(forecast_closes)) / (current_close + 1e-5) * 100
    is_flat_forecast   = forecast_range_pct < atr_pct          # less than 1 ATR of movement
    cv_weight = 0.20 if is_flat_forecast else 0.40             # dampen cv on flat names

    cv_score   = float(np.clip(1.0 - cv * 10, 0, 1))
    
    if weighted_score > 0:
        cons_score = float(np.clip((m3_consistency_pct - 50) / 50, 0.0, 1.0))
    elif weighted_score < 0:
        cons_score = float(np.clip((50 - m3_consistency_pct) / 50, 0.0, 1.0))
    else:
        cons_score = 0.0
        
    mag_score  = abs(weighted_score)
    cons_weight = 0.50 if is_flat_forecast else 0.40
    mag_weight  = 0.30 if is_flat_forecast else 0.20
    ai_confidence_score = int(np.clip(
        (cv_weight * cv_score + cons_weight * cons_score + mag_weight * mag_score) * 100,
        25, 92
    ))

    forecast_metrics = {
        "return_pct":         round(m1_return_pct,    2),
        "momentum_split":     round(m2_split_pct,     2),
        "consistency_pct":    round(m3_consistency_pct, 1),
        "breakout_signal":    bool(m4_breakout),
        "max_drawdown_pct":   round(m5_drawdown_pct,  2),
        "weighted_score":     round(weighted_score,   3),
        "normalised_return":  round(normalised_return, 2),
        "realised_std_10d":   round(realised_std,      2),
        "forecast_range_pct": round(forecast_range_pct, 2),
        "is_flat_forecast":   bool(is_flat_forecast),
    }

    return ai_forecast_bias, ai_confidence_score, forecast_metrics
