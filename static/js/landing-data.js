/**
 * MomentumScan Landing Page Mock Data
 * Realistic Indian Equity market stats for active breakouts, swing setups, and breadth.
 */

const LANDING_DATA = {
  // Hero Terminal initial stocks (Live Breakouts Feed)
  heroStocks: [
    { ticker: 'HAL', name: 'Hindustan Aeronautics', ltp: 4684.50, change: 6.84, sector: 'Defense', tag: 'Breakout Ready', sparkline: 'M 0,25 Q 10,28 20,18 T 40,22 T 60,8 T 80,14 T 100,2' },
    { ticker: 'TATASTEEL', name: 'Tata Steel Ltd', ltp: 168.45, change: 4.23, sector: 'Metals', tag: 'Elite Swing', sparkline: 'M 0,20 Q 10,15 20,25 T 40,10 T 60,18 T 80,12 T 100,5' },
    { ticker: 'ZOMATO', name: 'Zomato Ltd', ltp: 204.15, change: 5.12, sector: 'Internet', tag: 'Sector Leader', sparkline: 'M 0,28 Q 10,22 20,24 T 40,18 T 60,12 T 80,15 T 100,4' },
    { ticker: 'PFC', name: 'Power Finance Corp', ltp: 488.90, change: 3.82, sector: 'Finance', tag: 'Strong Swing', sparkline: 'M 0,22 Q 10,24 20,18 T 40,16 T 60,20 T 80,10 T 100,6' },
    { ticker: 'BHEL', name: 'Bharat Heavy Electricals', ltp: 298.30, change: -1.24, sector: 'Capital Goods', tag: 'Pullback Support', sparkline: 'M 0,8 Q 10,12 20,6 T 40,15 T 60,18 T 80,22 T 100,25' },
    { ticker: 'CUMMINSIND', name: 'Cummins India Ltd', ltp: 3450.00, change: 4.75, sector: 'Industrial', tag: 'Breakout Ready', sparkline: 'M 0,26 Q 10,24 20,28 T 40,15 T 60,18 T 80,10 T 100,3' }
  ],

  // Terminal simulated live updates feed
  liveFeed: [
    { ticker: 'RELIANCE', name: 'Reliance Industries', ltp: 2914.80, change: 2.15, sector: 'Energy/Oil', tag: 'Regime Heavyweight', sparkline: 'M 0,22 Q 10,20 20,18 T 40,15 T 60,14 T 80,12 T 100,10' },
    { ticker: 'IRFC', name: 'Indian Railway Finance', ltp: 174.60, change: 8.52, sector: 'Railways', tag: 'Breakout Ready', sparkline: 'M 0,28 Q 10,26 20,20 T 40,18 T 60,10 T 80,12 T 100,2' },
    { ticker: 'HDFCBANK', name: 'HDFC Bank Ltd', ltp: 1642.30, change: 1.14, sector: 'Banking', tag: 'Sector Leader', sparkline: 'M 0,20 Q 10,22 20,21 T 40,19 T 60,18 T 80,17 T 100,15' },
    { ticker: 'COALINDIA', name: 'Coal India Ltd', ltp: 472.10, change: 3.65, sector: 'Mining/Energy', tag: 'Elite Swing', sparkline: 'M 0,24 Q 10,20 20,22 T 40,18 T 60,14 T 80,12 T 100,8' },
    { ticker: 'BEL', name: 'Bharat Electronics Ltd', ltp: 292.40, change: 5.74, sector: 'Defense', tag: 'Sector Leader', sparkline: 'M 0,26 Q 10,22 20,24 T 40,18 T 60,14 T 80,10 T 100,4' }
  ],

  // Metrics Data
  metrics: [
    { id: 'stocks-tracked', label: 'Stocks Tracked', value: 2145, suffix: '+', desc: 'NSE Equities filtered daily' },
    { id: 'scans-run', label: 'Daily Scans Run', value: 120, suffix: 'k+', desc: 'Real-time multi-criteria screens' },
    { id: 'breadth-engines', label: 'Breadth Engines', value: 8, suffix: '', desc: 'Advanced market internals metrics' },
    { id: 'refresh-speed', label: 'Refresh Speed', value: 0.8, suffix: 's', desc: 'Sub-second TradingView latency' }
  ],

  // Scan Gallery categories & datasets
  scans: {
    'elite-swing': [
      { ticker: 'TATASTEEL', ltp: 168.45, change: 4.23, rsi: 64.2, volSurge: '2.4x', setup: 'Low Vol Pullback', pat: 'Cup & Handle' },
      { ticker: 'RECLTD', ltp: 512.60, change: 3.14, rsi: 61.8, volSurge: '1.8x', setup: '21EMA Support', pat: 'Flag' },
      { ticker: 'COALINDIA', ltp: 472.10, change: 3.65, rsi: 67.5, volSurge: '3.1x', setup: 'VCP Tightening', pat: 'Contraction' },
      { ticker: 'PFC', ltp: 488.90, change: 3.82, rsi: 63.4, volSurge: '2.1x', setup: '10EMA Bounce', pat: 'Channel breakout' },
      { ticker: 'GMRINFRA', ltp: 88.40, change: 2.80, rsi: 59.2, volSurge: '1.5x', setup: 'Stage 2 Markup', pat: 'Flat Base' }
    ],
    'strong-swing': [
      { ticker: 'ZOMATO', ltp: 204.15, change: 5.12, rsi: 72.4, volSurge: '4.2x', setup: 'High Tight Flag', pat: 'Flag' },
      { ticker: 'DIXON', ltp: 11450.00, change: 4.88, rsi: 74.1, volSurge: '3.5x', setup: 'Momentum Continuation', pat: 'Ascending Triangle' },
      { ticker: 'TRENT', ltp: 4950.00, change: 3.45, rsi: 69.8, volSurge: '2.2x', setup: 'Rally on Volume', pat: 'Box Breakout' },
      { ticker: 'JIOFIN', ltp: 358.70, change: 4.12, rsi: 68.3, volSurge: '2.8x', setup: 'Moving Average Bounce', pat: 'Double Bottom' },
      { ticker: 'TATAELXSI', ltp: 7280.00, change: 3.75, rsi: 65.4, volSurge: '1.9x', setup: 'Base Escalation', pat: 'Cup Outline' }
    ],
    'breakout-ready': [
      { ticker: 'HAL', ltp: 4684.50, change: 6.84, rsi: 78.5, volSurge: '5.8x', setup: 'All-Time High Breakout', pat: 'VCP 3rd Loop' },
      { ticker: 'IRFC', ltp: 174.60, change: 8.52, rsi: 82.1, volSurge: '7.4x', setup: 'Multi-Week Consol Break', pat: 'Flat Base' },
      { ticker: 'BEL', ltp: 292.40, change: 5.74, rsi: 75.2, volSurge: '4.8x', setup: 'Volume Surge Breakout', pat: 'Rounding Bottom' },
      { ticker: 'HUDCO', ltp: 272.30, change: 6.24, rsi: 77.9, volSurge: '4.5x', setup: 'ATH Trigger Active', pat: 'Channel Escape' },
      { ticker: 'CUMMINSIND', ltp: 3450.00, change: 4.75, rsi: 71.3, volSurge: '3.1x', setup: 'Trendline Breakout', pat: 'Descending Wedge' }
    ],
    'sector-leaders': [
      { ticker: 'NIFTY_AUTO', ltp: 25140.20, change: 2.45, rsi: 71.8, volSurge: '1.4x', setup: 'Sector Momentum Peak', pat: 'Nifty Auto Leader' },
      { ticker: 'M&M', ltp: 2884.00, change: 3.84, rsi: 73.5, volSurge: '2.9x', setup: 'Industry Dominance', pat: 'ATH Breakout' },
      { ticker: 'TATAMOTORS', ltp: 984.60, change: 2.95, rsi: 66.8, volSurge: '2.1x', setup: 'Large Cap Leadership', pat: 'Flag Breakout' },
      { ticker: 'NIFTY_METAL', ltp: 9840.40, change: 1.82, rsi: 64.3, volSurge: '1.2x', setup: 'Commodity Uplift', pat: 'Nifty Metal Leader' },
      { ticker: 'HINDALCO', ltp: 678.90, change: 3.42, rsi: 67.2, volSurge: '2.5x', setup: 'Sector Beta Catalyst', pat: 'Base Breakout' }
    ],
    'rrg-rotation': [
      { ticker: 'COCHINSHIP', ltp: 2145.00, change: 7.42, rsi: 76.5, volSurge: '5.2x', setup: 'Quadrant: Leading (NE)', pat: 'Strong Momentum & Trend' },
      { ticker: 'MAZDOCK', ltp: 3950.40, change: 5.92, rsi: 74.3, volSurge: '4.1x', setup: 'Quadrant: Leading (NE)', pat: 'Trend Expansion' },
      { ticker: 'RVNL', ltp: 412.50, change: 8.14, rsi: 79.2, volSurge: '6.3x', setup: 'Quadrant: Leading (NE)', pat: 'Velocity Spike' },
      { ticker: 'BHARATFORG', ltp: 1684.00, change: 3.12, rsi: 65.8, volSurge: '2.0x', setup: 'Quadrant: Improving (SE)', pat: 'Trend Bottoming Out' },
      { ticker: 'TCS', ltp: 3845.00, change: 1.85, rsi: 54.2, volSurge: '1.1x', setup: 'Quadrant: Weakening (SW)', pat: 'Losing Relative Momentum' }
    ],
    'intraday-pro': [
      { ticker: 'MAHABANK', ltp: 68.40, change: 9.85, rsi: 81.2, volSurge: '9.4x', setup: 'Opening Range Breakout', pat: 'ORB 15-Min' },
      { ticker: 'ADANIPOWER', ltp: 724.50, change: 6.78, rsi: 78.4, volSurge: '6.2x', setup: 'High Volume Volatility Break', pat: 'Daily High Break' },
      { ticker: 'NBCC', ltp: 184.20, change: 5.42, rsi: 73.1, volSurge: '4.5x', setup: 'Intraday Consolidation Escape', pat: 'Flag 5-Min' },
      { ticker: 'GMRINFRA', ltp: 88.40, change: 2.80, rsi: 59.2, volSurge: '3.2x', setup: 'VWAP Bounce Trigger', pat: 'Pullback 3-Min' },
      { ticker: 'NHPC', ltp: 104.15, change: -2.45, rsi: 52.8, volSurge: '2.8x', setup: 'Mean Reversion Target', pat: 'Short Setup' }
    ]
  },

  // Market Intelligence Widgets Data
  intelligence: {
    regime: {
      score: 72,
      max: 100,
      band: 'Bullish Transition',
      emoji: '📈',
      color: '--accent-green',
      description: 'Breadth expanding, Nifty holding above 21/50 SMAs. Momentum-long setups favored.'
    },
    breadth: {
      advances: 1412,
      declines: 648,
      unchanged: 85,
      total: 2145,
      ratio: '2.18'
    },
    highsLows: {
      highs52w: 145,
      lows52w: 12,
      ratio: '12.1'
    },
    sectors: [
      { name: 'Nifty Defense / Aerospace', score: 92, status: 'Leading', color: '#10b981' },
      { name: 'Nifty PSU Banks', score: 84, status: 'Leading', color: '#10b981' },
      { name: 'Nifty Metal', score: 76, status: 'Improving', color: '#3b82f6' },
      { name: 'Nifty Auto', score: 71, status: 'Improving', color: '#3b82f6' },
      { name: 'Nifty IT', score: 48, status: 'Weakening', color: '#f59e0b' },
      { name: 'Nifty FMCG', score: 32, status: 'Lagging', color: '#ef4444' }
    ]
  }
};
