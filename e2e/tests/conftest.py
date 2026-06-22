import pytest
import os
import sys
import time
import urllib.request
from subprocess import Popen
from pathlib import Path

@pytest.fixture(scope="session", autouse=True)
def run_server():
    """Start the Flask development server once for the entire test session.
    Disables debug mode and background scheduler tasks for stability and speed.
    """
    env = os.environ.copy()
    env["FLASK_DEBUG"] = "False"
    env["ENABLE_BACKGROUND_TASKS"] = "False"
    
    proc = Popen([sys.executable, "run.py"], env=env, cwd=Path.cwd())
    
    # Poll up to 20 times (every 500ms) until a successful response is received
    base_url = os.getenv("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:5000")
    success = False
    for _ in range(20):
        try:
            with urllib.request.urlopen(base_url, timeout=1.0) as response:
                if response.status == 200:
                    success = True
                    break
        except Exception:
            pass
        time.sleep(0.5)
        
    if not success:
        proc.terminate()
        proc.wait()
        raise RuntimeError(f"Flask server failed to start in time at {base_url}.")
    
    yield
    
    proc.terminate()
    proc.wait()

