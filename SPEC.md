# Spec: MomentumScan Security & Authentication Implementation

## Objective
Implement comprehensive authentication, authorization, and security measures for the MomentumScan stock screener application to make it production-ready. This includes adding user authentication, role-based access control, CSRF protection, input validation, SQL injection prevention, and other security hardening measures.

**Who is the user?**
- Individual investors and traders using the MomentumScan platform
- Administrators managing the system (if role-based access is implemented)
- Anonymous users accessing public data (limited to read-only endpoints)

**What does success look like?**
- Users can register, login, and logout securely
- All state-changing operations require authentication
- User sessions are properly managed and secured
- CSRF tokens protect against cross-site request forgery
- Input validation prevents injection attacks
- SQL injection vulnerabilities are eliminated
- Error messages don't leak sensitive information
- Security headers are present in all responses
- Rate limiting protects against abuse
- The application passes security scanning and penetration testing

## Tech Stack
safely handle user data in production

## Commands
- Install dependencies: `pip install -r requirements.txt`
- Install auth dependencies: `pip install flask-login flask-wtf flask-talisman flask-limiter`
- Run tests: `pytest`
- Run tests with coverage: `pytest --cov=app`
- Run performance tests: `python scripts/run_performance_tests.py`
- Run E2E tests: `python -m pytest -q e2e/tests/*.py`
- Start development server: `python run.py`
- Start production server: `gunicorn -w 4 -b 0.0.0.0:5000 run:app`

## Project Structure
```
MomentumScan/                 → Root directory
├── app/                      → Core Flask application
│   ├── __init__.py           → Application factory and setup
│   ├── extensions.py         → Flask extensions (db, login, csrf, etc.)
│   ├── models.py             → SQLAlchemy data models
│   models
│   ├── config.py             → Configuration classes
│   ├── database.py           → Database connection helpers (to be deprecated)
│   ├── utils/                → Utility functions
│   │   ├── validation.py     → Input validation helpers
│   │   ├── errors.py         → Error handling utilities
│   │   └── decorators.py     → Auth and permission decorators
│   ├── services/             → Business logic layer
│   │   ├── watchlist_service.py
│   │   ├── screener_service.py
│   │   └── ... (other services)
│   ├── api/                  → API endpoints
│   │   └── v1/               → Versioned API
│   │       ├── __init__.py   → Blueprint registration
│   │       ├── auth.py       → Authentication endpoints (NEW)
│   │       ├── watchlist.py  → Watchlist management
│   │       ├── screener.py   → Screener operations
│   │       └── ... (other endpoints)
│   ├── tasks/                → Background jobs
│   │   └── scheduler.py      → APScheduler setup
│   └── templates/            → HTML templates
├── tests/                    → Test suite
│   ├── test_auth.py          → Authentication tests (NEW)
│   ├── test_csrf.py          → CSRF protection tests (NEW)
│   ├── test_validation.py    → Input validation tests (NEW)
│   ├── test_security.py      → Security tests (NEW)
│   └── ... (existing tests)
├── static/                   → CSS, JavaScript, images
├── docs/                     → Documentation
├── scripts/                  → Utility scripts
├── requirements.txt          → Python dependencies
├── run.py                    → Application entry point
└── FIX_PLAN.md               → Implementation plan (this document)
```

## Code Style
```python
# Good: Proper Flask-Login user model
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128))
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Good: Protected endpoint with validation
@api_bp.route('/watchlist/items', methods=['POST'])
@login_required
def add_watchlist_item():
    """
    Add item to watchlist.
    ---
    parameters:
      - name: section_id
        in: formData
        type: integer
        required: true
      - name: ticker
        in: formData
        type: string
        required: true
        pattern: ^[A-Z0-9.]{1,10}$
    responses:
      200:
        description: Item added successfully
      400:
        description: Invalid input
      401:
        description: Authentication required
    """
    try:
        section_id = int(request.form.get('section_id'))
        ticker = request.form.get('ticker', '').upper().strip()
        
        # Input validation
        if not section_id or section_id <= 0:
            return jsonify(error="Invalid section ID"), 400
            
        if not ticker or not re.match(r'^[A-Z0-9.]{1,10}$', ticker):
            return jsonify(error="Invalid ticker symbol"), 400
            
        # Business logic
        watchlist_service.add_item(section_id, ticker)
        return jsonify(success=True, message="Item added")
        
    except ValueError:
        return jsonify(error="Invalid section ID format"), 400
    except Exception as e:
        current_app.logger.error(f"Error adding watchlist item: {e}")
        return jsonify(error="Internal server error"), 500

# Good: CSRF protected form in template
<form method="POST" action="{{ url_for('api.add_watchlist_item') }}">
    {{ csrf_token() }}
    <input type="text" name="ticker" placeholder="Enter stock symbol">
    <button type="submit">Add to Watchlist</button>
</form>
```

Key conventions:
- Use snake_case for functions and variables
- Use PascalCase for classes
- All API endpoints return JSON with consistent format: `{success: boolean, data: ..., error: ...}`
- Use Flask-Login's `@login_required` decorator for protection
- Validate all inputs early in the request handling
- Use parameterized queries or SQLAlchemy ORM for database operations
- Log errors appropriately but don't expose them to users
- Keep functions focused and under 50 lines when possible
- Add type hints to function signatures
- Write docstrings for all public functions and classes

## Testing Strategy
- **Framework**: pytest with pytest-flask for testing Flask applications
- **Test locations**:
  - Unit tests: `tests/` directory
  - Authentication tests: `tests/test_auth.py`
  - CSRF tests: `tests/test_csrf.py`
  - Validation tests: `tests/test_validation.py`
  - Security tests: `tests/test_security.py`
  - Existing tests remain in their current locations
- **Coverage expectations**:
  - ≥90% for authentication and security-related code
  - ≥85% for service APIs (as per existing requirements)
  - ≥80% overall coverage
- **Test levels**:
  - Unit tests: Test individual functions and methods
  - Integration tests: Test API endpoints with test client
  - Security tests: Test authentication, authorization, input validation, CSRF protection
  - No E2E test changes required for this security work (existing E2E tests may need updates to handle authentication)

## Boundaries
- **Always do**:
  - Write unit tests for new functionality before or during implementation
  - Validate and sanitize all user inputs
  - Use parameterized queries or SQLAlchemy ORM for database operations
  - Handle exceptions gracefully without leaking stack traces to users
  - Follow existing code style and conventions
  - Run the test suite before considering work complete
  
- **Ask first**:
  - Making changes to the User model or authentication system
  - Adding new dependencies (especially security-related ones)
  - Changing the database schema for auth tables
  - Modifying the application factory or extension initialization
  - Changing the API versioning or URL structure
  
- **Never do**:
  - Commit secrets, API keys, or passwords to version control
  - Disable authentication or CSRF protection in production
  - Store passwords in plain text
  - Remove failing tests without fixing them or getting approval
  - Use string formatting or concatenation for SQL queries with user input
  - Return detailed error messages or stack traces to clients in production

## Success Criteria
- [ ] Users can register accounts with email verification (if implemented)
- [ ] Users can login with username/email and password
- [ ] Users can logout and have their session invalidated
- [ ] Authenticated users can access protected endpoints
- [ ] Unauthenticated requests to protected endpoints return 401
- [ ] CSRF tokens are required and validated for all state-changing operations
- [ ] Invalid CSRF tokens result in 400 Bad Request responses
- [ ] All user inputs are validated and sanitized before processing
- [ ] SQL injection attempts are prevented and logged
- [ ] Error messages don't contain stack traces or internal implementation details
- [ ] Security headers (X-Frame-Options, X-Content-Type-Options, etc.) are present
- [ ] Rate limiting prevents abuse of authentication and API endpoints
- [ ] All existing functionality continues to work with authentication added
- [ ] Test suite passes with ≥85% coverage for service APIs
- [ ] New security tests pass

## Open Questions
1. Should we implement email verification for registration?
2. What roles and permissions should we implement beyond basic user/admin?
3. Should we implement remember-me functionality or keep sessions strictly server-side?
4. What should be the session lifetime and renewal strategy?
5. Should we implement rate limiting differently for authenticated vs anonymous users?
6. How should we handle API keys for external services (Marketaux, etc.) in relation to user accounts?
7. Should we implement two-factor authentication for sensitive operations?
8. What is the policy for account locking after failed login attempts?
9. Should we implement password strength requirements?
10. How should we handle password resets and account recovery?