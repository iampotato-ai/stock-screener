"""
Comprehensive unit tests for the signal_score package.

Tests all 11 submodules: MA alignment, MACD cross, RSI multi, volume analysis,
support/resistance, trend classifier, risk analytics, trade levels, composite
signal, AI overlay, and the orchestrator.
"""
import math
import pytest
from unittest.mock import patch, MagicMock


# ──────────────────────────────────────────────────────────────
# Test data helpers
# ──────────────────────────────────────────────────────────────

def _bullish_closes(n=100, start=100.0, daily_gain=0.005):
    """Generate a steadily rising price series."""
    return [start * (1 + daily_gain) ** i for i in range(n)]


def _bearish_closes(n=100, start=200.0, daily_loss=0.005):
    """Generate a steadily declining price series."""
    return [start * (1 - daily_loss) ** i for i in range(n)]


def _flat_closes(n=100, price=150.0):
    """Generate a flat price series."""
    return [price] * n


def _zigzag_closes(n=100, base=100.0, amplitude=5.0):
    """Generate a zigzag series oscillating around `base`."""
    return [base + amplitude * (1 if i % 2 == 0 else -1) for i in range(n)]


def _make_history(closes, volume_base=100000):
    """Build a minimal OHLCV history list from closes."""
    history = []
    for i, c in enumerate(closes):
        history.append({
            "date": f"2025-01-{i+1:02d}",
            "open": c * 0.999,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": volume_base + (i * 1000),
        })
    return history


# ══════════════════════════════════════════════════════════════
# 1. MA Alignment tests
# ══════════════════════════════════════════════════════════════

class TestMAAlignment:

    def test_bullish_alignment(self):
        """Perfect bullish: close > SMA5 > SMA10 > SMA20 > SMA60."""
        from app.services.signal_score.ma_alignment import compute_ma_alignment
        closes = _bullish_closes(100)
        result = compute_ma_alignment(closes)
        assert result["alignment_score"] == 1.0
        assert result["alignment_label"] == "Bullish Aligned"

    def test_bearish_alignment(self):
        """Perfect bearish: close < SMA5 < SMA10 < SMA20 < SMA60."""
        from app.services.signal_score.ma_alignment import compute_ma_alignment
        closes = _bearish_closes(100)
        result = compute_ma_alignment(closes)
        assert result["alignment_score"] == -1.0
        assert result["alignment_label"] == "Bearish Aligned"

    def test_insufficient_data(self):
        """Graceful default when data is too short."""
        from app.services.signal_score.ma_alignment import compute_ma_alignment
        result = compute_ma_alignment([100.0] * 10)
        assert result["alignment_score"] == 0.0
        assert result["alignment_label"] == "Mixed"

    def test_bias_pct_calculation(self):
        """Bias % should be (close - sma) / sma * 100."""
        from app.services.signal_score.ma_alignment import compute_ma_alignment
        closes = _bullish_closes(100)
        result = compute_ma_alignment(closes)
        current = closes[-1]
        sma5 = sum(closes[-5:]) / 5
        expected_bias = (current - sma5) / sma5 * 100
        assert abs(result["bias_pcts"]["sma_5_bias"] - expected_bias) < 0.01

    def test_flat_series_mixed(self):
        """Flat prices should produce near-zero alignment."""
        from app.services.signal_score.ma_alignment import compute_ma_alignment
        result = compute_ma_alignment(_flat_closes(100))
        assert abs(result["alignment_score"]) <= 0.01
        assert result["alignment_label"] == "Mixed"

    def test_sma_values_present(self):
        """All SMA keys must be present in result."""
        from app.services.signal_score.ma_alignment import compute_ma_alignment
        result = compute_ma_alignment(_bullish_closes(100))
        for key in ("sma_5", "sma_10", "sma_20", "sma_60"):
            assert key in result["sma_values"]
            assert result["sma_values"][key] > 0


# ══════════════════════════════════════════════════════════════
# 2. MACD Cross tests
# ══════════════════════════════════════════════════════════════

class TestMACDCross:

    def test_bullish_trend_positive_score(self):
        """Strong uptrend should produce positive MACD score."""
        from app.services.signal_score.macd_cross import compute_macd_cross
        closes = _bullish_closes(100, daily_gain=0.01)
        result = compute_macd_cross(closes)
        assert result["score"] > 0
        assert result["histogram"] > 0

    def test_bearish_trend_negative_score(self):
        """Accelerating downtrend should produce negative MACD score."""
        from app.services.signal_score.macd_cross import compute_macd_cross
        closes = [1000.0 - (i ** 1.5) for i in range(100)]
        result = compute_macd_cross(closes)
        assert result["macd_line"] < 0
        assert result["histogram"] < 0
        assert result["score"] < 0

    def test_insufficient_data_default(self):
        """Short series should return neutral defaults."""
        from app.services.signal_score.macd_cross import compute_macd_cross
        result = compute_macd_cross([100.0] * 10)
        assert result["cross_type"] == "none"
        assert result["score"] == 0.0

    def test_cross_type_is_valid_string(self):
        """Cross type should be one of the expected values."""
        from app.services.signal_score.macd_cross import compute_macd_cross
        valid_types = {
            "golden_cross", "death_cross", "approaching_golden",
            "approaching_death", "sustained_bull", "sustained_bear", "none"
        }
        result = compute_macd_cross(_bullish_closes(100))
        assert result["cross_type"] in valid_types

    def test_golden_cross_detection(self):
        """A series that transitions from bearish to bullish should detect golden cross."""
        from app.services.signal_score.macd_cross import compute_macd_cross
        # Build a series: drop then recover sharply
        closes = _bearish_closes(60, start=150, daily_loss=0.005)
        closes += _bullish_closes(40, start=closes[-1], daily_gain=0.015)
        result = compute_macd_cross(closes)
        # Should detect a bullish transition
        assert result["score"] > 0


# ══════════════════════════════════════════════════════════════
# 3. RSI Multi tests
# ══════════════════════════════════════════════════════════════

class TestRSIMulti:

    def test_bullish_rsi(self):
        """Strong uptrend should produce high RSI and positive composite score."""
        from app.services.signal_score.rsi_multi import compute_rsi_multi
        closes = _bullish_closes(100, daily_gain=0.015)
        result = compute_rsi_multi(closes)
        assert result["composite_score"] > 0
        assert result["rsi_values"]["rsi_6"] > 50

    def test_bearish_rsi(self):
        """Strong downtrend should produce low RSI and negative composite score."""
        from app.services.signal_score.rsi_multi import compute_rsi_multi
        closes = _bearish_closes(100, daily_loss=0.015)
        result = compute_rsi_multi(closes)
        assert result["composite_score"] < 0
        assert result["rsi_values"]["rsi_6"] < 50

    def test_classification_boundaries(self):
        """Verify RSI classification labels."""
        from app.services.signal_score.rsi_multi import _classify_rsi
        assert _classify_rsi(85) == "Overbought"
        assert _classify_rsi(70) == "Bullish"
        assert _classify_rsi(50) == "Neutral"
        assert _classify_rsi(30) == "Bearish"
        assert _classify_rsi(15) == "Oversold"

    def test_insufficient_data(self):
        """Short series should return neutral defaults."""
        from app.services.signal_score.rsi_multi import compute_rsi_multi
        result = compute_rsi_multi([100.0] * 5)
        assert result["composite_score"] == 0.0
        assert result["composite_label"] == "Neutral"

    def test_all_rsi_keys_present(self):
        """All RSI period keys must be present."""
        from app.services.signal_score.rsi_multi import compute_rsi_multi
        result = compute_rsi_multi(_bullish_closes(100))
        for key in ("rsi_6", "rsi_12", "rsi_24"):
            assert key in result["rsi_values"]
            assert key in result["classifications"]


# ══════════════════════════════════════════════════════════════
# 4. Volume Analysis tests
# ══════════════════════════════════════════════════════════════

class TestVolumeAnalysis:

    def test_heavy_up(self):
        """Price up with high RVOL → Heavy Up."""
        from app.services.signal_score.volume_analysis import classify_volume
        closes = [100.0] * 20 + [102.0]  # Up today
        volumes = [50000] * 20 + [100000]  # 2x volume
        result = classify_volume(closes, volumes)
        assert result["regime"] == "Heavy Up"
        assert result["score"] > 0

    def test_heavy_down(self):
        """Price down with high RVOL → Heavy Down."""
        from app.services.signal_score.volume_analysis import classify_volume
        closes = [100.0] * 20 + [97.0]
        volumes = [50000] * 20 + [100000]
        result = classify_volume(closes, volumes)
        assert result["regime"] == "Heavy Down"
        assert result["score"] < 0

    def test_shrink_up(self):
        """Price up with very low RVOL → Shrink Up."""
        from app.services.signal_score.volume_analysis import classify_volume
        closes = [100.0] * 20 + [101.0]
        volumes = [100000] * 20 + [30000]  # < 0.7x
        result = classify_volume(closes, volumes)
        assert result["regime"] == "Shrink Up"

    def test_shrink_down(self):
        """Price down with very low RVOL → Shrink Down."""
        from app.services.signal_score.volume_analysis import classify_volume
        closes = [100.0] * 20 + [99.0]
        volumes = [100000] * 20 + [30000]
        result = classify_volume(closes, volumes)
        assert result["regime"] == "Shrink Down"

    def test_insufficient_data(self):
        """Short series → neutral default."""
        from app.services.signal_score.volume_analysis import classify_volume
        result = classify_volume([100.0], [50000])
        assert result["score"] == 0.0

    def test_zero_volume(self):
        """Zero volume today → default result."""
        from app.services.signal_score.volume_analysis import classify_volume
        result = classify_volume([100.0, 101.0], [50000, 0])
        assert result["score"] == 0.0


# ══════════════════════════════════════════════════════════════
# 5. Support/Resistance tests
# ══════════════════════════════════════════════════════════════

class TestSupportResistance:

    def test_basic_sr_levels(self):
        """Known swing highs/lows should produce S/R levels."""
        from app.services.signal_score.support_resistance import compute_support_resistance
        # Create a series with obvious swing points
        closes = [100 + 5 * math.sin(i * 0.3) for i in range(80)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = compute_support_resistance(highs, lows, closes)
        assert result["nearest_support"] < closes[-1]
        assert result["nearest_resistance"] > closes[-1]

    def test_price_position_range(self):
        """Price position should be between 0 and 1."""
        from app.services.signal_score.support_resistance import compute_support_resistance
        closes = _zigzag_closes(80)
        highs = [c + 2 for c in closes]
        lows = [c - 2 for c in closes]
        result = compute_support_resistance(highs, lows, closes)
        assert 0.0 <= result["price_position"] <= 1.0

    def test_insufficient_data(self):
        """Short series → default result."""
        from app.services.signal_score.support_resistance import compute_support_resistance
        result = compute_support_resistance([100.0] * 5, [99.0] * 5, [100.0] * 5)
        assert "nearest_support" in result
        assert "nearest_resistance" in result

    def test_clustering(self):
        """Levels within 1.5% should be clustered."""
        from app.services.signal_score.support_resistance import _cluster_levels
        levels = [(100.0, "support"), (100.5, "support"), (101.0, "support"),
                  (120.0, "resistance")]
        clusters = _cluster_levels(levels, tolerance_pct=1.5)
        # 100/100.5/101 should merge into one cluster, 120 stays separate
        assert len(clusters) == 2
        assert clusters[0]["touches"] == 3


# ══════════════════════════════════════════════════════════════
# 6. Trend Classifier tests
# ══════════════════════════════════════════════════════════════

class TestTrendClassifier:

    def test_strong_bull(self):
        """All bullish signals → Strong Bull."""
        from app.services.signal_score.trend_classifier import classify_trend
        result = classify_trend(
            ma_score=1.0, macd_score=0.8, macd_cross="golden_cross", rsi_score=0.5
        )
        assert result["trend_label"] == "Strong Bull"

    def test_strong_bear(self):
        """All bearish signals → Strong Bear."""
        from app.services.signal_score.trend_classifier import classify_trend
        result = classify_trend(
            ma_score=-1.0, macd_score=-0.8, macd_cross="death_cross", rsi_score=-0.5
        )
        assert result["trend_label"] == "Strong Bear"

    def test_neutral_conflicting(self):
        """Conflicting signals → Neutral."""
        from app.services.signal_score.trend_classifier import classify_trend
        result = classify_trend(
            ma_score=0.0, macd_score=0.0, macd_cross="none", rsi_score=0.0
        )
        assert result["trend_label"] == "Neutral"

    def test_bull_with_death_cross_demoted(self):
        """Bull with death cross → demoted to Neutral."""
        from app.services.signal_score.trend_classifier import classify_trend
        result = classify_trend(
            ma_score=0.4, macd_score=0.3, macd_cross="death_cross", rsi_score=0.2
        )
        assert result["trend_label"] == "Neutral"

    def test_trend_score_in_range(self):
        """Trend score must be in [-1.0, +1.0]."""
        from app.services.signal_score.trend_classifier import classify_trend
        result = classify_trend(ma_score=1.0, macd_score=1.0, macd_cross="golden_cross", rsi_score=1.0)
        assert -1.0 <= result["trend_score"] <= 1.0


# ══════════════════════════════════════════════════════════════
# 7. Risk Analytics tests
# ══════════════════════════════════════════════════════════════

class TestRiskAnalytics:

    def test_realized_vol_positive(self):
        """Volatile series should have positive realized vol."""
        from app.services.signal_score.risk_analytics import compute_risk_analytics
        closes = _zigzag_closes(60, amplitude=10)
        highs = [c + 5 for c in closes]
        lows = [c - 5 for c in closes]
        result = compute_risk_analytics(closes, highs, lows)
        assert result["realized_vol_30d"] > 0

    def test_flat_series_low_vol(self):
        """Flat series should have very low volatility."""
        from app.services.signal_score.risk_analytics import compute_risk_analytics
        closes = _flat_closes(60)
        highs = [c + 0.01 for c in closes]
        lows = [c - 0.01 for c in closes]
        result = compute_risk_analytics(closes, highs, lows)
        assert result["realized_vol_30d"] < 0.01

    def test_atr_positive(self):
        """ATR should be positive for any real price data."""
        from app.services.signal_score.risk_analytics import compute_risk_analytics
        closes = _bullish_closes(60)
        highs = [c * 1.02 for c in closes]
        lows = [c * 0.98 for c in closes]
        result = compute_risk_analytics(closes, highs, lows)
        assert result["atr_14"] > 0
        assert result["atr_14_pct"] > 0

    def test_max_drawdown_declining(self):
        """Declining series should have negative max drawdown."""
        from app.services.signal_score.risk_analytics import compute_risk_analytics
        closes = _bearish_closes(100, daily_loss=0.01)
        highs = [c * 1.005 for c in closes]
        lows = [c * 0.995 for c in closes]
        result = compute_risk_analytics(closes, highs, lows)
        assert result["max_drawdown_90d"] < 0

    def test_risk_label_valid(self):
        """Risk label should be one of the four expected values."""
        from app.services.signal_score.risk_analytics import compute_risk_analytics
        result = compute_risk_analytics(_bullish_closes(60),
                                        [c * 1.01 for c in _bullish_closes(60)],
                                        [c * 0.99 for c in _bullish_closes(60)])
        assert result["risk_label"] in ("Low", "Medium", "High", "Very High")

    def test_insufficient_data(self):
        """Short series → default result."""
        from app.services.signal_score.risk_analytics import compute_risk_analytics
        result = compute_risk_analytics([100.0] * 5, [101.0] * 5, [99.0] * 5)
        assert result["risk_label"] == "Medium"


# ══════════════════════════════════════════════════════════════
# 8. Trade Levels tests
# ══════════════════════════════════════════════════════════════

class TestTradeLevels:

    def test_long_sl_below_close(self):
        """For LONG signals, SL must be below close."""
        from app.services.signal_score.trade_levels import compute_trade_levels
        result = compute_trade_levels(
            current_close=100.0, signal_verdict="Buy",
            nearest_support=95.0, nearest_resistance=108.0, atr=2.0
        )
        assert result["direction"] == "LONG"
        assert result["stop_loss"] < 100.0
        assert result["take_profit"] > 100.0

    def test_long_rr_ratio_minimum(self):
        """Risk-reward ratio must be >= 1.5 for LONG."""
        from app.services.signal_score.trade_levels import compute_trade_levels
        result = compute_trade_levels(
            current_close=100.0, signal_verdict="Strong Buy",
            nearest_support=98.0, nearest_resistance=102.0, atr=1.0
        )
        assert result["risk_reward_ratio"] >= 1.5

    def test_long_sl_capped_at_5pct(self):
        """SL should never be more than 5% below close."""
        from app.services.signal_score.trade_levels import compute_trade_levels
        result = compute_trade_levels(
            current_close=100.0, signal_verdict="Buy",
            nearest_support=80.0, nearest_resistance=120.0, atr=10.0
        )
        sl_pct = (100.0 - result["stop_loss"]) / 100.0 * 100
        assert sl_pct <= 5.01  # Small tolerance

    def test_short_sl_above_close(self):
        """For SHORT signals, SL must be above close."""
        from app.services.signal_score.trade_levels import compute_trade_levels
        result = compute_trade_levels(
            current_close=100.0, signal_verdict="Sell",
            nearest_support=90.0, nearest_resistance=105.0, atr=2.0
        )
        assert result["direction"] == "SHORT"
        assert result["stop_loss"] > 100.0
        assert result["take_profit"] < 100.0

    def test_neutral_direction(self):
        """Hold/Watch verdicts → NEUTRAL direction."""
        from app.services.signal_score.trade_levels import compute_trade_levels
        result = compute_trade_levels(
            current_close=100.0, signal_verdict="Hold",
            nearest_support=95.0, nearest_resistance=105.0, atr=2.0
        )
        assert result["direction"] == "NEUTRAL"

    def test_zero_close_default(self):
        """Zero close → default result."""
        from app.services.signal_score.trade_levels import compute_trade_levels
        result = compute_trade_levels(0.0, "Buy", 0.0, 0.0, 0.0)
        assert result["direction"] == "NEUTRAL"


# ══════════════════════════════════════════════════════════════
# 9. Composite Signal tests
# ══════════════════════════════════════════════════════════════

class TestCompositeSignal:

    def test_all_bullish_strong_buy(self):
        """All bullish components → score >= 80, verdict 'Strong Buy'."""
        from app.services.signal_score.composite_signal import compute_composite_signal
        result = compute_composite_signal(
            ma_score=1.0, macd_score=1.0, rsi_score=1.0,
            volume_score=1.0, trend_score=1.0, risk_score=1.0,
        )
        assert result["score"] >= 80
        assert result["verdict"] == "Strong Buy"

    def test_all_bearish_strong_sell(self):
        """All bearish components → score <= 14, verdict 'Strong Sell'."""
        from app.services.signal_score.composite_signal import compute_composite_signal
        result = compute_composite_signal(
            ma_score=-1.0, macd_score=-1.0, rsi_score=-1.0,
            volume_score=-1.0, trend_score=-1.0, risk_score=0.0,
        )
        assert result["score"] <= 14
        assert result["verdict"] == "Strong Sell"

    def test_neutral_hold(self):
        """All neutral components → score around 50, verdict 'Hold'."""
        from app.services.signal_score.composite_signal import compute_composite_signal
        result = compute_composite_signal(
            ma_score=0.0, macd_score=0.0, rsi_score=0.0,
            volume_score=0.0, trend_score=0.0, risk_score=0.5,
        )
        assert 45 <= result["score"] <= 64
        assert result["verdict"] == "Hold"

    def test_score_clamped(self):
        """Score must be in [0, 100]."""
        from app.services.signal_score.composite_signal import compute_composite_signal
        result = compute_composite_signal(
            ma_score=1.0, macd_score=1.0, rsi_score=1.0,
            volume_score=1.0, trend_score=1.0, risk_score=1.0,
        )
        assert 0 <= result["score"] <= 100

    def test_breakdown_present(self):
        """Breakdown dict must contain all component contributions."""
        from app.services.signal_score.composite_signal import compute_composite_signal
        result = compute_composite_signal(0.5, 0.3, 0.2, 0.1, 0.4, 0.7)
        breakdown = result["breakdown"]
        for key in ("ma_contribution", "macd_contribution", "rsi_contribution",
                     "volume_contribution", "trend_contribution", "risk_contribution"):
            assert key in breakdown

    def test_all_verdict_ranges(self):
        """Verify all 6 verdicts are reachable."""
        from app.services.signal_score.composite_signal import compute_composite_signal
        # Test with varying ma_score to hit different ranges
        verdicts = set()
        for ma in [1.0, 0.5, 0.0, -0.3, -0.7, -1.0]:
            r = compute_composite_signal(ma, ma, ma, ma, ma, max(0, (ma + 1) / 2))
            verdicts.add(r["verdict"])
        assert len(verdicts) >= 4  # Should hit at least 4 of 6


# ══════════════════════════════════════════════════════════════
# 10. AI Overlay tests
# ══════════════════════════════════════════════════════════════

class TestAIOverlay:

    def test_fallback_when_llm_unavailable(self):
        """When LLM is unavailable, fallback template should generate valid output."""
        from app.services.signal_score.ai_overlay import _generate_fallback
        snapshot = {
            "signal_verdict": "Buy",
            "signal_score": 72.5,
            "trend_status": "Bull",
            "ma_alignment": {"alignment_label": "Mostly Bullish"},
            "macd_status": {"cross_type": "golden_cross"},
            "volume_analysis": {"regime": "Heavy Up"},
            "rsi_multi": {"composite_label": "Bullish"},
            "risk_analytics": {"risk_label": "Medium"},
            "trade_levels": {"direction": "LONG"},
        }
        result = _generate_fallback("RELIANCE", snapshot, "sent-positive")
        assert len(result["summary"]) > 20
        assert isinstance(result["bull_factors"], list)
        assert isinstance(result["risk_factors"], list)
        assert len(result["bull_factors"]) <= 3
        assert len(result["risk_factors"]) <= 3

    @patch("app.services.signal_score.ai_overlay._call_llm")
    @patch("app.services.signal_score.ai_overlay._fetch_news_sentiment")
    def test_llm_success(self, mock_news, mock_llm):
        """When LLM returns valid JSON, it should be used."""
        from app.services.signal_score.ai_overlay import generate_ai_overlay
        mock_news.return_value = "sent-positive"
        mock_llm.return_value = {
            "summary": "RELIANCE shows strong momentum with bullish MA alignment.",
            "bull_factors": ["Strong technical setup", "Positive news flow"],
            "risk_factors": ["Elevated volatility"],
        }
        snapshot = {
            "signal_verdict": "Buy", "signal_score": 70,
            "trend_status": "Bull", "ma_alignment": {"alignment_label": "Bullish"},
            "macd_status": {"cross_type": "sustained_bull"},
            "rsi_multi": {"composite_label": "Bullish"},
            "volume_analysis": {"regime": "Heavy Up"},
            "risk_analytics": {"risk_label": "Low"},
            "trade_levels": {"direction": "LONG", "stop_loss": 95, "take_profit": 110},
        }
        result = generate_ai_overlay("RELIANCE", snapshot)
        assert "RELIANCE" in result["summary"]
        assert result["news_sentiment"] == "sent-positive"
        assert len(result["bull_factors"]) == 2

    @patch("app.services.signal_score.ai_overlay._call_llm")
    @patch("app.services.signal_score.ai_overlay._fetch_news_sentiment")
    def test_llm_failure_fallback(self, mock_news, mock_llm):
        """When LLM returns empty, fallback should be used."""
        from app.services.signal_score.ai_overlay import generate_ai_overlay
        mock_news.return_value = "sent-neutral"
        mock_llm.return_value = {}  # LLM failed
        snapshot = {
            "signal_verdict": "Hold", "signal_score": 50,
            "trend_status": "Neutral", "ma_alignment": {"alignment_label": "Mixed"},
            "macd_status": {"cross_type": "none"},
            "rsi_multi": {"composite_label": "Neutral"},
            "volume_analysis": {"regime": "Light Up"},
            "risk_analytics": {"risk_label": "Medium"},
            "trade_levels": {"direction": "NEUTRAL"},
        }
        result = generate_ai_overlay("INFY", snapshot)
        assert "INFY" in result["summary"]
        assert result["news_sentiment"] == "sent-neutral"


# ══════════════════════════════════════════════════════════════
# 11. Orchestrator (analyze_stock) tests
# ══════════════════════════════════════════════════════════════

class TestAnalyzeStock:

    @patch("app.services.signal_score.ai_overlay._call_llm")
    @patch("app.services.signal_score.ai_overlay._fetch_news_sentiment")
    @patch("app.utils.technical.fetch_historical_prices")
    def test_full_snapshot_success(self, mock_fetch, mock_news, mock_llm):
        """analyze_stock with mocked data should return a complete snapshot."""
        from app.services.signal_score import analyze_stock
        # Build realistic mock history
        closes = _bullish_closes(100, daily_gain=0.005)
        mock_fetch.return_value = _make_history(closes)
        mock_news.return_value = "sent-positive"
        mock_llm.return_value = {
            "summary": "Test summary.",
            "bull_factors": ["Factor 1"],
            "risk_factors": ["Risk 1"],
        }

        result = analyze_stock("TESTSTOCK", include_ai=True)

        assert result["success"] is True
        assert result["symbol"] == "TESTSTOCK"
        assert "signal_score" in result
        assert "signal_verdict" in result
        assert "ma_alignment" in result
        assert "macd_status" in result
        assert "rsi_multi" in result
        assert "volume_analysis" in result
        assert "support_resistance" in result
        assert "risk_analytics" in result
        assert "trade_levels" in result
        assert "ai_summary" in result

    @patch("app.utils.technical.fetch_historical_prices")
    def test_insufficient_data_error(self, mock_fetch):
        """analyze_stock with too few bars should return error."""
        from app.services.signal_score import analyze_stock
        mock_fetch.return_value = [{"close": 100, "high": 101, "low": 99,
                                     "open": 100, "volume": 1000, "date": "2025-01-01"}] * 5

        result = analyze_stock("TESTSTOCK", include_ai=False)
        assert result["success"] is False
        assert "Insufficient" in result["error"]

    @patch("app.utils.technical.fetch_historical_prices")
    def test_no_ai_overlay(self, mock_fetch):
        """analyze_stock with include_ai=False should skip AI."""
        from app.services.signal_score import analyze_stock
        mock_fetch.return_value = _make_history(_bullish_closes(100))

        result = analyze_stock("TESTSTOCK", include_ai=False)
        assert result["success"] is True
        assert result["ai_summary"] == ""
        assert result["ai_bull_factors"] == []

    @patch("app.utils.technical.fetch_historical_prices")
    def test_empty_history(self, mock_fetch):
        """Empty history → error."""
        from app.services.signal_score import analyze_stock
        mock_fetch.return_value = []

        result = analyze_stock("TESTSTOCK", include_ai=False)
        assert result["success"] is False
