# Plan: Implement Authentication and Security for MomentumScan

## Goal
Implement comprehensive authentication, authorization, and security measures to make MomentumScan production-ready.

## Prerequisites
- Review SPEC.md for detailed requirements
- Review FIX_PLAN.md for implementation roadmap
- Ensure development environment is set up
- Run existing tests to establish baseline

## Phase 1: Foundation Setup

### Task 1: Add Authentication Dependencies
- Add flask-login, flask-wtf, flask-talisman, flask-limiter to requirements.txt
- Install dependencies: pip install -r requirements.txt

### Task 2: Initialize Authentication Extensions
- Create/extend app/extensions.py to initialize LoginManager, CSRFProtal, Talisman, Limiter
- Update app/__init__.py to initialize these extensions

### Task 3: Enhance User Model
- Add authentication fields to User model in app/models.py:
  - is_active (boolean)
  - is_admin (boolean) 
  - last_login (datetime)
  - failed_login_attempts (integer)
  - locked_until (datetime)
- Add methods for password hashing, checking, login tracking

### Task 4: Create Auth Blueprint
- Create app/api/v1/auth.py with endpoints for:
  - GET/POST /auth/register
  - registration
I login system, facilitating user management. I will cover with password being able to log in the endpoint for login
  - GET /auth/logout
  - GET /auth/profile
  - POST /auth/change-password

## Phase 2: Protection Implementation

### Task 5: Protect Existing Endpoints
- Identify all state-changing endpoints (POST, PUT, DELETE, PATCH)
- Add @login_required decorator to these endpoints
- For GET endpoints that expose sensitive data, also add protection
- Update API documentation in docstrings

### Task 6: Implement CSRF Protection
- Configure CSRF protection for all state-changing operations
- Update templates to include {{ csrf_token() }} in forms
- Update JavaScript AJAX calls to include CSRF tokens in headers

### Task 7: Add Input Validation System
- Create app/utils/validation.py with:
  - Ticker symbol validator (regex: ^[A-Z0-9.]{1,10}$)
  - Numeric validators (positive integers, floats, ranges)
  - Text validators (length, sanitization)
  - Custom validators for specific use cases
- Integrate validation into all API endpoints
- Return 400 Bad Request with descriptive messages for invalid input

### Task 8: Fix SQL Injection Vulnerabilities
- Audit app/database.py for raw SQL with string formatting
- Convert to parameterized queries using ? placeholders
- Audit app/api/v1/legacy_routes.py similarly
- Ensure all service layer uses SQLAlchemy ORM properly
- Replace any remaining raw SQL with ORM queries

### Task 9: Implement Proper Error Handling
- Create app/utils/errors.py with:
  - Standard error response format
  - Global error handlers for 400, 401, 403, 404, 500
  - Helper functions for common error responses
- Update app/__init__.py to register error handlers
- Replace ad-hoc error returns with standardized helpers
- Ensure production errors don't leak stack traces

## Phase 3: Security Hardening

### Task 10: Add Security Headers
- Configure Flask-Talisman with appropriate defaults:
  - force_https: False (for development, True in production)
  - strict_transport_security: max_age=31536000, include_subdomains
  - frame_options: DENY
  - content_security_policy: reasonable defaults
  - content_security_policy_nonce_in: ['script-src']
  - referrer_policy: strict-origin-when-cross-origin

### Task 11: Implement Rate Limiting
- Configure Flask-Limiter:
  - Default limits: 100 per hour per IP
  - Stricter limits for auth endpoints: 5 per minute
  - Sensitive operations: 10 per hour
  - Exemptions for health checks if needed
- Store rate data in Redis for production (memory for dev)

### Task 12: Enhance Logging and Monitoring
- Configure structured logging in app/__init__.py
- Ensure security events are logged (failed logins, etc.)
- Don't log sensitive information (passwords, tokens)
- Set appropriate log levels for production

## Phase 4: Testing and Verification

### Task 13: Create Security Test Suite
- tests/test_auth.py:
  - User registration, login, logout
  - Password validation and hashing
  - Session management
  - Access control (protected vs unprotected endpoints)
- tests/test_csrf.py:
  - CSRF token generation and validation
  - Protection against missing/invalid tokens
- tests/test_validation.py:
  - All validation functions work correctly
  - Edge cases and boundary conditions
- tests/test_security.py:
  - SQL injection attempt prevention
  - Information leakage tests
  - Security headers verification
  - Rate limiting effectiveness

### Task 14: Update Existing Tests
- Modify existing tests to handle authentication:
  - Add login/logout in test setup/teardown
  - Use authenticated test client where needed
  - Update fixtures to create test users
- Ensure all existing tests still pass

### Task 15: Perform Manual Security Verification
- Create SECURITY_CHECKLIST.md with:
  - Authentication bypass attempts
  - CSRF testing
  - Input validation boundary testing
  - SQL injection attempts
  - Information leakage checks
  - Security headers verification
  - Rate limiting tests
- Execute checklist and document results

## Phase 5: Documentation and Cleanup

### Task 16: Update Documentation
- Update README.md with:
  - Authentication requirements
  - How to register/login
  - API changes due to security
- Update docs/ with:
  - Authentication API documentation
  - Security best practices
  - Deployment considerations

### Task 17: Cleanup and Deprecation
- Mark deprecated database helpers in app/database.py
- Add TODOs for removing legacy SQLite helpers in future
- Ensure consistent use of SQLAlchemy ORM going forward
- Remove any commented-out code or debug statements

## Phase 6: Final Verification

### Task 18: Run Full Test Suite
- Execute: pytest --cov=app
- Verify coverage meets targets (≥85% for services)
- Fix any failing tests

### Task 19: Performance Validation
- Run: python scripts/run_performance_tests.py
- Ensure authentication doesn't significantly impact performance
- Optimize if necessary (caching, indexing, etc.)

### Task 20: Pre-Production Checklist
- Verify all secrets are in environment variables
- Check that debug mode is off for production
- Validate logging doesn't contain sensitive data
- Confirm error pages don't leak stack traces
- Ensure all dependencies are up to date
- Run security scan (bandit, safety) if available

## Dependencies
- Tasks must be completed in order where indicated
- Authentication foundation (Tasks 1-4) must complete before protection (Tasks 5-9)
- Testing (Tasks 13-15) should run concurrently with development
- Documentation (Task 16) can lag slightly but should be complete before sign-off

## Estimated Timeline
- Foundation Setup: 1 day
- Protection Implementation: 2 days
- Security Hardening: 1 day
- Testing and Verification: 2 days
- Documentation and Cleanup: 0.5 days
- Final Verification: 0.5 days
- Total: ~7 days

## Success Criteria
All tasks completed, tests passing, manual verification checklist signed off, and the application is ready for production deployment with appropriate security measures in place.