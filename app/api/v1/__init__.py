from flask import Blueprint

# Create API v1 blueprint
api_bp = Blueprint('api', __name__)

# Import route modules to register routes
from . import announcements  # noqa: F401
from . import watchlist  # noqa: F401
from . import ep_watchlist  # noqa: F401
from . import ep  # noqa: F401
from . import journal  # noqa: F401
from . import market_breadth  # noqa: F401
from . import alerts  # noqa: F401
from . import ipo  # noqa: F401
from . import news  # noqa: F401
# Add other modules as they are created
from . import screener  # noqa: F401
from . import legacy_routes  # noqa: F401