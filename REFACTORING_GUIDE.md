# Stock Screener Application Refactoring Guide

## Current State Analysis

The `app.py` file has grown to approximately 378.5KB, indicating a monolithic structure that violates separation of concerns principles. Key issues include:

1. **Mixed Responsibilities**: Web routes, business logic, data access, and configuration are intertwined
2. **Difficult Navigation**: Finding specific functionality requires extensive searching
3. **Testing Challenges**: Unit testing is complicated due to tight coupling
4. **Scalability Limitations**: Adding new features increases complexity exponentially
5. **Team Collaboration Difficulties**: Merge conflicts likely when multiple developers work on different features

## Refactoring Goals

1. Separate concerns into distinct layers (presentation, business logic, data access)
2. Organize code by feature/domain rather than technical type
3. Improve testability through dependency injection and clear interfaces
4. Enhance maintainability with consistent patterns and conventions
5. Enable parallel development by reducing coupling between features
6. Preserve all existing functionality during refactoring

## Proposed Directory Structure

```
stock-screener/
│
├── app.py                      # Application factory (minimal)
├── config.py                   # Configuration management
├── requirements.txt            # Dependencies
│
├── /app                        # Main application package
│   ├── __init__.py             # Application factory
│   ├── models.py               # Database models
│   ├── extensions.py           # Flask extensions (db, migrate, etc.)
│   │
│   ├── /api                    # REST API endpoints
│   │   ├── __init__.py
│   │   ├── /v1                 # API versioning
│   │   │   ├── __init__.py
│   │   │   ├── market_breadth.py
│   │   │   ├── screener.py
│   │   │   ├── watchlist.py
│   │   │   ├── journal.py
│   │   │   ├── alerts.py
│   │   │   ├── ipo.py
│   │   │   └── news.py
│   │   │
│   │   └── /utils              # API helpers
│   │       ├── auth.py
│   │       ├── validation.py
│   │       └── responses.py
│   │
│   ├── /services               # Business logic layer
│   │   ├── __init__.py
│   │   ├── market_breadth_service.py
│   │   ├── screener_service.py
│   │   ├── prediction_service.py
│   │   ├── watchlist_service.py
│   │   ├── journal_service.py
│   │   ├── alert_service.py
│   │   ├── nlp_service.py      # NLP-specific logic (from our recent work)
│   │   ├── news_service.py
│   │   └── data_service.py     # Data fetching/processing
│   │
│   ├── /utils                  # Cross-cutting utilities
│   │   ├── __init__.py
│   │   ├── helpers.py
│   │   ├── constants.py
│   │   ├── decorators.py
│   │   └── exceptions.py
│   │
│   ├── /tasks                  # Background tasks (if any)
│   │   └── scheduler.py
│   │
│   └── /templates              # HTML templates (if using server-side rendering)
│       └── /includes
│
├── /migrations                 # Flask-Migrate directory
│
├── /tests                      # Test suite
│   ├── unit/
│   └── integration/
│
├── /scripts                    # Utility scripts
│   └── init_db.py
│
├── instance/                   # Instance-specific config (not in version control)
│   └── config.py
│
└── requirements/
    ├── base.txt
    ├── development.txt
    └── production.txt
```

## Module-by-Module Breakdown

### 1. Application Factory (`/app/__init__.py`)
```python
def create_app(config_name=None):
    app = Flask(__name__)
    
    # Load configuration
    config_obj = config[config_name or os.getenv('FLASK_ENV') or 'default']
    app.config.from_object(config_obj)
    
    # Initialize extensions
    from app.extensions import db, migrate
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Register blueprints
    from app.api.v1 import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    
    # Register error handlers
    from app.utils.errors import register_error_handlers
    register_error_handlers(app)
    
    return app
```

### 2. Configuration (`config.py`)
```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # NLP Configuration
    NLP_MODELS_ENABLED = os.environ.get('NLP_MODELS_ENABLED', 'True').lower() == 'true'
    NLP_MODEL_CACHE_SIZE = int(os.environ.get('NLP_MODEL_CACHE_SIZE', '3'))
    
    # External API Keys
    TRADINGVIEW_SCAN_URL = os.environ.get('TRADINGVIEW_SCAN_URL', 'https://scanner.tradingview.com/india/scan')
    NEWS_API_KEY = os.environ.get('NEWS_API_KEY')

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
```

### 3. Database Models (`/app/models.py`)
```python
from app.extensions import db

class WatchlistSection(db.Model):
    __tablename__ = 'watchlist_sections'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # ... other fields
    items = db.relationship('WatchlistItem', backref='section', lazy=True, cascade='all, delete-orphan')

class WatchlistItem(db.Model):
    __tablename__ = 'watchlist_items'
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('watchlist_sections.id'), nullable=False)
    # ... other fields

# ... other models (TradeJournal, KronosForecast, etc.)
```

### 4. Service Layer Example (`/app/services/screener_service.py`)
```python
from app.models import WatchlistItem, WatchlistSection
from app.utils.helpers import calculate_technical_indicators

class ScreenerService:
    @staticmethod
    def get_screener_data(filters=None, sort_by=None, page=1, per_page=50):
        """Get filtered and paginated screener data"""
        query = WatchlistItem.query
        
        # Apply filters
        if filters:
            if filters.get('sector'):
                query = query.filter(WatchlistItem.sector == filters['sector'])
            if filters.get('market_cap_min'):
                query = query.filter(WatchlistItem.market_cap >= filters['market_cap_min'])
            # ... other filters
        
        # Apply sorting
        if sort_by:
            query = query.order_by(
                getattr(WatchlistItem, sort_by.split(':')[0]).desc() 
                if sort_by.endswith(':desc') 
                else getattr(WatchlistItem, sort_by.split(':')[0]).asc()
            )
        
        # Pagination
        paginated = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # Enhance with calculated fields
        results = []
        for item in paginated.items:
            enhanced_item = item.to_dict()
            enhanced_item.update(
                calculate_technical_indicators(item.ticker)
            )
            results.append(enhanced_item)
        
        return {
            'items': results,
            'total': paginated.total,
            'pages': paginated.pages,
            'current_page': paginated.page
        }
    
    @staticmethod
    def get_sector_performance():
        """Calculate sector rotation data for RRG"""
        # Implementation for sector performance calculation
        pass
```

### 5. NLP Service (Extracted from our recent work) (`/app/services/nlp_service.py`)
```python
from app.utils.constants import _FALLBACK_CATALYST_SCORES
from app.utils.helpers import (
    _prepare_text_for_analysis, 
    _analyze_sentiment, 
    _classify_event_category,
    _generate_summary,
    calculate_base_catalyst_from_nlp,
    map_nlp_category_to_standard,
    _map_sentiment_to_score,
    _get_fallback_catalyst_score,
    classify_announcement  # Existing keyword-based function
)

class NLPService:
    def __init__(self):
        self.sentiment_analyzer = None
        self.event_classifier = None
        self.summarizer = None
        self._models_loaded = False
    
    def init_nlp_models(self):
        """Lazy load NLP models"""
        if self._models_loaded:
            return True
            
        try:
            # Import here to avoid loading unless needed
            from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
            
            # Initialize models only if enabled and dependencies available
            if current_app.config.get('NLP_MODELS_ENABLED', False):
                # Initialize FinBERT for sentiment
                self.sentiment_analyzer = pipeline(
                    "sentiment-analysis",
                    model="ProsusAI/finbert",
                    tokenizer="ProsusAI/finbert",
                    return_all_scores=True
                )
                
                # Initialize zero-shot classifier for event categories
                self.event_classifier = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli"
                )
                
                # Initialize DistilBART for summarization
                self.summarizer = pipeline(
                    "summarification",
                    model="sshleifer/distilbart-cnn-12-6"
                )
            
            self._models_loaded = True
            return True
        except Exception as e:
            current_app.logger.warning(f"NLP models not available: {e}")
            return False
    
    def process_announcement(self, desc: str, text: str, attachment_url: str = "") -> dict:
        """
        Main entry point for announcement processing.
        Uses NLP if available, falls back to keyword matching.
        """
        if not self.init_nlp_models() or not ((desc and len(desc.strip()) > 10) or (text and len(text.strip()) > 10)):
            return self._fallback_classify(desc, text)
        
        try:
            return self._process_with_nlp(desc, text, attachment_url)
        except Exception as e:
            current_app.logger.error(f"NLP processing failed: {e}")
            return self._fallback_classify(desc, text)
    
    def _process_with_nlp(self, desc: str, text: str, attachment_url: str) -> dict:
        """Process announcement using NLP models"""
        full_text = _prepare_text_for_analysis(desc, text, attachment_url)
        
        # Sentiment analysis
        if self.sentiment_analyzer:
            sent_res = _analyze_sentiment(full_text)
            sentiment_label = sent_res["sentiment_label"]
            nlp_sentiment_score = sent_res["nlp_sentiment_score"]
        else:
            # Fallback to keyword-based sentiment
            _, _, _, _, s_sent, _, _ = classify_announcement(desc, text)
            sentiment_label = s_sent.replace("sent-", "")
            nlp_sentiment_score = _map_sentiment_to_score(s_sent)
        
        # Event classification
        if self.event_classifier:
            cat_res = _classify_event_category(full_text)
            event_category = cat_res["event_category"]
            category_confidence = cat_res["category_confidence"]
        else:
            s_cat, s_cat_name, _, _, _, _, _ = classify_announcement(desc, text)
            event_category = s_cat_name.lower()
            category_confidence = 1.0
        
        # Summarization
        summary = _generate_summary(full_text) if self.summarizer else None
        
        # Catalyst calculation
        enhanced_catalyst_score = calculate_base_catalyst_from_nlp(
            sentiment_label, event_category, category_confidence
        )
        cat, cat_name, imp, imp_name = map_nlp_category_to_standard(event_category)
        
        sent_mapped = f"sent-{sentiment_label}"
        sent_name_mapped = {
            "positive": "🟢 Positive",
            "neutral": "🟡 Neutral",
            "negative": "🔴 Negative"
        }.get(sentiment_label, "🟡 Neutral")
        
        reason = f"NLP classification: category='{event_category}' (confidence={category_confidence:.2f}), sentiment='{sentiment_label}' (score={nlp_sentiment_score:.2f})."
        
        return {
            "cat": cat,
            "cat_name": cat_name,
            "imp": imp,
            "imp_name": imp_name,
            "sent": sent_mapped,
            "sent_name": sent_name_mapped,
            "reason": reason,
            "catalyst_score": round(enhanced_catalyst_score, 3),
            "nlp_sentiment_score": round(nlp_sentiment_score, 3),
            "nlp_category": event_category,
            "summary": summary or (desc or "")[:120],
            "impact_magnitude": round(abs(enhanced_catalyst_score), 3),
        }
    
    def _fallback_classify(self, desc: str, text: str) -> dict:
        """Fallback to keyword-based classification"""
        s_cat, s_cat_name, s_imp, s_imp_name, s_sent, s_sent_name, s_reason = classify_announcement(desc, text)
        
        nlp_sentiment_score = _map_sentiment_to_score(s_sent)
        catalyst_score = _get_fallback_catalyst_score(s_cat, s_sent)
        impact_magnitude = round(abs(catalyst_score), 3)
        
        return {
            "cat": s_cat,
            "cat_name": s_cat_name,
            "imp": s_imp,
            "imp_name": s_imp_name,
            "sent": s_sent,
            "sent_name": s_sent_name,
            "reason": s_reason,
            "summary": (desc or "")[:120],  # Consistent with NLP path
            "nlp_category": s_cat_name.lower(),
            "nlp_sentiment_score": nlp_sentiment_score,
            "catalyst_score": round(catalyst_score, 3),
            "impact_magnitude": impact_magnitude,
        }
```

### 6. API Endpoints Example (`/app/api/v1/screener.py`)
```python
from flask import Blueprint, request, jsonify
from app.services.screener_service import ScreenerService
from app.utils.decorators import handle_api_errors

api_bp = Blueprint('api', __name__)

@api_bp.route('/screener', methods=['GET'])
@handle_api_errors
def get_screener_data():
    """Get screener data with filtering and pagination"""
    # Parse query parameters
    filters = {}
    if request.args.get('sector'):
        filters['sector'] = request.args.get('sector')
    if request.args.get('market_cap_min'):
        filters['market_cap_min'] = float(request.args.get('market_cap_min'))
    # ... other filters
    
    sort_by = request.args.get('sort_by', 'market_cap:desc')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    # Get data from service layer
    result = ScreenerService.get_screener_data(
        filters=filters,
        sort_by=sort_by,
        page=page,
        per_page=per_page
    )
    
    return jsonify({
        'success': True,
        'data': result
    }), 200

@api_bp.route('/screener/sectors', methods=['GET'])
@handle_api_errors
def get_sector_performance():
    """Get sector rotation data for RRG visualization"""
    sector_data = ScreenerService.get_sector_performance()
    return jsonify({
        'success': True,
        'data': sector_data
    }), 200
```

## Migration Strategy

### Phase 1: Foundation (Week 1)
1. Create new directory structure
2. Implement application factory pattern
3. Move configuration to `config.py`
4. Extract database models to `models.py`
5. Set up Flask extensions in `extensions.py`

### Phase 2: Service Layer (Week 2)
1. Identify core business logic in `app.py`
2. Extract to service classes in `/app/services/`
3. Start with simpler modules (market breadth, watchlist)
4. Keep Flask routes in `app.py` temporarily

### Phase 3: API Layer (Week 3)
1. Create `/app/api/` directory with blueprints
2. Move route handlers to appropriate API modules
3. Update route handlers to call service layer
4. Implement error handling decorators

### Phase 4: NLP & Utilities (Week 4)
1. Extract NLP logic to `nlp_service.py` (building on our recent work)
2. Move helper functions to `/app/utils/`
3. Create constants file for magic numbers/strings
4. Implement cross-cutting concerns (logging, caching)

### Phase 5: Testing & Cleanup (Week 5)
1. Write unit tests for service layer
2. Update integration tests to use new structure
3. Remove dead code from original `app.py`
4. Performance testing and optimization
5. Documentation updates

## Benefits of This Approach

1. **Improved Readability**: Each file has a single, clear purpose
2. **Easier Testing**: Services can be tested in isolation without Flask context
3. **Better Collaboration**: Teams can work on different features simultaneously
4. **Enhanced Maintainability**: Changes to one feature don't affect others
5. **Scalability**: New features follow established patterns
6. **Reusability**: Service layer can be used by different interfaces (web, CLI, etc.)
7. **Clear Dependencies**: Explicit imports show what each module needs

## Potential Challenges & Mitigations

### Challenge: Circular Imports
- **Mitigation**: Use dependency injection, import inside functions when needed, leverage Flask's application context

### Challenge: Performance Overhead
- **Mitigation**: Profile critical paths, use caching where appropriate, keep lazy loading for heavy resources (like NLP models)

### Challenge: Data Transfer Objects
- **Mitigation**: Use simple dictionaries or dataclasses for service-to-API transfers; avoid over-engineering

### Challenge: State Management
- **Mitigation**: Use Flask extensions for shared state (db, cache), avoid global variables

### Challenge: Learning Curve
- **Mitigation**: Document patterns clearly, create examples, pair programming during transition

## Specific Recommendations for NLP Components

Based on our recent work on the Corporate Events NLP Enhancement:

1. **Lazy Loading**: Keep NLP model loading in the service class initializer to avoid startup delays
2. **Configuration Control**: Enable/disable NLP via environment variable (`NLP_MODELS_ENABLED`)
3. **Error Resilience**: Always have fallback to keyword-based classification
4. **Resource Management**: Consider implementing model unloading for long-running processes
5. **Metrics Collection**: Add logging for NLP vs fallback usage to monitor effectiveness
6. **Batch Processing**: Extend NLP service to handle multiple announcements efficiently

## Files to Create Immediately

1. `REFACTORING_PLAN.md` - Detailed migration steps with timelines
2. `/app/__init__.py` - Application factory
3. `config.py` - Configuration management
4. `/app/models.py` - Database models
5. `/app/extensions.py` - Flask extensions setup
6. `/app/services/nlp_service.py` - Building on our recent work
7. `/app/api/v1/__init__.py` - API blueprint registration
8. `/app/utils/helpers.py` - Moving existing helper functions

## Conclusion

This refactoring will transform the application from a monolithic script to a maintainable, scalable Flask application following industry best practices. The key is to proceed incrementally, ensuring each step delivers value while maintaining backward compatibility. The NLP service we began refactoring serves as an excellent model for how other components should be structured.

Remember: The goal isn't perfection in the first iteration, but establishing a clean foundation that makes future development faster and less error-prone.