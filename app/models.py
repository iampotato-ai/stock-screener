from .extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Association table for many-to-many relationships if needed
# Example: watchlist_item_tags = db.Table('watchlist_item_tags',
#     db.Column('item_id', db.Integer, db.ForeignKey('watchlist_items.id')),
#     db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'))
# )

class BaseModel(db.Model):
    """Abstract base model with serialization and helper utilities."""
    __abstract__ = True

    def save(self):
        db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def to_dict(self):
        """Convert model instance to dictionary, serializing date/time fields."""
        res = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for k, v in res.items():
            if hasattr(v, 'strftime'):
                if hasattr(v, 'hour') and hasattr(v, 'month'): # datetime
                    res[k] = v.strftime('%Y-%m-%d %H:%M:%S')
                elif hasattr(v, 'hour'): # time
                    res[k] = v.strftime('%H:%M:%S')
                else: # date
                    res[k] = v.strftime('%Y-%m-%d')
        return res


class User(BaseModel):
    """User model for authentication."""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128))
    # Add other fields as needed

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class WatchlistSection(BaseModel):
    """Watchlist sections (e.g., 'Long Term', 'Intraday')."""
    __tablename__ = 'watchlist_sections'
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.Integer, default=0)
    # Relationship
    items = db.relationship('WatchlistItem', backref='section', lazy='dynamic',
                            cascade='all, delete-orphan')

    def __repr__(self):
        return f'<WatchlistSection {self.name}>'


class WatchlistItem(BaseModel):
    """Individual stock/watchlist item."""
    __tablename__ = 'watchlist_items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    section_id = db.Column(db.String(100), db.ForeignKey('watchlist_sections.id'))
    ticker = db.Column(db.String(20), nullable=False)
    position = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<WatchlistItem {self.ticker}>'


# Example: Trade journal model
class TradeJournal(BaseModel):
    """Trade journal entries."""
    __tablename__ = 'trade_journal'
    id = db.Column(db.String(100), primary_key=True)
    ticker = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    setupLabel = db.Column(db.String(100), nullable=False)
    swingband = db.Column(db.String(100), nullable=False)
    entry = db.Column(db.Float, nullable=False)
    stop = db.Column(db.Float, nullable=False)
    target1 = db.Column(db.Float, nullable=False)
    target2 = db.Column(db.Float, nullable=False)
    target3 = db.Column(db.Float, nullable=False)
    riskAmount = db.Column(db.Float, nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    exitPrice = db.Column(db.Float)
    exitDate = db.Column(db.String(20))
    pnl = db.Column(db.Float)
    rAchieved = db.Column(db.Float)
    notes = db.Column(db.Text)

    def __repr__(self):
        return f'<TradeJournal {self.ticker}>'


# Add other models as needed from existing schema (e.g., IPO, News, Alerts, etc.)
# This initial version focuses on core watchlist functionality.


class BreadthHistory(BaseModel):
    """Market breadth history data."""
    __tablename__ = 'breadth_history'
    date = db.Column(db.Date, primary_key=True)  # Using Date since it's the primary key
    time = db.Column(db.Time)
    advances = db.Column(db.Integer)
    declines = db.Column(db.Integer)
    unchanged = db.Column(db.Integer)
    pct_sma21 = db.Column(db.Float)
    pct_sma50 = db.Column(db.Float)
    pct_52high = db.Column(db.Float)
    avg_recommend = db.Column(db.Float)
    regime_score = db.Column(db.Integer)
    regime_band = db.Column(db.String(50))

    def to_dict(self):
        """Convert model instance to dictionary with frontend expected camelCase keys."""
        # Get baseline serialization which formats Date and Time objects to strings
        base_dict = super().to_dict()
        return {
            'date': base_dict.get('date'),
            'time': base_dict.get('time'),
            'advances': self.advances,
            'declines': self.declines,
            'unchanged': self.unchanged,
            'pctAboveSMA21': self.pct_sma21,
            'pctAboveSMA50': self.pct_sma50,
            'pctNear52High': self.pct_52high,
            'regimeScore': self.regime_score,
            'regimeBand': self.regime_band,
            'avgRecommend': self.avg_recommend
        }


class KronosForecast(BaseModel):
    """Kronos forecast predictions."""
    __tablename__ = 'kronos_forecasts'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ticker = db.Column(db.String(20), nullable=False, index=True)
    generated_at = db.Column(db.DateTime, nullable=False)
    pred_len = db.Column(db.Integer, nullable=False)
    forecast_json = db.Column(db.JSON, nullable=False)  # Stores JSON forecast data
    last_close = db.Column(db.Float, nullable=False)
    model_type = db.Column(db.String(50), nullable=False, default='kronos')


class RrgHistory(BaseModel):
    """Relative Rotation Graph history."""
    __tablename__ = 'rrg_history'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    week = db.Column(db.String(20), nullable=False)
    sector = db.Column(db.String(100), nullable=False)
    jdk_rs = db.Column(db.Float, nullable=False)
    jdk_rs_momentum = db.Column(db.Float, nullable=False)
    score = db.Column(db.Integer)
    quadrant = db.Column(db.String(20))
    snapped_at = db.Column(db.DateTime, nullable=False)

    # Unique constraint
    __table_args__ = (db.UniqueConstraint('week', 'sector', name='_week_sector_uc'),)


class PatternCache(BaseModel):
    """Technical pattern cache."""
    __tablename__ = 'pattern_cache'
    ticker = db.Column(db.String(20), primary_key=True)
    generated_at = db.Column(db.DateTime, nullable=False)
    pattern_name = db.Column(db.String(100))
    pattern_grade = db.Column(db.String(20))
    pattern_desc = db.Column(db.Text)
    candlestick_json = db.Column(db.JSON)
    pattern_bias = db.Column(db.Float, default=0.0)
    max_down_vol_10 = db.Column(db.Float)
    volume_sma_50 = db.Column(db.Float)


class PatternSignal(BaseModel):
    """Technical pattern signals."""
    __tablename__ = 'pattern_signals'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ticker = db.Column(db.String(20), nullable=False, index=True)
    timeframe = db.Column(db.String(10), nullable=False, default='D')
    signal_type = db.Column(db.String(20), nullable=False)  # 'candle' | 'chart'
    pattern = db.Column(db.String(100), nullable=False)
    direction = db.Column(db.Integer, nullable=False)  # 100 bullish, -100 bearish
    confidence = db.Column(db.Float)  # 0.0-1.0 (chart patterns only)
    description = db.Column(db.Text)
    detected_at = db.Column(db.DateTime, nullable=False)
    bar_date = db.Column(db.Date)  # date of the last bar in the signal

    # Index for fast per-ticker lookups
    __table_args__ = (db.Index('idx_pattern_signals_ticker', 'ticker', 'detected_at'),)


class IpoListing(BaseModel):
    """IPO listings."""
    __tablename__ = 'ipo_listings'
    ticker = db.Column(db.String(20), primary_key=True)
    company_name = db.Column(db.String(200), nullable=False)
    listing_date = db.Column(db.Date, nullable=False)
    issue_price = db.Column(db.Float)
    listing_open = db.Column(db.Float)
    listing_close = db.Column(db.Float)
    exchange = db.Column(db.String(10), default='NSE')
    sector = db.Column(db.String(100))
    issue_size_cr = db.Column(db.Float)
    lot_size = db.Column(db.Integer)
    gmp_at_listing = db.Column(db.Float)
    added_at = db.Column(db.DateTime, default=db.func.now())


class IpoMetricsCache(BaseModel):
    """Cached IPO metrics for performance."""
    __tablename__ = 'ipo_metrics_cache'
    ticker = db.Column(db.String(20), primary_key=True)
    company_name = db.Column(db.String(200), nullable=False)
    listing_date = db.Column(db.Date, nullable=False)
    exchange = db.Column(db.String(10), nullable=False)
    sector = db.Column(db.String(100))
    issue_price = db.Column(db.Float)
    listing_open = db.Column(db.Float)
    listing_close = db.Column(db.Float)
    issue_size_cr = db.Column(db.Float)
    lot_size = db.Column(db.Integer)
    gmp_at_listing = db.Column(db.Float)
    listing_gain_pct = db.Column(db.Float)
    current_vs_issue_pct = db.Column(db.Float)
    current_vs_listing_pct = db.Column(db.Float)
    days_since_listing = db.Column(db.Integer)
    rvol_ratio = db.Column(db.Float)
    above_listing_high = db.Column(db.Integer)
    drawdown_from_ath = db.Column(db.Float)
    swing_score = db.Column(db.Integer)
    pattern_name = db.Column(db.String(100))
    momentum_phase = db.Column(db.String(20))
    current_price = db.Column(db.Float)
    volume = db.Column(db.Float)
    change_pct = db.Column(db.Float)
    day_low = db.Column(db.Float)
    day_high = db.Column(db.Float)
    is_blue_bar = db.Column(db.Integer, default=0)
    is_green_bar = db.Column(db.Integer, default=0)
    is_orange_bar = db.Column(db.Integer, default=0)
    cached_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (db.Index('idx_ipo_metrics_phase', 'momentum_phase'),)


class DailyBar(BaseModel):
    """Daily stock price/volume data."""
    __tablename__ = 'daily_bars'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False)
    exchange = db.Column(db.String(10), nullable=False)
    trade_date = db.Column(db.Date, nullable=False)
    open = db.Column(db.Float)
    high = db.Column(db.Float)
    low = db.Column(db.Float)
    close = db.Column(db.Float)
    volume = db.Column(db.Integer)
    delivery_qty = db.Column(db.Integer)
    delivery_pct = db.Column(db.Float)
    turnover = db.Column(db.Float)
    prev_close = db.Column(db.Float)
    gap_pct = db.Column(db.Float)
    close_loc = db.Column(db.Float)
    atr_14 = db.Column(db.Float)
    rel_volume_20 = db.Column(db.Float)
    rel_volume_50 = db.Column(db.Float)
    price_change_pct = db.Column(db.Float)
    intraday_range_pct = db.Column(db.Float)

    __table_args__ = (
        db.UniqueConstraint('symbol', 'exchange', 'trade_date', name='_symbol_exchange_date_uc'),
        db.Index('idx_daily_bars_symbol_date', 'symbol', 'trade_date'),
        db.Index('idx_daily_bars_date', 'trade_date'),
    )


class Fundamental(BaseModel):
    """Company fundamental data."""
    __tablename__ = 'fundamentals'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False)
    exchange = db.Column(db.String(10), nullable=False)
    result_date = db.Column(db.Date, nullable=False)
    quarter = db.Column(db.String(20))
    revenue = db.Column(db.Float)
    revenue_yoy_pct = db.Column(db.Float)
    revenue_qoq_pct = db.Column(db.Float)
    net_profit = db.Column(db.Float)
    net_profit_yoy_pct = db.Column(db.Float)
    ebitda = db.Column(db.Float)
    ebitda_margin = db.Column(db.Float)
    eps = db.Column(db.Float)
    eps_yoy_pct = db.Column(db.Float)
    guidance_text = db.Column(db.Text)
    surprise_type = db.Column(db.String(50))
    consecutive_quarters_growth = db.Column(db.Integer)
    source = db.Column(db.String(100))

    __table_args__ = (db.UniqueConstraint('symbol', 'exchange', 'quarter', name='_symbol_exchange_quarter_uc'),)


class CorporateEvent(BaseModel):
    """Corporate events (earnings, results, etc.)."""
    __tablename__ = 'corporate_events'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False)
    exchange = db.Column(db.String(10), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    event_type = db.Column(db.String(100))
    headline = db.Column(db.Text)
    sentiment = db.Column(db.Integer)
    catalyst_score = db.Column(db.Float)
    source = db.Column(db.String(100))
    raw_url = db.Column(db.Text)

    # NLP Enhancement fields
    nlp_sentiment_score = db.Column(db.Float)
    nlp_category = db.Column(db.String(100))
    summary = db.Column(db.Text)
    impact_magnitude = db.Column(db.Float)

    __table_args__ = (db.Index('idx_corp_events_symbol_date', 'symbol', 'event_date'),)


class EpFeature(BaseModel):
    """Episodic Pivot features."""
    __tablename__ = 'ep_features'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False)
    exchange = db.Column(db.String(10), nullable=False)
    feature_date = db.Column(db.Date, nullable=False)
    perf_3m = db.Column(db.Float)
    perf_6m = db.Column(db.Float)
    range_60d_pct = db.Column(db.Float)
    avg_vol_rank = db.Column(db.Float)
    neglect_score = db.Column(db.Float)
    has_result = db.Column(db.Integer, default=0)
    revenue_growth = db.Column(db.Float)
    profit_growth = db.Column(db.Float)
    has_corp_event = db.Column(db.Integer, default=0)
    event_type = db.Column(db.String(100))
    catalyst_score = db.Column(db.Float)
    gap_pct = db.Column(db.Float)
    rel_volume = db.Column(db.Float)
    close_loc = db.Column(db.Float)
    repricing_score = db.Column(db.Float)
    ep_score = db.Column(db.Float)
    ep_type = db.Column(db.String(50))
    confidence = db.Column(db.String(20))
    market_cap_cr = db.Column(db.Float)
    avg_turnover_cr = db.Column(db.Float)
    float_days = db.Column(db.Float)
    price_change_pct = db.Column(db.Float)

    __table_args__ = (
        db.UniqueConstraint('symbol', 'exchange', 'feature_date', name='_symbol_exchange_feature_date_uc'),
        db.Index('idx_ep_features_date', 'feature_date'),
        db.Index('idx_ep_features_score', 'feature_date', 'ep_score'),
        db.Index('idx_ep_features_symbol_date', 'symbol', 'feature_date'),
    )


class EpWatchlist(BaseModel):
    """Episodic Pivot watchlist."""
    __tablename__ = 'ep_watchlist'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False)
    exchange = db.Column(db.String(10), nullable=False)
    catalyst_date = db.Column(db.Date, nullable=False)
    ep_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='ACTIVE')
    trigger_type = db.Column(db.String(50))
    entry_price = db.Column(db.Float)
    stop_price = db.Column(db.Float)
    target_price = db.Column(db.Float)
    entry_date = db.Column(db.Date)
    days_on_watch = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    ep_score = db.Column(db.Float)
    catalyst_close = db.Column(db.Float)
    last_incremented_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (db.Index('idx_ep_watchlist_symbol', 'symbol'),)


class SugarBaby(BaseModel):
    """Sugar Babies (high momentum stocks)."""
    __tablename__ = 'sugar_babies'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False, unique=True)
    exchange = db.Column(db.String(10), nullable=False)
    added_date = db.Column(db.Date)
    avg_burst_pct = db.Column(db.Float)
    avg_burst_days = db.Column(db.Float)
    episode_count = db.Column(db.Integer)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Integer, default=1)


class ScanHistory(BaseModel):
    """Scan history tracking."""
    __tablename__ = 'scan_history'
    date = db.Column(db.Date, primary_key=True)
    ticker = db.Column(db.String(20), primary_key=True)


class ScanPriceLog(BaseModel):
    """Scan price log with detailed price information."""
    __tablename__ = 'scan_price_log'
    date = db.Column(db.Date, nullable=False)
    ticker = db.Column(db.String(20), nullable=False)
    close = db.Column(db.Float)
    swingband = db.Column(db.String(20))
    setupLabel = db.Column(db.String(100))

    __table_args__ = (db.PrimaryKeyConstraint('date', 'ticker', name='_date_ticker_pk'),)


class MomentumScore(BaseModel):
    """Model for storing daily Momentum Confidence Scores for stocks."""
    __tablename__ = 'momentum_scores'

    # Composite primary key: one score per stock per exchange per date
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    exchange = db.Column(db.String(10), nullable=False, default='NSE', index=True)
    date = db.Column(db.Date, nullable=False, index=True)

    # Total score (0-100)
    total_score = db.Column(db.Integer, nullable=False)

    # Pillar scores
    technical_score = db.Column(db.Integer, nullable=False)  # 0-30
    fundamental_score = db.Column(db.Integer, nullable=False)  # 0-25
    momentum_score = db.Column(db.Integer, nullable=False)  # 0-20
    institutional_score = db.Column(db.Integer, nullable=False)  # 0-15
    risk_liquidity_score = db.Column(db.Integer, nullable=False)  # 0-10

    # Badges (stored as JSON array of strings)
    badges = db.Column(db.JSON, nullable=False)

    # Calculation timestamp
    calculated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Unique constraint to prevent duplicate scores for same stock/date
    __table_args__ = (
        db.UniqueConstraint('symbol', 'exchange', 'date', name='_symbol_exchange_date_uc'),
        db.Index('idx_momentum_scores_date', 'date'),
        db.Index('idx_momentum_scores_score', 'total_score'),
    )

    def to_dict(self):
        """Convert model instance to dictionary."""
        # Compute swing_score from stored pillars — no DB migration needed.
        # Formula: Technical×(45/30) + Momentum×(45/20) + Risk×(10/10), capped 100.
        swing_score = None
        if (self.technical_score is not None and
                self.momentum_score is not None and
                self.risk_liquidity_score is not None):
            swing_score = min(100, round(
                self.technical_score * (45.0 / 30.0) +
                self.momentum_score  * (45.0 / 20.0) +
                self.risk_liquidity_score * (10.0 / 10.0)
            ))

        res = {
            'id': self.id,
            'symbol': self.symbol,
            'exchange': self.exchange,
            'date': self.date.isoformat() if self.date else None,
            'total_score': self.total_score,
            'swing_score': swing_score,
            'technical_score': self.technical_score,
            'fundamental_score': self.fundamental_score,
            'momentum_score': self.momentum_score,
            'institutional_score': self.institutional_score,
            'risk_liquidity_score': self.risk_liquidity_score,
            'badges': self.badges,
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None
        }
        return res