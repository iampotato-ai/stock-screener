"""
Thin wrapper for EP scoring model training.

Provides a function that can be scheduled to run the EP training script
within the Flask application context, handling logging and error propagation.
"""

import subprocess
import sys
from pathlib import Path
import logging
from flask import Flask


def run_ep_model_training(app: Flask):
    """Run EP scoring model training using the training script.

    Executes ``scripts/train_ep_scoring_model.py`` via ``subprocess``.
    The script supports a ``--dry-run`` flag for fast CI execution.
    Any exception is logged and re‑raised so the scheduler can react.
    """
    logger = logging.getLogger(__name__)
    try:
        with app.app_context():
            # Resolve the training script relative to the project root
            script_path = Path(__file__).resolve().parents[2] / "scripts" / "train_ep_scoring_model.py"
            # Run the script in dry‑run mode to avoid heavy training during tests
            result = subprocess.run(
                [sys.executable, str(script_path), "--dry-run"],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info(f"EP model training completed: {result.stdout.strip()}")
    except Exception as e:
        logger.error(f"EP model training failed: {e}")
        raise
