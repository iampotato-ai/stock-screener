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

    # Pagination
    ITEMS_PER_PAGE = int(os.environ.get('ITEMS_PER_PAGE', '50'))

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
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    DATABASE = ':memory:'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}