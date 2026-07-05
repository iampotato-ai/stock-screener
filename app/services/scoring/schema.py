"""
Stock data schema for Momentum Confidence Score analyzers.

This TypedDict is the single source of truth for field names consumed by
all five scoring analyzer modules (technical, fundamental, momentum,
institutional, risk).

Both the mock data generator in MomentumConfidenceScoreService and any
future real data-fetching layer MUST conform to this schema.
"""
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class StockDataSchema(TypedDict, total=False):
    """
    Schema for stock data dicts passed to scoring analyzers.
    All keys are optional (total=False); analyzers must use .get(key, default).
    """

    # --- Identity ---
    symbol: str
    exchange: str

    # --- Technical ---
    price: float                # Last traded price in INR
    ema_20: float               # 20-period EMA
    ema_50: float               # 50-period EMA
    ema_100: float              # 100-period EMA
    ema_200: float              # 200-period EMA
    rsi: float                  # RSI 0-100
    macd: float                 # MACD line value
    macd_signal: float          # MACD signal line
    adx: float                  # ADX 0-100
    supertrend: float           # Supertrend level in INR
    supertrend_direction: int   # 1 = uptrend, -1 = downtrend
    price_vs_52w_high: float    # price / 52w-high ratio (0.0-1.0)
    higher_highs: bool          # True if making higher highs
    higher_lows: bool           # True if making higher lows
    golden_cross: bool          # True if 50 EMA > 200 EMA

    # --- Fundamental ---
    revenue_growth_yoy: float    # YoY revenue growth as decimal (0.18 = 18%)
    profit_growth_yoy: float     # YoY net profit growth as decimal
    roe: float                   # Return on Equity as decimal
    roce: float                  # Return on Capital Employed as decimal
    debt_to_equity: float        # D/E ratio (lower is better)
    operating_margin: float      # Operating margin as decimal
    net_margin: float            # Net profit margin as decimal
    operating_cash_flow: float   # Operating cash flow in INR crores (positive = good)
    promoter_holding_pct: float  # Promoter holding 0-100%
    promoter_pledged_pct: float  # % of promoter holding that is pledged 0-100

    # --- Momentum ---
    relative_strength_rating: float  # RS percentile vs peers (0-100)
    volume_ratio: float               # Today volume / 30-day avg volume
    price_vs_52w_high_pct: float      # (price / 52w-high) * 100
    has_vcp_pattern: bool             # True if VCP pattern detected
    is_breakout: bool                 # True if recent breakout above resistance
    momentum_acceleration: float      # Rate-of-change acceleration percentage

    # --- Institutional ---
    mf_holding_change_pct: float        # % change in MF holdings (positive = buying)
    fii_net_buy_cr: float               # FII net buying in INR crores
    fii_holding_pct: float              # FII holding % of total shares
    promoter_buy_qty: int               # Shares bought by promoters
    promoter_holding_change_pct: float  # % change in promoter holding
    block_deal_count: int               # Number of block deals in period
    block_deal_buy_ratio: float         # Buy-side ratio of block deals (0.0-1.0)

    # --- Risk and Liquidity ---
    avg_daily_volume: int       # Average daily volume in shares
    market_cap_cr: float        # Market cap in INR crores
    bid_ask_spread_pct: float   # Bid-ask spread as % of price
    volatility_30d: float       # 30-day annualised volatility as decimal
    circuit_history: int        # Circuit hits in last year
    operator_risk: str          # 'low' | 'medium' | 'high'
