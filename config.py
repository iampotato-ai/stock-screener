import os

basedir = os.path.abspath(os.path.dirname(__file__))

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

    # Feature flags
    ENABLE_BACKGROUND_TASKS = os.environ.get('ENABLE_BACKGROUND_TASKS', 'True').lower() == 'true'
    ENABLE_TELEGRAM_ALERTS = os.environ.get('ENABLE_TELEGRAM_ALERTS', 'True').lower() == 'true'
    ENABLE_NLP_ENRICHMENT = os.environ.get('ENABLE_NLP_ENRICHMENT', 'True').lower() == 'true'

    # Pagination
    ITEMS_PER_PAGE = int(os.environ.get('ITEMS_PER_PAGE', '50'))
    # EP Scoring Model configuration
    EP_MODEL_PATH = os.path.join(basedir, 'models', 'ep_scoring_model_latest.pkl')
    EP_CONFIDENCE_HIGH = float(os.environ.get('EP_CONFIDENCE_HIGH', '0.72'))
    EP_CONFIDENCE_MEDIUM = float(os.environ.get('EP_CONFIDENCE_MEDIUM', '0.55'))
    EP_MODEL_TRAIN_HOUR = int(os.environ.get('EP_MODEL_TRAIN_HOUR', '16'))
    EP_MODEL_TRAIN_MINUTE = int(os.environ.get('EP_MODEL_TRAIN_MINUTE', '0'))

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    # Development-specific settings
    ASSETS_DEBUG = True


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


class PytestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    DATABASE = ':memory:'
    ENABLE_BACKGROUND_TASKS = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'pytest': PytestConfig,
    'default': DevelopmentConfig
}