# Spec: Add RS Score Column to Screener Table

## Objective
Add Relative Strength (RS) Score calculation and display to the MomentumScan screener table. The RS Score measures a stock's performance relative to all other stocks in the market over multiple time periods, expressed as a percentile ranking from 1-99. This will help users identify strong momentum stocks for investment decisions.

**Who is the user?**
- Individual investors and traders using MomentumScan to identify momentum stocks
- Users who want to compare stock performance relative to the broader market
- Traders looking for stocks with strong relative strength characteristics

**What does success look like?**
- Screener table displays an "RS Score" column for each stock
- RS Score is calculated as a percentile ranking (1-99) based on weighted multi-period returns
- Calculation uses the formula: 40%×3M Return + 20%×6M Return + 20%×9M Return + 20%×12M Return
- Scores are updated regularly (daily or with screener refresh)
- Users can sort screener results by RS Score
- RS Score calculation is accurate and performs efficiently
- Existing screener functionality remains unaffected

## Tech Stack
- Python 3.8+ (Flask backend)
- SQLAlchemy ORM (database interactions)
- Pandas/Numerical Python (for calculations if needed)
- Existing screener infrastructure (TradingView API, database models)
- Redis or database caching (for performance optimization)

## Commands
- Install dependencies: `pip install -r requirements.txt` (add pandas if not present)
- Run tests: `pytest`
- Run tests with coverage: `pytest --cov=app`
- Run performance tests: `python scripts/run_performance_tests.py`
- Start development server: `python run.py`
- Create migration (if needed): `flask db migrate -m "Add RS score to screener tables"`
- Apply migration: `flask db upgrade`

## Project Structure
```
MomentumScan/                 → Root directory
├── app/                      → Core Flask application
│   ├── __init__.py           → Application factory and setup
│   ├── extensions.py         → Flask extensions
│   ├── models.py             → SQLAlchemy data models (to be updated)
│   ├── utils/                → Utility functions
│   │   ├── calculation.py    → Mathematical calculation helpers (NEW)
│   │   └── validation.py     → Input validation helpers
│   ├── services/             → Business logic layer
│   │   ├── screener_service.py     → Main screener logic (to be updated)
│   │   └── rs_service.py           → RS Score calculation service (NEW)
│   ├── api/                  → API endpoints
│   │   └── v1/               → Versioned API
│   │       ├── __init__.py   → Blueprint registration
│   │       └── screener.py   → Screener endpoints (to be updated)
│   └── tasks/                → Background jobs
│       └── scheduler.py      → APScheduler setup (may need updates)
├── tests/                    → Test suite
│   ├── test_rs_calculation.py    → RS Score calculation tests (NEW)
│   ├── test_rs_service.py        → RS Service tests (NEW)
│   └── test_screener_rs.py       → Screener RS integration tests (NEW)
├── static/                   → CSS, JavaScript, images
├── docs/                     → Documentation
├── scripts/                  → Utility scripts
├── requirements.txt          → Python dependencies
├── run.py                    → Application entry point
└── migrations/               → Database migrations (if using Flask-Migrate)
```

## Code Style
```python
# Good: RS Score calculation service
class RSService:
    """Service for calculating Relative Strength scores."""
    
    def __init__(self):
        self.weights = {
            '3m': 0.40,
            '6m': 0.20,
            '9m': 0.20,
            '12m': 0.20
        }
    
    def calculate_momentum_score(self, returns_dict: Dict[str, float]) -> float:
        """
        Calculate weighted momentum score from returns.
        
        Args:
            returns_dict: Dictionary with keys '3m', '6m', '9m', '12m' containing percentage returns
            
        Returns:
            Weighted momentum score
        """
        score = 0.0
        for period, weight in self.weights.items():
            score += weight * returns_dict.get(period, 0.0)
        return score
    
    def calculate_rs_scores(self, stocks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculate RS scores (percentile rankings) for a list of stocks.
        
        Args:
            stocks_data: List of stock dictionaries with momentum_score
            
        Returns:
            List of stocks with added rs_score field (1-99)
        """
        if not stocks_data:
            return stocks_data
            
        # Sort by momentum score descending
        sorted_stocks = sorted(
            stocks_data, 
            key=lambda x: x.get('momentum_score', 0.0), 
            reverse=True
        )
        
        total_stocks = len(sorted_stocks)
        for i, stock in enumerate(sorted_stocks):
            # Calculate percentile: 100 * (N - Rank + 1) / N
            # Where Rank = i + 1 (1-based ranking)
            percentile = 100 * (total_stocks - (i + 1) + 1) / total_stocks
            stock['rs_score'] = max(1, min(99, round(percentile)))
            
        return sorted_stocks

# Good: Updated screener service method
def get_scan_results(self, limit: int = 500, live: bool = False, full_response: bool = False) -> Any:
    """
    Get the latest screener scan results with RS scores.
    """
    # ... existing logic to get stocks ...
    
    # Calculate RS scores if we have the needed data
    if has_required_return_data(stocks):
        rs_service = RSService()
        stocks_with_rs = rs_service.calculate_rs_scores(stocks)
        # ... return stocks_with_rs ...
    
    # ... existing return logic ...

# Good: Screener API endpoint (unchanged but now returns RS score)
@api_bp.route('/scan', methods=['GET'])
@api_bp.route('/screener/scan', methods=['GET'])
def get_screener_scan():
    """
    Get the latest screener scan results.
    Query parameters:
    - limit: maximum number of results to return (default: 500)
    """
    try:
        limit = request.args.get('limit', '500').strip()
        try:
            limit = int(limit) if limit.isdigit() else 500
        except ValueError:
            limit = 500

        scan_data = screener_service.get_scan_results(limit=limit, live=True, full_response=True)
        if isinstance(scan_data, dict):
            return jsonify(
                success=True,
                count=len(scan_data['stocks']),
                data=scan_data['stocks'],
                total_scanned=scan_data.get('total_scanned', len(scan_data['stocks'])),
                total_matched=scan_data.get('total_matched', len(scan_data['stocks'])),
                universe=scan_data.get('universe', [])
            )
        else:
            return jsonify(
                success=True,
                count=len(scan_data),
                data=scan_data,
                total_scanned=len(scan_data),
                total_matched=len(scan_data),
                universe=[]
            )
    except Exception as e:
        current_app.logger.error(f"Error getting screener scan: {e}")
        return jsonify(error=str(e)), 500
```

Key conventions:
- Use snake_case for functions and variables
- Use PascalCase for classes
- All API endpoints return JSON with consistent format
- Add comprehensive docstrings to all public functions and classes
- Handle edge cases (empty data, missing values)
- Log errors appropriately but don't expose them to users
- Keep functions focused and under 50 lines when possible
- Add type hints to function signatures
- Validate inputs early in the request handling

## Testing Strategy
- **Framework**: pytest with pytest-flask for testing Flask applications
- **Test locations**:
  - Unit tests: `tests/test_rs_calculation.py` (pure calculation functions)
  - Service tests: `tests/test_rs_service.py` (RSService class)
  - Integration tests: `tests/test_screener_rs.py` (screener with RS scores)
  - Existing tests remain in their current locations
- **Coverage expectations**:
  - ≥90% for RS calculation and service code
  - Maintain existing coverage requirements (≥85% for service APIs)
- **Test levels**:
  - Unit tests: Test individual calculation methods, edge cases
  - Service tests: Test RSService class methods with mock data
  - Integration tests: Test screener API returns RS scores correctly
  - Performance tests: Verify RS calculation doesn't significantly impact screener performance

## Boundaries
- **Always do**:
  - Write unit tests for new functionality before or during implementation
  - Handle edge cases (empty data, missing returns, extreme values)
  - Validate that RS scores are always between 1-99 inclusive
  - Ensure calculation accuracy with known test cases
  - Follow existing code style and conventions
  - Run the test suite before considering work complete
  
- **Ask first**:
  - Changing the RS calculation formula or weights
  - Adding new time periods or calculation methods
  - Changing how RS scores are stored or retrieved
  - Making changes to the screener database schema
  - Adding dependencies beyond what's already in requirements.txt
  
- **Never do**:
  - Commit secrets, API keys, or passwords to version control
  - Calculate RS scores without proper data validation
  - Allow RS scores outside the 1-99 range
  - Remove failing tests without fixing them or getting approval
  - Use hard-coded values that should be configurable
  - Perform expensive calculations on every request without caching

## Success Criteria
- [ ] RS Score column appears in screener table UI
- [ ] RS Scores are calculated correctly using the specified formula
- [ ] RS Scores are accurate percentile rankings (1-99)
- [ ] Stocks with higher momentum scores get higher RS Scores
- [ ] RS Score calculation handles edge cases (no data, missing periods)
- [ ] Existing screener functionality continues to work unchanged
- [ ] Performance impact of RS calculation is acceptable (<100ms additional latency)
- [ ] Unit tests for RS calculation pass with ≥90% coverage
- [ ] Integration tests verify RS scores appear in API responses
- [ ] Manual testing confirms RS scores display correctly in UI

## Open Questions
1. Should we calculate RS scores in real-time during screener runs or pre-calculate and store them?
2. What universe of stocks should we use for percentile ranking (all NSE stocks or just screened stocks)?
3. Should we allow configuration of the weighting formula (40/20/20/20 vs other options)?
4. How frequently should RS scores be updated (with each screener refresh, daily, etc.)?
5. Should we store historical RS scores for trend analysis?
6. How should we handle stocks with insufficient return data (e.g., newly listed)?
7. Should we add sector-based or industry-based RS scores in addition to market-wide RS?
8. What is the minimum data requirement for calculating a valid RS score?