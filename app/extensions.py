"""
Flask extensions initialization.
"""
from flask import g
from flask_sqlalchemy import SQLAlchemy
from . import database

# Initialize SQLAlchemy
db = SQLAlchemy()

def init_extensions(app):
    """Initialize database connection handling."""
    # Initialize SQLAlchemy
    db.init_app(app)

    # Initialize raw SQLite database connection handling (for backward compatibility)
    app.teardown_appcontext(database.close_db)

    # We don't have other extensions to initialize for now.
    # If you have other extensions (like login, mail, etc.), initialize them here.
    pass