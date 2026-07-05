"""
scripts/smoke_test_mcs.py
Run: python scripts/smoke_test_mcs.py
Purpose: Verify end-to-end MCS calculation for 5 NSE stocks.
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from run import create_app
from app.services.scoring_service import MomentumConfidenceScoreService

SYMBOLS = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'TATAMOTORS']

def main():
    app = create_app('development')
    results = []
    with app.app_context():
        svc = MomentumConfidenceScoreService()
        for sym in SYMBOLS:
            r = svc.calculate_score_for_stock(sym, 'NSE')
            print(f"\n{'='*50}\n{sym}: {r.get('total_score', '?')}/100  "
                  f"| Badges: {r.get('badges', [])}")
            print(f"  Technical={r.get('technical_score')} "
                  f"Fundamental={r.get('fundamental_score')} "
                  f"Momentum={r.get('momentum_score')} "
                  f"Institutional={r.get('institutional_score')} "
                  f"Risk={r.get('risk_liquidity_score')}")
            results.append(r)

    os.makedirs('logs', exist_ok=True)
    with open('logs/mcs_smoke_test.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print("\n✅ Smoke test complete. Results saved to logs/mcs_smoke_test.json")

if __name__ == '__main__':
    main()