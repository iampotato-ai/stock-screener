"""
Verify fetch_screener_fundamentals() parses CAPILLARY correctly.
Expected from screener.in live data:
  Quarters: Dec 2024, Mar 2025, Sep 2025, Dec 2025, Mar 2026
  Net Profit: 10, 10, 0, 8, 43   (Cr)
  EPS in Rs:  1.40, 1.34, 0.04, 1.01, 5.46
  Sales:      159, 152, 179, 184, 191
"""
import sys, os
sys.path.insert(0, os.path.abspath('.'))

# Stub out sqlite3 so app imports cleanly without a real DB
import sqlite3
orig_connect = sqlite3.connect
import tempfile
_fd, _path = tempfile.mkstemp()
sqlite3.connect = lambda db, *a, **kw: orig_connect(_path if db == 'scan_history.db' else db, *a, **kw)

import app
app.init_db()

result = app.fetch_screener_fundamentals('CAPILLARY')

if not result:
    print('ERROR: got empty result')
    sys.exit(1)

print(f'Parsed {len(result)} quarters:')
for q in result:
    print(f"  {q['quarter']} ({q['date_key']}): "
          f"revenue={q['revenue']}, net_profit={q['net_profit']}, eps={q['eps']}")

# Assertions against known-good yfinance values
assert len(result) == 4, f"Expected 4 quarters, got {len(result)}"

# Mar 2026 is the last quarter
mar26 = result[-1]
assert mar26['quarter'] == 'Mar 2026', f"Last quarter should be Mar 2026, got {mar26['quarter']}"
assert mar26['net_profit'] == 43.36, f"Mar 2026 net_profit should be 43.36, got {mar26['net_profit']}"
assert mar26['eps'] == 5.47, f"Mar 2026 EPS should be 5.47, got {mar26['eps']}"
assert mar26['revenue'] == 191.35, f"Mar 2026 revenue should be 191.35, got {mar26['revenue']}"

print('\nAll assertions PASSED.')
