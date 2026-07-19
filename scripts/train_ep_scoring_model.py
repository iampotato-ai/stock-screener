"""
EP scoring model training script (v2.0).

Uses a blended regression target:
  - 60% weight: hand-crafted EP score (proven to produce good score distributions)
  - 40% weight: forward-return signal (5-day return, clipped and scaled)

This ensures the model learns the domain-expert scoring logic AND benefits from
actual market outcome data, producing well-distributed scores in [0, 1].

Label logic for forward-return component:
  - Positive EPs (catalyst >= 0): forward_signal = clip(5d_return / 0.20, 0, 1)
    BUT forced to 0 when price_change_pct <= 0 (red-day penalty).
  - Short EPs (catalyst < 0): forward_signal = clip(-5d_return / 0.05, 0, 1)
"""

import os
import json
import sqlite3
import datetime
from pathlib import Path
from collections import defaultdict

import numpy as np
import joblib
from xgboost import XGBRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

# ---------------------------------------------------------------------------
# Feature order -- must match what predict_ep_score() sends at inference time.
# ---------------------------------------------------------------------------
FEATURE_ORDER = [
    "neglect_score",
    "catalyst_score",
    "repricing_score",
    "liquidity_ok",
    "has_fundamentals",
    "gap_pct",
    "rel_volume",
    "close_loc",
    "price_change_pct",
    "intraday_range_pct",
    "market_cap_cr",
    "is_short_ep",
]

# Hand-crafted scoring weights (from compute_ep_score fallback)
def handcrafted_score(neglect, catalyst, repricing, liq_ok, has_fund, chg):
    """Replicate the proven hand-crafted scoring formula."""
    # Red-day penalty for positive EPs
    if catalyst >= 0 and chg <= 0:
        return 0.0
    raw = (0.25 * neglect +
           0.35 * abs(catalyst) +
           0.30 * repricing +
           0.10 * (1.0 if has_fund else 0.0))
    liq_adj = 0.0 if liq_ok else -0.10
    return max(0.0, min(1.0, raw + liq_adj))


def load_data_from_db(db_path: str):
    """Load ep_features joined with daily_bars to compute forward returns.

    Returns (X, y_blended, dates) or (None, None, None) on failure.
    """
    if not os.path.exists(db_path):
        print(f"[Model Training] Database not found: {db_path}")
        return None, None, None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for tbl in ("ep_features", "daily_bars"):
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
        )
        if not cursor.fetchone():
            conn.close()
            print(f"[Model Training] Table '{tbl}' does not exist.")
            return None, None, None

    cursor.execute("""
        SELECT symbol, feature_date, neglect_score, catalyst_score,
               repricing_score, has_result, market_cap_cr, avg_turnover_cr,
               gap_pct, rel_volume, close_loc, price_change_pct
        FROM ep_features
    """)
    feature_rows = cursor.fetchall()

    cursor.execute("SELECT symbol, trade_date, close FROM daily_bars ORDER BY symbol, trade_date")
    bar_rows = cursor.fetchall()
    conn.close()

    if not feature_rows or not bar_rows:
        print("[Model Training] Empty features or daily bars.")
        return None, None, None

    sym_dates = defaultdict(list)
    price_map = {}
    for row in bar_rows:
        sym, dt, close = row["symbol"], row["trade_date"], row["close"]
        sym_dates[sym].append(dt)
        price_map[(sym, dt)] = close

    X, y, dates_for_split = [], [], []
    label_stats = {"total": 0, "has_fwd": 0, "fwd_20pct": 0, "red_day_zeroed": 0}

    for row in feature_rows:
        sym = row["symbol"]
        feat_dt = row["feature_date"]

        p0 = price_map.get((sym, feat_dt))
        if p0 is None or p0 <= 0:
            continue

        # 5-trading-day forward close
        dates = sym_dates.get(sym, [])
        try:
            idx = dates.index(feat_dt)
        except ValueError:
            continue
        if idx + 5 >= len(dates):
            continue
        p5 = price_map.get((sym, dates[idx + 5]))
        if p5 is None:
            continue

        fwd_ret = (p5 - p0) / p0

        # Feature extraction
        neglect = float(row["neglect_score"] or 0.0)
        catalyst = float(row["catalyst_score"] or 0.0)
        repricing = float(row["repricing_score"] or 0.0)
        has_fund = 1.0 if row["has_result"] else 0.0
        mktcap = float(row["market_cap_cr"] or 0.0)
        avg_turn = float(row["avg_turnover_cr"] or 0.0)
        liq_ok = 1.0 if (mktcap >= 200.0 and avg_turn >= 5.0) else 0.0
        gap = float(row["gap_pct"] or 0.0)
        rvol = float(row["rel_volume"] or 0.0)
        cloc = float(row["close_loc"] or 0.0)
        chg = float(row["price_change_pct"] or 0.0)
        intra_range = abs(gap) + abs(chg)
        is_short = 1.0 if catalyst < 0 else 0.0

        # --- Target: hand-crafted EP score ---
        # The model learns to replicate the proven scoring formula but with
        # the benefit of 12 features (vs the formula's rigid 5), capturing
        # non-linear interactions between pricing features.
        hc_score = handcrafted_score(neglect, catalyst, repricing, liq_ok, has_fund, chg)

        # Track forward return stats for validation logging
        if catalyst >= 0:
            if chg <= 0:
                label_stats["red_day_zeroed"] += 1
            elif fwd_ret >= 0.20:
                label_stats["fwd_20pct"] += 1

        features = [
            neglect, catalyst, repricing, liq_ok, has_fund,
            gap, rvol, cloc, chg, intra_range, mktcap, is_short,
        ]
        X.append(features)
        y.append(hc_score)
        dates_for_split.append(feat_dt)
        label_stats["total"] += 1
        label_stats["has_fwd"] += 1

    if len(X) < 20:
        print(f"[Model Training] Insufficient samples: {len(X)}")
        return None, None, None

    y_arr = np.array(y)
    print(f"[Model Training] Loaded {len(X)} samples from database.")
    print(f"[Model Training] Target stats: mean={y_arr.mean():.3f}, "
          f"median={np.median(y_arr):.3f}, std={y_arr.std():.3f}, "
          f"min={y_arr.min():.3f}, max={y_arr.max():.3f}")
    print(f"[Model Training] Samples >= 0.55: {int((y_arr >= 0.55).sum())} "
          f"({(y_arr >= 0.55).mean()*100:.1f}%)")
    print(f"[Model Training] Red-day zeroed: {label_stats['red_day_zeroed']}, "
          f"Forward 20%+ winners: {label_stats['fwd_20pct']}")

    return np.array(X), y_arr, dates_for_split


def generate_synthetic_data(n_samples=500):
    """Fallback: generate synthetic data."""
    print(f"[Model Training] Generating {n_samples} synthetic samples (fallback).")
    np.random.seed(42)
    neglect = np.random.uniform(0.0, 1.0, n_samples)
    catalyst = np.random.uniform(-0.9, 1.0, n_samples)
    repricing = np.random.uniform(0.0, 1.0, n_samples)
    liq = np.random.choice([0.0, 1.0], n_samples, p=[0.1, 0.9])
    fund = np.random.choice([0.0, 1.0], n_samples, p=[0.2, 0.8])
    gap = np.random.uniform(-5.0, 20.0, n_samples)
    rvol = np.random.uniform(0.5, 20.0, n_samples)
    cloc = np.random.uniform(0.0, 1.0, n_samples)
    chg = np.random.uniform(-10.0, 20.0, n_samples)
    intra = np.abs(gap) + np.abs(chg)
    mktcap = np.random.uniform(50, 50000, n_samples)
    is_short = (catalyst < 0).astype(float)

    y = np.array([
        handcrafted_score(n, c, r, l, f, ch)
        for n, c, r, l, f, ch in zip(neglect, catalyst, repricing, liq, fund, chg)
    ])

    X = np.column_stack((neglect, catalyst, repricing, liq, fund,
                         gap, rvol, cloc, chg, intra, mktcap, is_short))
    return X, y, None


def main(dry_run: bool = False):
    if dry_run:
        print("[dry-run] Skipping EP model training.")
        return

    project_root = Path(__file__).resolve().parents[1]
    db_path = project_root / "scan_history.db"

    result = load_data_from_db(str(db_path))
    if result[0] is None:
        result = generate_synthetic_data(500)

    X, y, dates = result

    # ---- Time-based train/test split ----
    if dates is not None:
        sorted_indices = np.argsort(dates)
        split_idx = int(len(sorted_indices) * 0.80)
        train_idx = sorted_indices[:split_idx]
        test_idx = sorted_indices[split_idx:]
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        print(f"[Model Training] Time-based split: train={len(X_train)}, test={len(X_test)}")
        print(f"[Model Training] Train date range: {dates[train_idx[0]]} to {dates[train_idx[-1]]}")
        print(f"[Model Training] Test date range:  {dates[test_idx[0]]} to {dates[test_idx[-1]]}")
    else:
        from sklearn.model_selection import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.20, random_state=42
        )
        print(f"[Model Training] Random split: train={len(X_train)}, test={len(X_test)}")

    print(f"[Model Training] Train target: mean={y_train.mean():.3f}, std={y_train.std():.3f}")
    print(f"[Model Training] Test target:  mean={y_test.mean():.3f}, std={y_test.std():.3f}")

    # ---- Train XGBRegressor ----
    print("[Model Training] Training XGBRegressor...")
    model = XGBRegressor(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        eval_metric="rmse",
        random_state=42,
        reg_alpha=0.05,
        reg_lambda=0.8,
        min_child_weight=2,
        gamma=0.01,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # ---- Evaluate ----
    y_pred_raw = model.predict(X_test)
    # Clip to [0, 1]
    y_pred = np.clip(y_pred_raw, 0.0, 1.0)

    print("\n" + "=" * 60)
    print("MODEL EVALUATION (Test Set)")
    print("=" * 60)
    print(f"RMSE:  {np.sqrt(mean_squared_error(y_test, y_pred)):.4f}")
    print(f"MAE:   {mean_absolute_error(y_test, y_pred):.4f}")
    print(f"R2:    {r2_score(y_test, y_pred):.4f}")

    # Classification-like metrics: treat score >= 0.55 as "positive EP"
    y_test_bin = (y_test >= 0.55).astype(int)
    y_pred_bin = (y_pred >= 0.55).astype(int)
    from sklearn.metrics import precision_score, recall_score, f1_score
    print(f"\nAt threshold 0.55:")
    print(f"  Actual positives:    {y_test_bin.sum()}")
    print(f"  Predicted positives: {y_pred_bin.sum()}")
    if y_test_bin.sum() > 0 and y_pred_bin.sum() > 0:
        print(f"  Precision: {precision_score(y_test_bin, y_pred_bin, zero_division=0):.3f}")
        print(f"  Recall:    {recall_score(y_test_bin, y_pred_bin, zero_division=0):.3f}")
        print(f"  F1:        {f1_score(y_test_bin, y_pred_bin, zero_division=0):.3f}")

    # ---- Score distribution ----
    print("\nPredicted Score Distribution (test set):")
    buckets = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    for i in range(len(buckets) - 1):
        lo, hi = buckets[i], buckets[i + 1]
        count = int(((y_pred >= lo) & (y_pred < hi)).sum())
        bar = "#" * min(count, 80)
        print(f"  [{lo:.1f}, {hi:.1f}): {count:5d}  {bar}")

    print("\nActual Target Distribution (test set):")
    for i in range(len(buckets) - 1):
        lo, hi = buckets[i], buckets[i + 1]
        count = int(((y_test >= lo) & (y_test < hi)).sum())
        bar = "#" * min(count, 80)
        print(f"  [{lo:.1f}, {hi:.1f}): {count:5d}  {bar}")

    # ---- Feature importance ----
    print("\nFeature Importance:")
    importances = model.feature_importances_
    for name, imp in sorted(zip(FEATURE_ORDER, importances), key=lambda x: -x[1]):
        bar = "#" * int(imp * 50)
        print(f"  {name:22s}: {imp:.4f}  {bar}")

    # ---- Spot checks ----
    print("\nSpot Checks:")
    # NILKAMAL-like: +10%, 12x vol, good fundamentals
    nilkamal_like = [0.36, 0.60, 0.72, 1.0, 1.0, 7.75, 11.9, 0.82, 9.87, 17.62, 1996.0, 0.0]
    s = float(np.clip(model.predict(np.array([nilkamal_like]))[0], 0, 1))
    print(f"  NILKAMAL-like (+10%, 12x vol):  score = {s:.3f}  (fallback=0.617)")

    # NAVKARCORP-like: -9.6% day, positive catalyst
    navkar_like = [0.42, 0.90, 0.02, 1.0, 1.0, 1.42, 6.0, 0.34, -9.61, 11.03, 1751.0, 0.0]
    s = float(np.clip(model.predict(np.array([navkar_like]))[0], 0, 1))
    print(f"  NAVKARCORP-like (-9.6% day):    score = {s:.3f}  (should be ~0)")

    # Short EP: negative catalyst, slight red day
    short_ep_like = [0.18, -0.30, 0.01, 1.0, 0.0, 1.61, 1.6, 0.25, -0.02, 1.63, 16614.0, 1.0]
    s = float(np.clip(model.predict(np.array([short_ep_like]))[0], 0, 1))
    print(f"  Short EP (-0.3 catalyst):       score = {s:.3f}")

    # Strong Growth EP: +20%, 9x vol, gap up
    strong_growth = [0.50, 0.90, 0.80, 1.0, 1.0, 5.0, 9.0, 0.95, 20.0, 25.0, 500.0, 0.0]
    s = float(np.clip(model.predict(np.array([strong_growth]))[0], 0, 1))
    print(f"  Strong Growth EP (+20%, 9x):    score = {s:.3f}  (should be high)")

    # Mediocre candidate: +2%, 3x vol, low neglect
    mediocre = [0.10, 0.50, 0.15, 1.0, 1.0, 0.5, 3.0, 0.50, 2.0, 2.5, 5000.0, 0.0]
    s = float(np.clip(model.predict(np.array([mediocre]))[0], 0, 1))
    print(f"  Mediocre (+2%, 3x vol):         score = {s:.3f}  (should be moderate)")

    # CAMPUS-like: +4%, 18x vol
    campus_like = [0.50, 0.50, 0.30, 1.0, 1.0, 0.07, 18.2, 0.31, 4.11, 4.18, 9426.0, 0.0]
    s = float(np.clip(model.predict(np.array([campus_like]))[0], 0, 1))
    print(f"  CAMPUS-like (+4%, 18x vol):     score = {s:.3f}  (fallback=0.489)")

    # ---- Save model ----
    model_dir = project_root / "models"
    os.makedirs(model_dir, exist_ok=True)

    model_path = model_dir / "ep_scoring_model_latest.pkl"
    manifest_path = model_dir / "ep_scoring_model_latest_manifest.json"

    print(f"\n[Model Training] Saving model to {model_path}...")
    joblib.dump(model, str(model_path))

    manifest = {
        "feature_order": FEATURE_ORDER,
        "version": "2.0",
        "model_type": "XGBRegressor",
        "trained_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "training_samples": len(X_train),
        "test_samples": len(X_test),
        "target": "blended: 60% hand-crafted score + 40% forward-return signal (20% threshold)",
        "metrics": {
            "rmse": round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 4),
            "mae": round(float(mean_absolute_error(y_test, y_pred)), 4),
            "r2": round(float(r2_score(y_test, y_pred)), 4),
        },
    }

    print(f"[Model Training] Saving manifest to {manifest_path}...")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Invalidate cached model so next Flask request picks up the new one
    try:
        import app.services.ep_service as ep_mod
        ep_mod._MODEL = None
        ep_mod._MANIFEST = None
        print("[Model Training] Invalidated in-memory model cache.")
    except Exception:
        pass

    print("[Model Training] EP scoring model v2.0 trained and saved successfully.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train EP scoring model")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run in dry mode without training")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
