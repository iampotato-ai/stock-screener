import os
import json

basedir = os.path.abspath(os.path.dirname(__file__))

# Load .env file manually if it exists in the root directory
env_path = os.path.join(basedir, '.env')
if os.path.exists(env_path):
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    val_str = val.strip()
                    if len(val_str) >= 2 and val_str[0] == val_str[-1] and val_str[0] in ('"', "'"):
                        val_str = val_str[1:-1]
                    os.environ[key.strip()] = val_str
    except Exception as e:
        print(f"Warning: could not parse .env file: {e}")

# Momentum Confidence Score weights configuration
MOMENTUM_SCORE_WEIGHTS_FILE = os.path.join(basedir, 'momentum_score_weights.json')

def load_momentum_score_weights():
    """Load momentum score weights from JSON file, return defaults if file not found."""
    default_weights = {
        "technical_strength": 30,
        "fundamental_quality": 25,
        "momentum": 20,
        "institutional_confidence": 15,
        "risk_liquidity": 10
    }

    try:
        if os.path.exists(MOMENTUM_SCORE_WEIGHTS_FILE):
            with open(MOMENTUM_SCORE_WEIGHTS_FILE, 'r') as f:
                weights = json.load(f)
                # Validate that all required keys are present
                for key in default_weights:
                    if key not in weights:
                        weights[key] = default_weights[key]
                return weights
        else:
            # Create default weights file if it doesn't exist
            save_momentum_score_weights(default_weights)
            return default_weights
    except Exception as e:
        print(f"Warning: could not load momentum score weights: {e}")
        return default_weights

def save_momentum_score_weights(weights):
    """Save momentum score weights to JSON file."""
    try:
        with open(MOMENTUM_SCORE_WEIGHTS_FILE, 'w') as f:
            json.dump(weights, f, indent=2)
        return True
    except Exception as e:
        print(f"Warning: could not save momentum score weights: {e}")
        return False


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'scan_history.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DATABASE = os.environ.get('DATABASE') or 'scan_history.db'

    # NLP Configuration
    NLP_MODELS_ENABLED = os.environ.get('NLP_MODELS_ENABLED', 'True').lower() == 'true'
    NLP_MODEL_CACHE_SIZE = int(os.environ.get('NLP_MODEL_CACHE_SIZE', '3'))

    # External API configuration
    TRADINGVIEW_SCAN_URL = os.environ.get('TRADINGVIEW_SCAN_URL', 'https://scanner.tradingview.com/india/scan')
    NEWS_API_KEY = os.environ.get('NEWS_API_KEY')
    YAHOO_FINANCE_URL = os.environ.get('YAHOO_FINANCE_URL', 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_str}')
    GOOGLE_NEWS_URL = os.environ.get('GOOGLE_NEWS_URL', 'https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en')
    MARKETAUX_API_TOKEN = os.environ.get('MARKETAUX_API_TOKEN')
    NEWS_REFRESH_MINUTES = int(os.environ.get('NEWS_REFRESH_MINUTES', '60'))
    EVENT_REFRESH_MINUTES = int(os.environ.get('EVENT_REFRESH_MINUTES', '120'))

    # Feature flags
    ENABLE_BACKGROUND_TASKS = os.environ.get('ENABLE_BACKGROUND_TASKS', 'True').lower() == 'true'
    ENABLE_TELEGRAM_ALERTS = os.environ.get('ENABLE_TELEGRAM_ALERTS', 'True').lower() == 'true'
    ENABLE_NLP_ENRICHMENT = os.environ.get('ENABLE_NLP_ENRICHMENT', 'True').lower() == 'true'
    ENABLE_BULL_SNORT = os.environ.get('ENABLE_BULL_SNORT', 'False').lower() == 'true'
    # Momentum Confidence Score daily calculation job.
    # Defaults to False until real data fetching is wired up; set to 'true' in production
    # only when the scoring pipeline is connected to live stock data.
    ENABLE_MOMENTUM_SCORE_CALCULATION = os.environ.get('ENABLE_MOMENTUM_SCORE_CALCULATION', 'False').lower() == 'true'

    # Bull Snort Configuration defaults
    BULL_SNORT_VOL_AVG_PERIOD = int(os.environ.get('BULL_SNORT_VOL_AVG_PERIOD', '20'))
    BULL_SNORT_VOL_SURGE_MIN = float(os.environ.get('BULL_SNORT_VOL_SURGE_MIN', '3.0'))
    BULL_SNORT_CLOSE_POSITION_MIN = float(os.environ.get('BULL_SNORT_CLOSE_POSITION_MIN', '0.65'))
    BULL_SNORT_MIN_GAP_HISTORY = float(os.environ.get('BULL_SNORT_MIN_GAP_HISTORY', '10.0'))
    BULL_SNORT_MAX_CURRENT_GAP = float(os.environ.get('BULL_SNORT_MAX_CURRENT_GAP', '5.0'))

    # Pagination
    ITEMS_PER_PAGE = int(os.environ.get('ITEMS_PER_PAGE', '50'))
    # EP Scoring Model configuration
    EP_MODEL_PATH = os.path.join(basedir, 'models', 'ep_scoring_model_latest.pkl')
    EP_CONFIDENCE_HIGH = float(os.environ.get('EP_CONFIDENCE_HIGH', '0.45'))
    EP_CONFIDENCE_MEDIUM = float(os.environ.get('EP_CONFIDENCE_MEDIUM', '0.35'))
    EP_MODEL_TRAIN_HOUR = int(os.environ.get('EP_MODEL_TRAIN_HOUR', '16'))
    EP_MODEL_TRAIN_MINUTE = int(os.environ.get('EP_MODEL_TRAIN_MINUTE', '0'))
    # Daily Momentum Confidence Score calculation schedule (default 16:30 IST)
    DAILY_SCORE_BATCH_SIZE = int(os.environ.get('DAILY_SCORE_BATCH_SIZE', '200'))
    DAILY_SCORE_HOUR = int(os.environ.get('DAILY_SCORE_HOUR', '16'))
    DAILY_SCORE_MINUTE = int(os.environ.get('DAILY_SCORE_MINUTE', '30'))
    EP_MODEL_TRAINING_ENABLED = os.environ.get('EP_MODEL_TRAINING_ENABLED', 'False').lower() == 'true'
    EP_MODEL_TRAINING_DRY_RUN = os.environ.get('EP_MODEL_TRAINING_DRY_RUN', 'True').lower() == 'true'
    EP_STALENESS_DAYS = int(os.environ.get('EP_STALENESS_DAYS', '180'))

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    # Development-specific settings
    ASSETS_DEBUG = True
    EP_STALENESS_DAYS = 9999


class ProductionConfig(Config):
    DEBUG = False
    # Production logging, etc.
    # Example: log to stderr
    import logging
    from logging import StreamHandler
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        # Log errors to stderr
        file_handler = StreamHandler()
        file_handler.setLevel(logging.WARNING)
        app.logger.addHandler(file_handler)


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    DATABASE = os.environ.get('DATABASE') or ':memory:'
    ENABLE_BACKGROUND_TASKS = False
    ENABLE_MOMENTUM_SCORE_CALCULATION = False
    EP_STALENESS_DAYS = 9999


class PytestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    DATABASE = ':memory:'
    ENABLE_BACKGROUND_TASKS = False
    ENABLE_MOMENTUM_SCORE_CALCULATION = False
    EP_STALENESS_DAYS = 9999


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'pytest': PytestConfig,
    'default': DevelopmentConfig
}