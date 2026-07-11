# Plan: Implement RS Score Feature for MomentumScan Screener

## Goal
Add Relative Strength (RS) Score calculation and display to the MomentumScan screener table to help users identify strong momentum stocks.

## Prerequisites
- Review RS_SPEC.md for detailed requirements
- Ensure development environment is set up with all dependencies
- Run existing test suite to establish baseline
- Check if pandas is available (may need to add to requirements.txt)

## Phase 1: Foundation Setup

### Task 1: Add Required Dependencies
- Check if pandas is already in requirements.txt
- If not, add pandas to requirements.txt
- Install dependencies: pip install -r requirements.txt

### Task 2: Create Calculation Utilities
- Create app/utils/calculation.py with mathematical helper functions
- Implement basic validation for financial calculations
- Add helper functions for percentage calculations, ranking, etc.

### Task 3: Create RS Service
- Create app/services/rs_service.py with RSService class
- Implement weighted momentum score calculation (40% 3M + 20% 6M + 20% 9M + 20% 12M)
- Implement percentile ranking algorithm (1-99 scale)
- Add methods for handling edge cases (missing data, new stocks, etc.)

## Phase 2: Integration with Screener

### Task 4: Update Screener Service
- Modify app/services/screener_service.py
- Import and use RSService in get_scan_results method
- Calculate momentum scores for each stock using available return data
- Apply RS score tocks with RS scores
- Handle cases where return data is incomplete

### Task 5: Update Data Models (if needed)
- Check if existing models store the required return data (1M, 3M, 6M, 9M, 12M)
- If not stored, determine where to get this data from (likely from screener service)
- Add any necessary model fields or properties for storing RS scores

### Task 6: Update Screener API Endpoints
- Verify that app/api/v1/screener.py returns RS scores in the response
- Ensure the API documentation in docstrings mentions the RS Score field
- Confirm that existing parameters (limit, etc.) still work correctly

## Phase 3: UI Integration

### Task 7: Update Frontend Templates
- Check templates/index.html (main dashboard/screener view)
- Add RS Score column to the screener table
- Ensure the column is sortable (if using client-side sorting)
- Add appropriate styling for the RS Score column
- Consider adding tooltips or help text explaining what RS Score means

### Task 8: Update Static Assets
- Check if any JavaScript needs updating to handle the new column
- Ensure sorting/filtering functionality works with RS Score
- Update any data processing scripts if needed

## Phase 4: Testing

### Task 9: Create Unit Tests for RS Calculation
- Create tests/test_rs_calculation.py
- Test weighted momentum score calculation with various inputs
- Test percentile ranking algorithm
- Test edge cases (empty data, all same values, extreme values)
- Test that scores are always between 1-99

### Task 10: Create Service Tests
- Create tests/test_rs_service.py
- Test RSService class methods
- Test integration with screener service methods
- Test handling of missing or incomplete data

### Task 11: Create Integration Tests
- Create tests/test_screener_rs.py
- Test that screener API returns RS scores
- Test that RS scores are calculated correctly in context
- Test performance impact is acceptable

### Task 12: Update Existing Tests
- Modify any existing screener tests to account for new RS Score field
- Ensure all existing tests still pass

## Phase 5: Performance and Optimization

### Task 13: Performance Testing
- Run performance tests before and after implementation
- Ensure RS calculation doesn't significantly slow down screener
- Consider caching strategies if performance is an issue
- Test with various dataset sizes

### Task 14: Optimize if Needed
- Implement caching for RS scores if calculating in real-time is too slow
- Consider pre-calculating and storing RS scores if appropriate
- Optimize database queries if needed

## Phase 6: Documentation and Cleanup

### Task 15: Update Documentation
- Update README.md to mention RS Score feature
- Add documentation to docs/ about the RS Score calculation
- Update API documentation if needed
- Add inline comments explaining the calculation logic

### Task 16: Cleanup
- Remove any commented-out code or debug statements
- Ensure code follows existing style conventions
- Verify all imports are necessary and properly organized

## Dependencies and Ordering
1. Dependencies must be installed before implementation
2. Calculation utilities and RS service must be created before integrating with screener
3. Screener service updates must come before API endpoint verification
4. UI updates can happen in parallel with backend work
5. Testing should be done throughout, with final verification after all changes
6. Documentation should be updated as features are implemented

## Estimated Timeline
- Foundation Setup: 0.5 days
- RS Service Creation: 1 day
- Screener Integration: 1 day
- UI Integration: 0.5 days
- Testing: 1 day
- Performance Optimization: 0.5 days
- Documentation: 0.5 days
- Total: ~4 days

## Success Criteria
- RS Score column visible in screener table
- RS Scores calculated correctly using 40/20/20/20 weighting
- Scores properly scaled to 1-99 percentile ranking
- Existing screener functionality unchanged
- All tests pass
- Performance impact acceptable
- Documentation updated