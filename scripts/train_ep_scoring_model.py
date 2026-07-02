"""
EP scoring model training script.

Loads EP features and price data, constructs training set, trains XGBoost classifier, and saves model.
"""

import os
import json
import sqlite3
import datetime
from pathlib import Path
import numpy as np
import joblib
from xgboost import XGBClassifier

def load_data_from_db(db_path: str):
    """Load ep_features and join with daily_bars to get target label.
    Label is 1 if price went up >= 40% in 5 trading days, else 0.
    """
    if not os.path.exists(db_path):
        print(f"[Model Training] Database path not found: {db_path}")
        return None, None
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ep_features'")
        if not cursor.fetchone():
            conn.close()
            print("[Model Training] Table 'ep_features' does not exist.")
            return None, None
            
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_bars'")
        if not cursor.fetchone():
            conn.close()
            print("[Model Training] Table 'daily_bars' does not exist.")
            return None, None
            
        # Read features
        cursor.execute("SELECT symbol, feature_date, neglect_score, catalyst_score, repricing_score, liquidity_ok, has_fundamentals FROM ep_features")
        features_rows = cursor.fetchall()
        
        # Read close prices
        cursor.execute("SELECT symbol, trade_date, close FROM daily_bars")
        price_rows = cursor.fetchall()
        
        conn.close()
    except Exception as e:
        print(f"[Model Training] Error reading from database: {e}")
        return None, None
        
    if not features_rows or not price_rows:
        print("[Model Training] Empty features or daily bars in database.")
        return None, None
        
    # Map price_rows for easy lookup: (symbol, date_str) -> close
    price_map = {}
    for r in price_rows:
        sym, dt, close = r
        if isinstance(dt, str):
            dt = dt.split()[0]
        price_map[(sym.upper(), dt)] = close

    # Get sorted list of trade dates per symbol to find "+5 trading days"
    sym_dates = {}
    for r in price_rows:
        sym, dt, _ = r
        if isinstance(dt, str):
            dt = dt.split()[0]
        sym_upper = sym.upper()
        if sym_upper not in sym_dates:
            sym_dates[sym_upper] = []
        sym_dates[sym_upper].append(dt)
        
    for sym in sym_dates:
        sym_dates[sym].sort()

    X = []
    y = []
    
    for row in features_rows:
        sym, feat_dt, neglect, catalyst, repricing, liq, fund = row
        if isinstance(feat_dt, str):
            feat_dt = feat_dt.split()[0]
        sym_upper = sym.upper()
        
        p0 = price_map.get((sym_upper, feat_dt))
        if p0 is None or p0 == 0:
            continue
            
        # Find 5 trading days later
        dates = sym_dates.get(sym_upper, [])
        try:
            idx = dates.index(feat_dt)
            if idx + 5 < len(dates):
                feat_dt_5 = dates[idx + 5]
                p5 = price_map.get((sym_upper, feat_dt_5))
            else:
                p5 = None
        except ValueError:
            p5 = None
            
        if p5 is None:
            continue
            
        pct_move = (p5 - p0) / p0
        label = 1 if pct_move >= 0.40 else 0
        
        X.append([
            float(neglect or 0.0),
            float(catalyst or 0.0),
            float(repricing or 0.0),
            1.0 if liq else 0.0,
            1.0 if fund else 0.0
        ])
        y.append(label)
        
    if len(X) < 10:
        print(f"[Model Training] Insufficient samples found in database: {len(X)}")
        return None, None
        
    print(f"[Model Training] Loaded {len(X)} samples from database.")
    return np.array(X), np.array(y)

def generate_synthetic_data(n_samples=100):
    """Generate high-quality synthetic training data based on the fallback scoring formula."""
    print(f"[Model Training] Generating {n_samples} synthetic training samples.")
    np.random.seed(42)
    neglect = np.random.uniform(0.1, 1.0, n_samples)
    catalyst = np.random.uniform(0.1, 1.0, n_samples)
    repricing = np.random.uniform(0.1, 1.0, n_samples)
    liq = np.random.choice([0.0, 1.0], n_samples, p=[0.1, 0.9])
    fund = np.random.choice([0.0, 1.0], n_samples, p=[0.2, 0.8])
    
    # Calculate a score based on the handcrafted logic
    raw = 0.25 * neglect + 0.35 * catalyst + 0.30 * repricing + 0.10 * fund
    # Adjust for liquidity
    raw += np.where(liq == 1.0, 0.0, -0.10)
    
    # Binary label: 1 if raw score >= 0.55, else 0
    # Add minor random noise to simulate real-world variance
    noise = np.random.normal(0, 0.05, n_samples)
    y = ((raw + noise) >= 0.58).astype(int)
    
    X = np.column_stack((neglect, catalyst, repricing, liq, fund))
    return X, y

def main(dry_run: bool = False):
    """Entry point for training.

    If dry_run is True, perform no training and exit with code 0.
    """
    if dry_run:
        print("[dry-run] Skipping EP model training.")
        return
        
    project_root = Path(__file__).resolve().parents[1]
    db_path = project_root / "scan_history.db"
    
    # Try to load real data
    X, y = load_data_from_db(str(db_path))
    
    # Fallback to synthetic if not available
    if X is None or y is None:
        X, y = generate_synthetic_data(100)
        
    # Fit the XGBoost classifier
    print("[Model Training] Training XGBoost classifier...")
    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        eval_metric='logloss',
        random_state=42
    )
    model.fit(X, y)
    
    # Ensure models dir exists
    model_dir = project_root / "models"
    os.makedirs(model_dir, exist_ok=True)
    
    model_path = model_dir / "ep_scoring_model_latest.pkl"
    manifest_path = model_dir / "ep_scoring_model_latest_manifest.json"
    
    # Save model and manifest
    print(f"[Model Training] Saving model to {model_path}...")
    joblib.dump(model, str(model_path))
    
    feature_order = [
        "neglect_score", "catalyst_score", "repricing_score",
        "liquidity_ok", "has_fundamentals"
    ]
    manifest = {
        "feature_order": feature_order,
        "version": "1.0",
        "trained_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "training_samples": len(X)
    }
    
    print(f"[Model Training] Saving manifest to {manifest_path}...")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        
    print("[Model Training] EP scoring model trained and saved successfully.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train EP scoring model")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry mode without training")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
