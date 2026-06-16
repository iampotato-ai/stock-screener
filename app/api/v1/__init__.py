from flask import Blueprint

# Create API v1 blueprint
api_bp = Blueprint('api', __name__)

# Import route modules to register routes
from . import announcements  # noqa: F401
# Add other modules as they are created
# from . import screener
# from . import watchlist
# from . import journal
# from . import alerts
# from . import ipo
# from . import news
# from . import market_breadth