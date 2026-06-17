import os
import tempfile
import pytest
from flask import Flask

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
    """Create a Flask app configured for testing with the temporary database."""
    monkeypatch.setenv('DATABASE', temp_db_path)
    from app import create_app
    app = create_app('testing')
    # Initialize database within app context
    with app.app_context():
        from app.database import init_db_app
        init_db_app()
    yield app