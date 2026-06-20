"""
Central constants for the Stock Screener application.
"""

# NLP model names (matching those used in the original app.py)
NLP_MODELS = {
    "sentiment": "ProsusAI/finbert",
    "summarizer": "sshleifer/distilbart-cnn-6-6",  # Fixed to match original
    "classifier": "typeform/distilbert-base-uncased-mnli"
}

# Fallback catalyst scores for standard categories (used when NLP is unavailable)
_FALLBACK_CATALYST_SCORES = {
    "cat-order-win": 0.65,
    "cat-capex": 0.45,
    "cat-governance": 0.55,
    "cat-regulatory": -0.70,
    "cat-results": 0.50,
    "cat-dividend": 0.40,
    "cat-acquisition": 0.60,
    "cat-unknown": 0.20,
}

# Base scores for event categories (used in NLP catalyst calculation)
EVENT_BASE_SCORES = {
    'financial results': 0.60,
    'dividend announcement': 0.40,
    'order win': 0.65,
    'acquisition': 0.55,
    'capex expansion': 0.45,
    'management change': 0.50,
    'regulatory issue': -0.30,
    'bonus issue': 0.25,
    'stock split': 0.20,
    'analyst upgrade': 0.40,
    'analyst downgrade': -0.40,
    'guidance raise': 0.50,
    'guidance cut': -0.70,
    'contract win': 0.60,
    'plant inauguration': 0.35
}

# NLP category mapping to standard categories
_NLP_CATEGORY_MAPPINGS = [
    (["dividend", "bonus issue", "stock split"], ("cat-dividend", "Dividend", "imp-earnings-st", "Earnings impact (short-term)")),
    (["financial results", "guidance raise", "guidance cut"], ("cat-results", "Results", "imp-earnings-st", "Earnings impact (short-term)")),
    (["order win", "contract win"], ("cat-order-win", "Order Win", "imp-order-book", "Order book impact")),
    (["acquisition"], ("cat-acquisition", "Acquisition", "imp-balance-sheet", "Balance sheet impact")),
    (["capex expansion", "plant inauguration"], ("cat-capex", "Capex", "imp-earnings-lt", "Earnings impact (long-term)")),
    (["regulatory issue"], ("cat-regulatory", "Regulatory", "imp-governance", "Governance signal")),
    (["management change"], ("cat-governance", "Governance", "imp-governance", "Governance signal"))
]

# NLP positive/negative keyword sets (used in keyword-based classifier)
_NLP_POSITIVE_WORDS = {"order", "win", "award", "profit", "growth", "expansion", "dividend",
                       "buyback", "bonus", "upgrade", "strong", "beat", "record", "approved"}
_NLP_NEGATIVE_WORDS = {"fraud", "penalty", "notice", "default", "npa", "loss", "decline",
                       "downgrade", "resign", "investigation", "concern", "miss", "cut"}