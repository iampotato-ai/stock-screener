import pytest
import os
import sys
import time
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
    # 3 seconds is plenty when debug reloading and background tasks are disabled
    time.sleep(3)
    
    yield
    
    proc.terminate()
    proc.wait()
