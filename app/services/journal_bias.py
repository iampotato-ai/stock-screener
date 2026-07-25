"""
Trade Journal Bias Diagnostics.

Adapted from HKUDS/Vibe-Trading trade journal analysis tools (MIT License).
Source: https://github.com/HKUDS/Vibe-Trading

Diagnoses four common trading biases from closed trade history:

  1. Disposition Effect    — holding losers too long / cutting winners early
  2. Overtrading Score     — too many trades relative to a calibrated baseline
  3. Momentum Chasing      — entering after large recent moves (buying tops)
  4. Anchoring Bias        — using too-similar stop distances regardless of ATR

All functions are pure Python — no Flask/DB imports; testable in isolation.

Usage:
    from app.services.journal_bias import analyze_biases
    result = analyze_biases(closed_entries)
"""
from __future__ import annotations

import math
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Calibration constants ─────────────────────────────────────────────────────
OPTIMAL_TRADES_PER_MONTH = 6      # baseline for overtrading check
MOMENTUM_CHASE_THRESHOLD = 0.03   # 3% move in entry lookback = "chasing"
MIN_TRADES_FOR_ANALYSIS  = 5      # fewer than this → return meaningful error

# Severity thresholds
_SEVERITY = {
    'HIGH':     'HIGH',
    'MODERATE': 'MODERATE',
    'LOW':      'LOW',
}


def _severity(value: float, low: float, high: float) -> str:
    """Map a raw score to HIGH / MODERATE / LOW severity."""
    if value >= high:
        return _SEVERITY['HIGH']
    if value >= low:
        return _SEVERITY['MODERATE']
    return _SEVERITY['LOW']


def _safe_mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _safe_std(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = _safe_mean(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)


# ──────────────────────────────────────────────────────────────────────────────
# Bias 1 — Disposition Effect
# ──────────────────────────────────────────────────────────────────────────────

def compute_disposition_effect(entries: List[Dict[str, Any]]) -> Optional[float]:
    """
    Disposition Effect = avg_holding_days(winners) / avg_holding_days(losers).

    A value > 1.0 means winners are held longer than losers → correct behaviour.
    A value < 1.0 means losers are held longer → disposition bias present.
    None if insufficient data.

    Args:
        entries: List of closed trade dicts with 'pnl', 'date', 'exitDate' fields.

    Returns:
        Float ratio, or None if <2 trades in either category.
    """
    def _holding_days(e: Dict) -> Optional[float]:
        try:
            from datetime import datetime
            entry_d = datetime.strptime(str(e.get('date', '')),   '%Y-%m-%d')
            exit_d  = datetime.strptime(str(e.get('exitDate', '')), '%Y-%m-%d')
            return max(0.0, (exit_d - entry_d).days)
        except Exception:
            return None

    winners = [e for e in entries if (e.get('pnl') or 0) > 0]
    losers  = [e for e in entries if (e.get('pnl') or 0) < 0]

    winner_days = [d for e in winners if (d := _holding_days(e)) is not None]
    loser_days  = [d for e in losers  if (d := _holding_days(e)) is not None]

    if not winner_days or not loser_days:
        return None

    avg_winner = _safe_mean(winner_days)
    avg_loser  = _safe_mean(loser_days)

    if avg_loser <= 0:
        return None

    return round(avg_winner / avg_loser, 3)


# ──────────────────────────────────────────────────────────────────────────────
# Bias 2 — Overtrading Score
# ──────────────────────────────────────────────────────────────────────────────

def compute_overtrading_score(entries: List[Dict[str, Any]]) -> float:
    """
    Overtrading Score = (actual trades/month) / OPTIMAL_TRADES_PER_MONTH.

    >1.5 = overtrading; <0.5 = undertrading.

    Args:
        entries: List of trade dicts with 'date' field (any status).

    Returns:
        Float ratio (≥0).
    """
    if not entries:
        return 0.0

    dates = []
    for e in entries:
        try:
            from datetime import datetime
            dates.append(datetime.strptime(str(e.get('date', '')), '%Y-%m-%d'))
        except Exception:
            continue

    if len(dates) < 2:
        return 0.0

    dates.sort()
    span_days   = max(1, (dates[-1] - dates[0]).days)
    span_months = span_days / 30.0
    actual_per_month = len(dates) / span_months

    return round(actual_per_month / OPTIMAL_TRADES_PER_MONTH, 3)


# ──────────────────────────────────────────────────────────────────────────────
# Bias 3 — Momentum Chasing
# ──────────────────────────────────────────────────────────────────────────────

def compute_momentum_chasing(entries: List[Dict[str, Any]]) -> float:
    """
    Momentum Chasing = fraction of trades entered after a large recent move.

    Uses (entry - stop) / entry as a crude proxy for the move-before-entry.
    A wide risk vs stop (>3%) suggests the stock had already moved substantially.

    Args:
        entries: List of trade dicts with 'entry' and 'stop' fields.

    Returns:
        Float in [0, 1] — fraction of trades that were likely chasing.
    """
    if not entries:
        return 0.0

    chasing = 0
    valid   = 0
    for e in entries:
        entry = float(e.get('entry') or 0)
        stop  = float(e.get('stop')  or 0)
        if entry <= 0:
            continue
        valid += 1
        gap_pct = (entry - stop) / entry if entry > stop else 0.0
        if gap_pct > MOMENTUM_CHASE_THRESHOLD:
            chasing += 1

    return round(chasing / valid, 3) if valid else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Bias 4 — Anchoring Bias
# ──────────────────────────────────────────────────────────────────────────────

def compute_anchoring_bias(entries: List[Dict[str, Any]]) -> float:
    """
    Anchoring Bias = coefficient of variation (CV) of stop distances.

    Low CV → trader always uses same stop distance regardless of volatility.
    High CV → properly adapts stops to each stock's characteristics.

    Returns CV (std/mean of stop_pct_distances). Low (<0.2) = anchored.

    Args:
        entries: List of trade dicts with 'entry' and 'stop' fields.

    Returns:
        Float CV ≥ 0. Lower values indicate higher anchoring.
    """
    stop_pcts: List[float] = []
    for e in entries:
        entry = float(e.get('entry') or 0)
        stop  = float(e.get('stop')  or 0)
        if entry > 0 and stop > 0 and entry > stop:
            stop_pcts.append((entry - stop) / entry)

    if len(stop_pcts) < 2:
        return 0.0

    mean = _safe_mean(stop_pcts)
    if mean <= 0:
        return 0.0

    return round(_safe_std(stop_pcts) / mean, 3)


# ──────────────────────────────────────────────────────────────────────────────
# Composite analyzer
# ──────────────────────────────────────────────────────────────────────────────

def _recommendation_for_bias(bias: str, severity: str, value: float) -> Optional[str]:
    """Return a plain-English recommendation for a specific bias + severity."""
    recs = {
        ('disposition_effect', 'HIGH'): (
            "Your winners are held much longer than losers. "
            "Set a hard rule: if a position drops to break-even, exit immediately."
        ),
        ('disposition_effect', 'MODERATE'): (
            "Some tendency to cut winners early. Consider trailing stop-losses "
            "to let momentum run."
        ),
        ('overtrading_score', 'HIGH'): (
            f"You trade {value:.1f}x your optimal cadence. "
            "Raise your setup quality bar — only take A+ setups."
        ),
        ('overtrading_score', 'MODERATE'): (
            "Slightly elevated trading frequency. Keep a 'no-trade' day log."
        ),
        ('momentum_chasing', 'HIGH'): (
            "Over half your trades were entered after big moves. "
            "Add a rule: only enter if close is within 5% of the base."
        ),
        ('momentum_chasing', 'MODERATE'): (
            "Some chasing detected. Use a limit order at the break-even level "
            "rather than market orders."
        ),
        ('anchoring_bias', 'HIGH'): (
            "Your stops cluster at the same distance regardless of stock volatility. "
            "Size stops to 1.5× ATR(14) per trade."
        ),
        ('anchoring_bias', 'MODERATE'): (
            "Moderate anchoring on stops. Try varying them by sector volatility."
        ),
    }
    return recs.get((bias, severity))


def analyze_biases(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run all four bias diagnostics on a list of trade journal entries.

    Args:
        entries: List of TradeJournal.to_dict() results (any status).
                 Closed trades (with exitDate, pnl) are used for disposition/holding.
                 All trades are used for overtrading and momentum chasing.

    Returns:
        {
            'total_trades_analyzed': int,
            'closed_trades': int,
            'bias_scores': {
                'disposition_effect':         float | None,
                'disposition_severity':        str,
                'overtrading_score':           float,
                'overtrading_severity':        str,
                'momentum_chasing':            float,
                'momentum_chasing_severity':   str,
                'anchoring_bias':              float,
                'anchoring_severity':          str,
            },
            'recommendations': [str],
            'summary': str,
        }
    """
    if len(entries) < MIN_TRADES_FOR_ANALYSIS:
        return {
            'total_trades_analyzed': len(entries),
            'closed_trades': 0,
            'message': f'Need at least {MIN_TRADES_FOR_ANALYSIS} trades for bias analysis.',
            'bias_scores': {},
            'recommendations': [],
            'summary': '',
        }

    closed = [e for e in entries if str(e.get('status', '')).lower() == 'closed']

    # ── Compute biases ────────────────────────────────────────────────────────
    disp = compute_disposition_effect(closed)
    over = compute_overtrading_score(entries)
    chase = compute_momentum_chasing(entries)
    anch  = compute_anchoring_bias(entries)

    # ── Severity mapping ──────────────────────────────────────────────────────
    # Disposition: >2.0 = HIGH bias (holding losers 2× longer than winners)
    #              Note: ratio < 1.0 is the problematic direction (cut winners)
    #              So we invert: LOW disposition score = HIGH severity
    if disp is None:
        disp_sev = 'LOW'
    elif disp < 0.7:
        disp_sev = 'HIGH'
    elif disp < 1.0:
        disp_sev = 'MODERATE'
    else:
        disp_sev = 'LOW'       # >1.0 = healthy (hold winners longer)

    over_sev  = _severity(over,  low=1.0, high=1.5)
    chase_sev = _severity(chase, low=0.3, high=0.5)
    anch_sev  = _severity(1.0 - anch if anch >= 0 else 0, low=0.5, high=0.8)
    # anchoring: LOW cv = HIGH severity; invert for _severity call

    # Re-compute anchoring severity cleanly
    if anch < 0.15:
        anch_sev = 'HIGH'
    elif anch < 0.30:
        anch_sev = 'MODERATE'
    else:
        anch_sev = 'LOW'

    # ── Recommendations ───────────────────────────────────────────────────────
    recs: List[str] = []
    for (bias_name, sev, val) in [
        ('disposition_effect', disp_sev, disp or 0.0),
        ('overtrading_score',  over_sev, over),
        ('momentum_chasing',   chase_sev, chase),
        ('anchoring_bias',     anch_sev, anch),
    ]:
        if sev in ('HIGH', 'MODERATE'):
            rec = _recommendation_for_bias(bias_name, sev, val)
            if rec:
                recs.append(rec)

    # ── Summary sentence ──────────────────────────────────────────────────────
    high_biases = [
        b for b, s in [
            ('disposition effect', disp_sev),
            ('overtrading',        over_sev),
            ('momentum chasing',   chase_sev),
            ('anchoring',          anch_sev),
        ] if s == 'HIGH'
    ]
    if high_biases:
        summary = (
            f"Your biggest edge leaks: {', '.join(high_biases)}. "
            "Address these first for the highest performance uplift."
        )
    else:
        summary = (
            "No severe biases detected. Continue monitoring for emerging patterns."
        )

    return {
        'total_trades_analyzed': len(entries),
        'closed_trades': len(closed),
        'bias_scores': {
            'disposition_effect':         disp,
            'disposition_severity':        disp_sev,
            'overtrading_score':           over,
            'overtrading_severity':        over_sev,
            'momentum_chasing':            chase,
            'momentum_chasing_severity':   chase_sev,
            'anchoring_bias':              anch,
            'anchoring_severity':          anch_sev,
        },
        'recommendations': recs,
        'summary': summary,
    }
