import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from config import config
from .extensions import db, init_extensions

logger = logging.getLogger(__name__)

def create_app(config_name=None, overrides=None):
    """Application factory pattern."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder='../templates',
        static_folder='../static'
    )
    app.config.from_object(config[config_name])
    
    if overrides:
        app.config.update(overrides)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize extensions
    init_extensions(app)

    # Initialize scheduler
    from .tasks.scheduler import init_scheduler
    scheduler = init_scheduler(app)
    if scheduler is not None:
        app.scheduler = scheduler
        logger.info("Background scheduler initialized and stored on app")
    else:
        logger.debug("Scheduler initialization skipped in reloader process")

    # Register blueprints
    from .api.v1 import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(api_bp, url_prefix='/api/v1', name='api_v1')

    # Register frontend root route
    from flask import render_template
    @app.route('/')
    def landing():
        return render_template('landing.html')

    @app.route('/dashboard')
    def index():
        return render_template('index.html')

    # Register error handlers
    register_error_handlers(app)

    # Configure logging for production
    if not app.debug and not app.testing:
        if app.config.get('LOG_TO_STDOUT'):
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO)
            app.logger.addHandler(stream_handler)
        else:
            if not os.path.exists('logs'):
                os.mkdir('logs')
            file_handler = RotatingFileHandler('logs/stock_screener.log',
                                               maxBytes=10240, backupCount=10)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s '
                '[in %(pathname)s:%(lineno)d]'))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('Stock Screener startup')

    return app

def register_error_handlers(app):
    """Register error handlers."""
    @app.errorhandler(400)
    def bad_request(e):
        return {'error': 'Bad request'}, 400

    @app.errorhandler(401)
    def unauthorized(e):
        return {'error': 'Unauthorized'}, 401

    @app.errorhandler(403)
    def forbidden(e):
        return {'error': 'Forbidden'}, 403

    @app.errorhandler(404)
    def not_found(e):
        return {'error': 'Not found'}, 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return {'error': 'Method not allowed'}, 405

    @app.errorhandler(500)
    def internal_server_error(e):
        return {'error': 'Internal server error'}, 500

    @app.errorhandler(503)
    def service_unavailable(e):
        return {'error': 'Service unavailable'}, 503

# Create a default app instance for backward compatibility with tests/scripts
app = create_app()

# Export compatibility functions at package level
from app.services.ep_service import (
    compute_neglect_score,
    compute_catalyst_score,
    compute_repricing_score,
    compute_ep_score,
    assign_ep_type,
    assign_confidence
)
from app.api.v1.legacy_routes import (
    init_db,
    classify_setup,
    ensemble_blend,
    compute_dynamic_weights,
    refresh_ep_screener,
    analyze_single_stock,
    refresh_ipo_metrics,
    seed_ipo_listings,
    merge_candlestick_fallback,
    send_telegram_alert,
    fetch_screener_fundamentals,
    fetch_nse_announcements,
    kronos_predict,
    prophet_predict,
    arima_predict,
    get_kronos_predictor,
    _compute_rolling_mape,
    _weight_ema_state,
    init_nlp_models,
    summarizer,
    event_classifier,
    sentiment_analyzer,
    classify_announcement,
    enhanced_classify_announcement
)
from app.utils.technical import (
    classify_technical_pattern,
    classify_momentum_phase,
    fetch_historical_prices
)