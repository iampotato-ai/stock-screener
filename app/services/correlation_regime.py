"""
Correlation Regime Detector for MomentumScan.

Adapted from HKUDS/Vibe-Trading correlation regime detection logic (MIT License).
Source: https://github.com/HKUDS/Vibe-Trading

Classifies the current market as one of:
  - FUSED    : High pairwise correlation (risk-off; alpha is low; signals unreliable)
  - NORMAL   : Moderate correlation (typical market)
  - DIVERGED : Low correlation (high dispersion; good environment for stock picking)

A 3-day hysteresis prevents rapid regime flickering.

Usage (in market_breadth_service.py or scheduler):
    from app.services.correlation_regime import CorrelationRegimeService
    svc = CorrelationRegimeService()
    regime, score = svc.compute_regime_from_db()
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Thresholds for regime classification
FUSED_THRESHOLD    = 0.65   # avg pairwise corr above this → FUSED
DIVERGED_THRESHOLD = 0.20   # avg pairwise corr below this → DIVERGED
HYSTERESIS_DAYS    = 3      # regime must persist N days to become active
MIN_SYMBOLS        = 10     # minimum symbols needed for a meaningful regime
MIN_BARS           = 10     # minimum bars per symbol for correlation
LOOKBACK_BARS      = 20     # rolling lookback window


# ──────────────────────────────────────────────────────────────────────────────
# Pure math (no Flask / SQLAlchemy imports; fully testable in isolation)
# ──────────────────────────────────────────────────────────────────────────────

def compute_daily_returns(closes: List[float]) -> List[float]:
    """Convert a list of close prices to 1-day percentage returns."""
    if len(closes) < 2:
        return []
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]


def _pearson_corr(x: List[float], y: List[float]) -> Optional[float]:
    """Pearson correlation coefficient between two equal-length lists."""
    n = len(x)
    if n < 2:
        return None

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov   = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / n
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x) / n)
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y) / n)

    if std_x < 1e-12 or std_y < 1e-12:
        return None  # constant series — skip

    return cov / (std_x * std_y)


def compute_avg_pairwise_correlation(returns_matrix: Dict[str, List[float]]) -> float:
    """
    Compute the mean pairwise Pearson correlation across all symbol pairs.

    Args:
        returns_matrix: {symbol: [daily_returns]} — same-length lists preferred;
                        shorter lists are trimmed to the minimum length.

    Returns:
        Mean correlation in [-1, 1], or 0.0 if fewer than 2 symbols available.
    """
    symbols = [s for s, v in returns_matrix.items() if len(v) >= 2]
    if len(symbols) < 2:
        return 0.0

    # Trim to common length
    min_len = min(len(returns_matrix[s]) for s in symbols)
    trimmed = {s: returns_matrix[s][-min_len:] for s in symbols}

    corrs: List[float] = []
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            c = _pearson_corr(trimmed[symbols[i]], trimmed[symbols[j]])
            if c is not None:
                corrs.append(c)

    return sum(corrs) / len(corrs) if corrs else 0.0


def classify_regime(avg_corr: float) -> str:
    """
    Map an average pairwise correlation value to a regime label.

    Args:
        avg_corr: Mean pairwise correlation in [-1, 1].

    Returns:
        'FUSED' | 'NORMAL' | 'DIVERGED'
    """
    if avg_corr >= FUSED_THRESHOLD:
        return 'FUSED'
    if avg_corr <= DIVERGED_THRESHOLD:
        return 'DIVERGED'
    return 'NORMAL'


def apply_hysteresis(
    new_regime: str,
    history: List[str],
    n_days: int = HYSTERESIS_DAYS
) -> str:
    """
    Apply N-day hysteresis filter.  A new regime only becomes active when it
    has been classified identically for the last n_days consecutive readings.

    Args:
        new_regime: The regime just computed.
        history:    List of past regime labels (most recent last).
        n_days:     Hysteresis window.

    Returns:
        The active (hysteresis-smoothed) regime label.
    """
    if len(history) < n_days - 1:
        return history[-1] if history else new_regime

    recent = history[-(n_days - 1):] + [new_regime]
    if len(set(recent)) == 1:
        return new_regime                # unanimous → switch
    return history[-1] if history else new_regime   # hold previous


# ──────────────────────────────────────────────────────────────────────────────
# Service class (Flask-aware; uses DailyBar for data)
# ──────────────────────────────────────────────────────────────────────────────

class CorrelationRegimeService:
    """
    Computes and caches the current market correlation regime.
    Designed as a lightweight singleton; call compute_regime_from_db()
    from the APScheduler breadth job.
    """

    def __init__(self):
        self._regime_history: List[str] = []   # sliding window of past labels

    def compute_regime_from_db(
        self,
        n_bars: int = LOOKBACK_BARS,
        min_symbols: int = MIN_SYMBOLS,
    ) -> Tuple[str, float]:
        """
        Load close-price history from DailyBar, compute pairwise correlations,
        and return the hysteresis-smoothed regime label.

        Returns:
            (regime_label, avg_pairwise_corr)
            regime_label: 'FUSED' | 'NORMAL' | 'DIVERGED'
            avg_pairwise_corr: float in [-1, 1]
        """
        try:
            returns_matrix = self._load_returns_from_db(n_bars)
        except Exception as err:
            logger.error("CorrelationRegimeService: DB load failed — %s", err)
            return 'NORMAL', 0.0

        if len(returns_matrix) < min_symbols:
            logger.info(
                "CorrelationRegimeService: only %d symbols — defaulting to NORMAL",
                len(returns_matrix)
            )
            return 'NORMAL', 0.0

        avg_corr   = compute_avg_pairwise_correlation(returns_matrix)
        raw_regime = classify_regime(avg_corr)
        regime     = apply_hysteresis(raw_regime, self._regime_history)

        # Update sliding window (keep last HYSTERESIS_DAYS labels)
        self._regime_history.append(raw_regime)
        self._regime_history = self._regime_history[-(HYSTERESIS_DAYS * 2):]

        logger.info(
            "CorrelationRegimeService: avg_corr=%.3f raw=%s active=%s",
            avg_corr, raw_regime, regime
        )
        return regime, round(avg_corr, 4)

    @staticmethod
    def _load_returns_from_db(n_bars: int) -> Dict[str, List[float]]:
        """
        Load close prices for all symbols from DailyBar and compute returns.
        Only includes symbols that have at least MIN_BARS bars.
        """
        from app.models import DailyBar
        from app.extensions import db

        # Fetch the most recent trading date
        latest_date = db.session.query(
            db.func.max(DailyBar.trade_date)
        ).scalar()

        if not latest_date:
            return {}

        # Load all bars from the rolling window
        all_bars = (
            db.session.query(DailyBar.symbol, DailyBar.trade_date, DailyBar.close)
            .filter(DailyBar.close.isnot(None))
            .filter(DailyBar.close > 0)
            .order_by(DailyBar.symbol, DailyBar.trade_date.asc())
            .all()
        )

        # Group by symbol
        by_symbol: Dict[str, List[float]] = {}
        for bar in all_bars:
            by_symbol.setdefault(bar.symbol, []).append(float(bar.close))

        # Trim to last n_bars and compute returns; drop symbols with too few bars
        returns_matrix: Dict[str, List[float]] = {}
        for sym, closes in by_symbol.items():
            recent_closes = closes[-n_bars:]
            if len(recent_closes) < MIN_BARS:
                continue
            rets = compute_daily_returns(recent_closes)
            if rets:
                returns_matrix[sym] = rets

        return returns_matrix


# Singleton instance — share across requests to preserve hysteresis state
correlation_regime_service = CorrelationRegimeService()
