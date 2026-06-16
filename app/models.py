from .extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Association table for many-to-many relationships if needed
# Example: watchlist_item_tags = db.Table('watchlist_item_tags',
#     db.Column('item_id', db.Integer, db.ForeignKey('watchlist_items.id')),
#     db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'))
# )

class BaseModel(db.Model):
    """Abstract base model."""
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def save(self):
        db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def to_dict(self):
        """Convert model instance to dictionary."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class User(BaseModel):
    """User model for authentication."""
    __tablename__ = 'users'
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
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    # Relationship
    items = db.relationship('WatchlistItem', backref='section', lazy='dynamic',
                            cascade='all, delete-orphan')

    def __repr__(self):
        return f'<WatchlistSection {self.name}>'


class WatchlistItem(BaseModel):
    """Individual stock/watchlist item."""
    __tablename__ = 'watchlist_items'
    ticker = db.Column(db.String(20), nullable=False, index=True)
    exchange = db.Column(db.String(10), default='NSE')
    name = db.Column(db.String(200))
    sector = db.Column(db.String(100))
    # Additional fields for technical/fundamental data
    # These can be extended as needed
    section_id = db.Column(db.Integer, db.ForeignKey('watchlist_sections.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<WatchlistItem {self.ticker}>'


# Example: Trade journal model
class TradeJournal(BaseModel):
    """Trade journal entries."""
    __tablename__ = 'trade_journal'
    ticker = db.Column(db.String(20), nullable=False)
    trade_type = db.Column(db.String(10))  # BUY/SELL
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    entry_date = db.Column(db.DateTime)
    exit_date = db.Column(db.DateTime, nullable=True)
    pnl = db.Column(db.Float)
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<TradeJournal {self.ticker} {self.trade_type}>'


# Add other models as needed from existing schema (e.g., IPO, News, Alerts, etc.)
# This initial version focuses on core watchlist functionality.