import os
import sys
import sqlite3
import sqlite3.dbapi2
import tempfile
import pytest
from flask import Flask

# Prevent background schedulers and task runners from spawning during test collection
os.environ.setdefault('PYTEST_CURRENT_TEST', 'conftest_setup')

# Global patch of sqlite3.connect to ensure SQLAlchemy connection redirect works
# even if app/SQLAlchemy was initialized before the individual test module imports.
if not hasattr(sqlite3, "__original_connect__"):
    sqlite3.__original_connect__ = sqlite3.connect
orig_connect = sqlite3.__original_connect__

def global_mock_connect(database, *args, **kwargs):
    if database and "scan_history.db" in database:
        current_test = os.environ.get('PYTEST_CURRENT_TEST')
        if current_test:
            module_path = current_test.split('::')[0]
            base = os.path.basename(module_path)
            name = os.path.splitext(base)[0]
            for mod_name, mod in list(sys.modules.items()):
                if mod_name == name or mod_name.endswith('.' + name):
                    if hasattr(mod, 'db_path'):
                        val = getattr(mod, 'db_path')
                        if val:
                            return orig_connect(val, *args, **kwargs)
                    if hasattr(mod, 'db_file'):
                        val = getattr(mod, 'db_file')
                        if val:
                            return orig_connect(val, *args, **kwargs)
    return orig_connect(database, *args, **kwargs)

sqlite3.connect = global_mock_connect
sqlite3.dbapi2.connect = global_mock_connect

@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)

@pytest.fixture
def initialized_db(temp_db_path):
    """Initialize the database standalone with the temporary file."""
    from app.database import init_db_standalone
    init_db_standalone(temp_db_path)

@pytest.fixture
def flask_app(monkeypatch, temp_db_path):
    """Create a Flask app configured for testing with the temporary database.
    Yields the app instance; tests can utilize the app context as needed.
    """
    monkeypatch.setenv('DATABASE', temp_db_path)
    from app import create_app
    app = create_app('pytest')
    
    # Initialize database within app context
    with app.app_context():
        from app.database import init_db_app
        init_db_app()
        
    yield app
