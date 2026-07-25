"""
Flask extensions initialization.
"""
from flask import g
from flask_sqlalchemy import SQLAlchemy
from . import database
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

# Initialize SQLAlchemy
db = SQLAlchemy()

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

def init_extensions(app):
    """Initialize database connection handling."""
    # Initialize SQLAlchemy
    db.init_app(app)

    # Initialize raw SQLite database connection handling (for backward compatibility)
    app.teardown_appcontext(database.close_db)

    # We don't have other extensions to initialize for now.
    # If you have other extensions (like login, mail, etc.), initialize them here.
    pass