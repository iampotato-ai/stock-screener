# MomentumScan Fix Implementation Plan

## Overview
This plan addresses all critical, high, medium, and low priority issues identified in the production readiness audit, plus quick wins. The plan is organized by priority and implementation dependencies.

## Prerequisites
- Review and approve the SPEC.md file (spec-driven-development)
- Ensure development environment is set up with all dependencies
- Run existing test suite to establish baseline

## Phase 1: Authentication & Authorization (Critical)
*Must be completed before considering production deployment*

### Task 1: Implement Flask-Login
- [ ] Task: Install Flask-Login and Flask-WTF dependencies
  - Acceptance: Dependencies installed in requirements.txt
  - Verify: `pip install flask-login flask-wtf` and update requirements.txt
  - Files: requirements.txt

- [ ] Task: Configure login manager in app/extensions.py
  - Acceptance: LoginManager initialized and configured
  - Verify: Login manager accessible via current_app.login_manager
  - Files: app/extensions.py

- [ ] Task: Complete User model implementation
  - Acceptance: User model has all required Flask-Login properties/methods
  - Verify: User.is_authenticated, User.is_active, User.is_anonymous, User.get_id() work correctly
  - Files: app/models.py

- [ ] Task: Create authentication routes (login, logout, register)
  - Acceptance: Users can register, login, logout; sessions work correctly
  - Verify: Test login/logout flow with test client
  - Files: app/api/v1/auth.py (new file), update app/api/v1/__init__.py to import

- [ ] Task: Protect all state-changing endpoints with authentication
  - Acceptance: POST, PUT, DELETE endpoints require authentication
  - Verify: Unauthenticated requests return 401; authenticated requests succeed
  - Files: All API v1 endpoint files (watchlist.py, screener.py, etc.)

### Task 2: Implement Role-Based Access Control (if needed)
- [ ] Task: Define user roles and permissions
  - Acceptance: Role model or role field on User model implemented
  - Verify: Roles can be assigned and checked
  - Files: app/models.py

- [ ] Task: Implement permission decorators
  - Acceptance: Custom decorators for role-based access control
  - Verify: Decorators correctly allow/deny access based on roles
  - Files: app/utils/decorators.py (new)

## Phase 2: CSRF Protection (Critical)
*Should be implemented alongside authentication*

### Task 3: Implement CSRF Protection
- [ ] Task: Configure Flask-WTF CSRF protection
  - Acceptance: CSRF protection enabled for all state-changing endpoints
  - Verify: POST requests without valid CSRF token return 400
  - Files: app/extensions.py, app/__init__.py

- [ ] Task: Add CSRF tokens to forms and AJAX requests
  - Acceptance: All frontend forms include CSRF tokens; AJAX requests handle CSRF
  - Verify: Forms render with CSRF tokens; JavaScript includes token in headers
  - Files: templates/*, static/js/*

## Phase 3: Fixes High) and* 

### Task 4: Fix SQL Injection Vulnerabilities
- [ ] Task: Audit and fix raw SQL queries in database.py
  - Acceptance: All SQL queries use parameterized queries
  - Verify: No string formatting/concatenation of user input in SQL
  - Files: app/database.py

- [ ] Task: Audit and fix SQL queries in legacy_routes.py
  - Acceptance: All SQL queries use parameterized queries
  - Verify: No string formatting/concatenation of user input in SQL
  - Files: app/api/v1/legacy_routes.py

- [ ] Task: Ensure all service layer uses SQLAlchemy ORM properly
  - Acceptance: Services use SQLAlchemy ORM or parameterized queries
  - Verify: No raw SQL with user input concatenation
  - Files: app/services/*

### Task 5: Implement Comprehensive Input Validation
- [ ] Task: Create input validation helpers
  - Acceptance: Validation functions for ticker symbols, numeric inputs, text inputs
  - Verify: Validation functions correctly validate and sanitize inputs
  - Files: app/utils/validation.py (new)

- [ ] Task: Add validation to all API endpoints
  - Acceptance: All API endpoints validate input parameters
  - Verify: Invalid inputs return 400 with descriptive messages
  - Files: All API v1 endpoint files

- [ ] Task: Add validation to service layer methods
  - Acceptance: Service methods validate their inputs
  - Verify: Service methods raise appropriate validation errors
  - Files: app/services/*

## Phase 4: Error Handling & Information Leakage (High)

### Task 6: Implement Proper Error Handling
- [ ] Task: Create global error handlers
  - Acceptance: Global error handlers return generic messages in production
  - Verify: 500 errors don't leak stack traces; 400 errors are descriptive
  - Files: app/__init__.py (error handlers), app/utils/errors.py (new)

- [ ] Task: Update existing try/except blocks
  - Acceptance: External API calls and database operations have proper error handling
  - Verify: Errors are logged appropriately; users get meaningful messages
  - Files: Throughout codebase (legacy_routes.py, services, etc.)

- [ ] Task: Implement logging configuration
  - Acceptance: Errors are logged with sufficient detail for debugging
  - Verify: Log files contain error details; production logs don't leak to clients
  - Files: app/__init__.py (logging config), config.py

## Phase 5: Security Headers & Additional Protections (Medium/Low)

### Task 7: Add Security Headers
- [ ] Task: Implement Flask-Talisman or custom security headers
  - Acceptance: Security headers present in all responses
  - Verify: X-Frame-Options, X-Content-Type-Options, etc. present
  - Files: app/extensions.py or app/__init__.py

### Task 8: Implement Rate Limiting
- [ ] Task: Add rate limiting to authentication and API endpoints
  - Acceptance: Auth endpoints rate-limited; external API calls throttled
  - Verify: Too many requests return 429; legitimate requests work
  - Files: app/extensions.py, app/api/v1/auth.py

### Task 9: Standardize Data Access Patterns
- [ ] Task: Deprecate raw SQLite helpers in favor of SQLAlchemy ORM
  - Acceptance: New code uses SQLAlchemy ORM; legacy helpers marked deprecated
  - Verify: No new usage of raw SQLite helpers for new features
  - Files: app/database.py (mark helpers deprecated), app/models.py

## Phase 6: Quick Wins (Low Effort, High Impact)

### Task 10: Implement Quick Wins
- [ ] Task: Add request size limits
  - Acceptance: Flask configured to reject oversized requests
  - Verify: Requests over limit return 413
  - Files: app/__init__.py

- [ ] Task: Add request logging middleware
  - Acceptance: All requests logged with method, path, status, duration
  - Verify: Request logs appear in application logs
  - Files: app/__init__.py (before_request/after_request handlers)

- [ ] Task: Standardize error response format
  - Acceptance: All JSON errors follow {error: "message"} format
  - Verify: Error responses are consistent across endpoints
  - Files: app/utils/errors.py

- [ ] Task: Add input validation for common parameters
  - Acceptance: Ticker symbols, IDs, and numeric params validated early
  - Verify: Invalid parameters caught before reaching business logic
  - Files: app/utils/validation.py, used in API endpoints

## Phase 7: Testing & Verification

### Task 11: Implement Security Tests
- [ ] Task: Create authentication test suite
  - Acceptance: Tests cover registration, login, logout, protected routes
  - Verify: All auth-related tests pass
  - Files: tests/test_auth.py

- [ ] Task: Create CSRF protection tests
  - Acceptance: Tests verify CSRF tokens required and validated
  - Verify: CSRF tests pass
  - Files: tests/test_csrf.py

- [ ] Task: Create input validation tests
  - Acceptance: Tests verify validation functions work correctly
  - Verify: Validation tests pass
  - Files: tests/test_validation.py

- [ ] Task: Create SQL injection tests
  - Acceptance: Tests attempt SQL injection; verify they fail safely
  - Verify: Security tests pass
  - Files: tests/test_security.py

### Task 12: Verification & Sign-off
- [ ] Task: Run full test suite with coverage
  - Acceptance: All tests pass; coverage meets targets
  - Verify: `pytest --cov=app` shows ≥85% service coverage
  - Files: N/A

- [ ] Task: Perform manual security testing
  - Acceptance: Manual verification of key security controls
  - Verify: Checklist completed and signed off
  - Files: SECURITY_CHECKLIST.md (to be created)

- [ ] Task: Update documentation
  - Acceptance: README and docs reflect new authentication requirements
  - Verify: Documentation is accurate and helpful
  - Files: README.md, docs/*

## Dependencies & Ordering
1. Authentication must be implemented before protecting endpoints
2. CSRF protection should be implemented alongside authentication
3. Input validation should be done before or alongside SQL injection fixes
4. Error handling improvements can be done in parallel with validation
5. Security headers and rate limiting can be implemented later in the cycle
6. Testing should be done throughout, with final verification after all changes

## Estimated Effort
- Critical items (Auth + CSRF): 3-5 days
- High items (SQL injection, validation, error handling): 2-3 days
- Medium/Low items: 1-2 days
- Quick wins: 0.5 days
- Testing: 1-2 days (ongoing)
- Total: 7-12 days depending on scope of role-based access control

## Success Criteria for Plan Completion
All tasks in phases 1-6 completed, all tests passing, and manual security verification checklist signed off.