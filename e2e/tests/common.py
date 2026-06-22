import sys
import time
import os
def get_base_url():
    """Return the base URL for the Flask app, defaulting to localhost.
    Allows CI to override via PLAYWRIGHT_BASE_URL env var.
    """
    return os.getenv("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:5000")
from subprocess import Popen
from pathlib import Path

def start_flask_server():
    """Start the Flask development server in background and return the subprocess.
    Caller must terminate the process after the test.
    """
    proc = Popen([sys.executable, "run.py"], cwd=Path.cwd())
    # Allow time for server to bind sockets and finish initialisation.
    time.sleep(8)
    return proc
