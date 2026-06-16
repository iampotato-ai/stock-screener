"""
Database helper functions for the Stock Screener application.
Provides raw SQLite3 connection handling via Flask's g object.
"""
import sqlite3
from flask import g, current_app


def get_db():
    """Get a database connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    """Close the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()