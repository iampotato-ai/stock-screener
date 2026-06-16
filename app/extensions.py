"""
Flask extensions initialization.
Note: We are not using Flask-SQLAlchemy; instead, we use raw sqlite3 via app/database.py.
"""
from flask import g
from . import database

def init_extensions(app):
    """Initialize database connection handling."""
    app.teardown_appcontext(database.close_db)
    # We don't have other extensions to initialize for now.
    # If you have other extensions (like login, mail, etc.), initialize them here.
    pass