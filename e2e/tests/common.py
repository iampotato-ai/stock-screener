import os


def get_base_url():
    """Return the base URL for the Flask app, defaulting to localhost.
    Allows CI to override via PLAYWRIGHT_BASE_URL env var.
    """
    return os.getenv("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:5000")


def launch_browser(playwright_inst):
    """Launch the browser using environment configurations.
    Supports PLAYWRIGHT_HEADLESS (default True) and PLAYWRIGHT_CHANNEL (e.g. 'chrome').
    """
    headless_val = os.getenv("PLAYWRIGHT_HEADLESS", "True").lower() == "true"
    channel_val = os.getenv("PLAYWRIGHT_CHANNEL", None)
    
    kwargs = {"headless": headless_val}
    if channel_val:
        kwargs["channel"] = channel_val
        
    return playwright_inst.chromium.launch(**kwargs)

