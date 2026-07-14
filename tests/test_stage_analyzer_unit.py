import pytest
from app.services.stage_analyzer.stage_classifier import StageClassifier, classify_stock
from app.services.stage_analyzer.scoring import StageAnalyzer
from app.services.stage_analyzer.explanations import generate_stage_explanation, StageExplanationGenerator
from app.services.stage_analyzer.trend_template import render_trend, BASIC_SUMMARY, DETAILED_TEMPLATE
from app.services.stage_analyzer.engine import analyze, get_score, explain, render


def test_determine_stage_stage2():
    classifier = StageClassifier()
    # 60 days where last is > 10% higher than first (e.g., first=100, last=111.8)
    history = [{"close": 100.0 + i * 0.2} for i in range(60)]
    stock_data = {"ticker": "TEST_STAGE2", "history": history}
    assert classifier.determine_stage(stock_data) == "Stage 2"


def test_determine_stage_stage4():
    classifier = StageClassifier()
    # 60 days where last is < -5% lower than first (e.g., first=100, last=94.1)
    history = [{"close": 100.0 - i * 0.1} for i in range(60)]
    stock_data = {"ticker": "TEST_STAGE4", "history": history}
    assert classifier.determine_stage(stock_data) == "Stage 4"


def test_determine_stage_stage1():
    classifier = StageClassifier()
    # flat growth but current close is at the min close of the history (Stage 1 consolidation base)
    history = [{"close": 100.0} for _ in range(60)]
    history[-1] = {"close": 98.0} # slight drop to be at the min range
    stock_data = {"ticker": "TEST_STAGE1", "history": history}
    assert classifier.determine_stage(stock_data) == "Stage 1"


def test_determine_stage_stage3():
    classifier = StageClassifier()
    # flat growth but current close is at the max close of the history (Stage 3 topping/distribution)
    history = [{"close": 100.0} for _ in range(60)]
    history[-1] = {"close": 102.0} # slight rise to be at the max range
    stock_data = {"ticker": "TEST_STAGE3", "history": history}
    assert classifier.determine_stage(stock_data) == "Stage 3"


def test_determine_stage_insufficient_data():
    classifier = StageClassifier()
    # Less than 5 history entries
    stock_data_short = {"ticker": "SHORT", "history": [{"close": 100}, {"close": 101}]}
    assert classifier.determine_stage(stock_data_short) == "Unknown"

    # Missing history
    stock_data_missing = {"ticker": "MISSING"}
    assert classifier.determine_stage(stock_data_missing) == "Unknown"

    # History is not a list
    stock_data_invalid = {"ticker": "INVALID", "history": "not a list"}
    assert classifier.determine_stage(stock_data_invalid) == "Unknown"

    # Valid list length but closing prices extraction yields < 2 values
    stock_data_bad_entries = {"ticker": "BAD", "history": [{}, {}, {}, {}, {}]}
    assert classifier.determine_stage(stock_data_bad_entries) == "Unknown"


def test_classify_stock_convenience():
    # Test classifier integration via convenience function
    history = [{"close": 100 + i * 0.2} for i in range(60)]
    stock_data = {"ticker": "RELIANCE", "history": history, "SMA21": 110.0, "SMA50": 105.0}
    res = classify_stock(stock_data)
    assert res["stage"] == "Stage 2"
    assert res["score"] == 0
    assert res["max_score"] == 10
    assert res["details"]["ticker"] == "RELIANCE"
    assert res["details"]["SMA21"] == 110.0
    assert "stock_snapshot" not in res["details"]
    assert "history" not in res["details"]


def test_scoring_no_history_leak():
    analyzer = StageAnalyzer()
    stock_data = {
        "ticker": "INFY",
        "history": [{"close": 1500} for _ in range(60)],
        "SMA21": 1510.0,
        "SMA50": 1490.0
    }
    score = analyzer.analyze(stock_data, "Stage 1")
    assert score["stage"] == "Stage 1"
    assert score["score"] == 0
    assert score["max_score"] == 10
    assert score["details"]["ticker"] == "INFY"
    assert score["details"]["SMA21"] == 1510.0
    assert score["details"]["SMA50"] == 1490.0
    assert "stock_snapshot" not in score["details"]


def test_generate_explanation_happy_path():
    score_data = {
        "stage": "Stage 2",
        "score": 5,
        "max_score": 10,
        "details": {
            "ticker": "RELIANCE",
            "SMA21": 2500.0,
            "reason": "Strong upward trend",
            "valid_bool": True
        }
    }
    explanation = generate_stage_explanation(score_data)
    assert "Stage: Stage 2" in explanation
    assert "Score: 5/10" in explanation
    assert "- ticker: RELIANCE" in explanation
    assert "- SMA21: 2500.0" in explanation
    assert "- reason: Strong upward trend" in explanation
    assert "- valid_bool: True" in explanation


def test_generate_explanation_complex_details():
    score_data = {
        "stage": "early",
        "score": 5,
        "max_score": 10,
        "details": {
            "complex_list": [1, 2, 3]
        }
    }
    explanation = generate_stage_explanation(score_data)
    assert "- complex_list: [1, 2, 3]" in explanation


def test_generate_explanation_empty_details():
    score_data = {
        "stage": "Stage 1",
        "score": 2,
        "max_score": 10,
        "details": {}
    }
    explanation = generate_stage_explanation(score_data)
    assert "Stage: Stage 1" in explanation
    assert "Score: 2/10" in explanation
    assert "Details:" not in explanation


def test_generate_explanation_error_handling():
    # Pass none or invalid type to trigger exception
    explanation = generate_stage_explanation(None)
    assert "Stage: ERROR" in explanation
    assert "Unable to generate explanation" in explanation


def test_stage_explanation_generator_class_backward_compatibility():
    generator = StageExplanationGenerator()
    score_data = {
        "stage": "Stage 4",
        "score": 1,
        "max_score": 10,
        "details": {"ticker": "TCS"}
    }
    explanation = generator.generate_explanation(score_data)
    assert "Stage: Stage 4" in explanation
    assert "- ticker: TCS" in explanation


def test_render_trend_detailed():
    score_data = {
        "stage": "Stage 2",
        "score": 7,
        "max_score": 10,
        "details": {
            "ticker": "SBIN",
            "SMA21": 600.0
        }
    }
    res = render_trend(score_data, multiline=True)
    expected = "Stage: Stage 2\nScore: 7/10\nDetails:\n- ticker: SBIN\n- SMA21: 600.0"
    assert res == expected


def test_render_trend_detailed_no_details():
    score_data = {
        "stage": "Stage 2",
        "score": 7,
        "max_score": 10,
        "details": None
    }
    res = render_trend(score_data, multiline=True)
    assert res == "Stage: Stage 2\nScore: 7/10"


def test_render_trend_basic_summary():
    score_data = {
        "stage": "Stage 2",
        "score": 7,
        "max_score": 10
    }
    res = render_trend(score_data, multiline=False)
    assert res == "Stage 2 stage – 7/10"


def test_engine_orchestration():
    history = [{"close": 100.0 + i * 0.2} for i in range(60)]
    stock_data = {"ticker": "RELIANCE", "history": history, "SMA21": 110.0, "SMA50": 105.0}

    # Test analyze
    analysis = analyze(stock_data)
    assert "score" in analysis
    assert "explanation" in analysis
    assert "trend" in analysis
    assert analysis["score"]["stage"] == "Stage 2"
    assert "Stage: Stage 2" in analysis["explanation"]
    assert "Stage: Stage 2" in analysis["trend"]

    # Test get_score
    score = get_score(stock_data)
    assert score["stage"] == "Stage 2"

    # Test explain
    explanation = explain(score)
    assert "Stage: Stage 2" in explanation

    # Test render
    trend_str = render(score, multiline=False)
    assert trend_str == "Stage 2 stage – 0/10"
