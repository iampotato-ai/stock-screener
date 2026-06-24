import sys
sys.path.insert(0, 'C:/Users/91996/Documents/My Projects/stock-screener')

from app.database import execute_query

# Ensure the nse_symbols table exists (idempotent)
execute_query(
    '''
    CREATE TABLE IF NOT EXISTS nse_symbols (
        ticker TEXT PRIMARY KEY,
        market_cap_inr INTEGER NOT NULL,
        fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    ''',
    commit=True,
)
print('nse_symbols table ensured')
