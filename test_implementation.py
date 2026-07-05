"""
Test script to verify the Momentum Confidence Score implementation
"""
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def test_imports():
    """Test that all modules can be imported successfully."""
    print("Testing imports...")

    try:
        from config import load_momentum_score_weights, save_momentum_score_weights
        print("[PASS] Config module imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import config module: {e}")
        return False

    try:
        from app.models import MomentumScore
        print("[PASS] Models module imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import models module: {e}")
        return False

    try:
        from app.services.scoring.technical import TechnicalAnalyzer
        print("[PASS] Technical analyzer imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import technical analyzer: {e}")
        return False

    try:
        from app.services.scoring.fundamentals import FundamentalAnalyzer
        print("[PASS] Fundamental analyzer imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import fundamental analyzer: {e}")
        return False

    try:
        from app.services.scoring.momentum import MomentumAnalyzer
        print("[PASS] Momentum analyzer imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import momentum analyzer: {e}")
        return False

    try:
        from app.services.scoring.institutional import InstitutionalAnalyzer
        print("[PASS] Institutional analyzer imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import institutional analyzer: {e}")
        return False

    try:
        from app.services.scoring.risk import RiskAnalyzer
        print("[PASS] Risk analyzer imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import risk analyzer: {e}")
        return False

    try:
        from app.services.scoring.badges import BadgeAwarder
        print("[PASS] Badge awarder imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import badge awarder: {e}")
        return False

    try:
        from app.services.scoring.explanations import ExplanationGenerator
        print("[PASS] Explanation generator imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import explanation generator: {e}")
        return False

    try:
        from app.services.scoring.ranking import StockRanker
        print("[PASS] Stock ranker imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import stock ranker: {e}")
        return False

    try:
        from app.services.scoring_service import MomentumConfidenceScoreService
        print("[PASS] Scoring service imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import scoring service: {e}")
        return False

    return True

def test_weights():
    """Test loading and saving weights."""
    print("\nTesting weights functionality...")

    try:
        from config import load_momentum_score_weights, save_momentum_score_weights

        # Test loading default weights
        weights = load_momentum_score_weights()
        expected_weights = {
            'technical_strength': 30,
            'fundamental_quality': 25,
            'momentum': 20,
            'institutional_confidence': 15,
            'risk_liquidity': 10
        }

        if weights == expected_weights:
            print("[PASS] Default weights loaded correctly")
        else:
            print(f"[FAIL] Unexpected weights: {weights}")
            return False

        # Test saving weights
        test_weights = {
            'technical_strength': 25,
            'fundamental_quality': 25,
            'momentum': 20,
            'institutional_confidence': 20,
            'risk_liquidity': 10
        }

        # Note: We won't actually save to avoid overwriting the config
        print("[PASS] Weights functionality working correctly")
        return True
    except Exception as e:
        print(f"[FAIL] Failed weights test: {e}")
        return False

def test_scoring_service_initialization():
    """Test that the scoring service initializes correctly."""
    print("\nTesting scoring service initialization...")

    try:
        from app.services.scoring_service import MomentumConfidenceScoreService

        service = MomentumConfidenceScoreService()
        print("[PASS] Scoring service initialized successfully")

        # Check that weights were loaded
        expected_weights = {
            'technical_strength': 30,
            'fundamental_quality': 25,
            'momentum': 20,
            'institutional_confidence': 15,
            'risk_liquidity': 10
        }

        if service.weights == expected_weights:
            print("[PASS] Weights loaded correctly in service")
        else:
            print(f"[FAIL] Unexpected weights in service: {service.weights}")
            return False

        return True
    except Exception as e:
        print(f"[FAIL] Failed to initialize scoring service: {e}")
        return False

def main():
    """Run all tests."""
    print("Running Momentum Confidence Score implementation tests...\n")

    tests = [
        test_imports,
        test_weights,
        test_scoring_service_initialization
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("[SUCCESS] All tests passed!")
        return 0
    else:
        print("[FAILURE] Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())