# EP Scoring Model – Data‑Driven Design (2026‑06‑21)

## 1. Goal
Replace the hand‑crafted weighted sum in `compute_ep_score` with a **gradient‑boosted tree (XGBoost) classifier** that predicts the probability of a ≥ 40 % price move within 5 days. The predicted probability is mapped to the existing confidence tiers (`HIGH ≥ 0.72`, `MEDIUM ≥ 0.55`, otherwise `LOW`).

## 2. Data Pipeline (Training Set)
| Source | Columns | Transformation |
|--------|---------|----------------|
| `ep_features` | `symbol`, `feature_date`, `neglect_score`, `catalyst_score`, `repricing_score`, `has_fundamentals`, `liquidity_ok`, `event_type` (derived via `assign_ep_type`) | Keep numeric scores; one‑hot encode `event_type`. |
| `daily_bars` | `symbol`, `trade_date`, `close` | For each EP row fetch the closing price on `feature_date` (price₀) and the closing price 5 trading days later (price₅). Compute `pct_move = (price₅‑price₀)/price₀`. |
| Label | `label = 1` if `pct_move ≥ 0.40` else `0` | Binary target for the classifier. |

**SQL sketch (pseudo‑code)**
```sql
WITH ep AS (
    SELECT f.id, f.symbol, f.feature_date,
           f.neglect_score, f.catalyst_score, f.repricing_score,
           f.has_fundamentals, f.liquidity_ok,
           <event_type expression> AS event_type
    FROM ep_features f
    WHERE f.feature_date = (SELECT MAX(feature_date) FROM ep_features)
),
price AS (
    SELECT d.symbol, d.trade_date, d.close
    FROM daily_bars d
    WHERE d.trade_date IN (
        SELECT feature_date FROM ep
        UNION ALL
        SELECT DATE(feature_date, '+5 days') FROM ep
    )
)
SELECT e.*, 
       (p5.close - p0.close) / p0.close AS pct_move,
       CASE WHEN (p5.close - p0.close) / p0.close >= 0.40 THEN 1 ELSE 0 END AS label
FROM ep e
JOIN price p0 ON p0.symbol = e.symbol AND p0.trade_date = e.feature_date
JOIN price p5 ON p5.symbol = e.symbol AND p5.trade_date = DATE(e.feature_date, '+5 days');
```
The query is executed in the training script via SQLAlchemy.

## 3. Model Training Script (`scripts/train_ep_scoring_model.py`)
1. Load data using the query above.
2. Feature engineering – one‑hot `event_type`; impute missing numeric values with column means.
3. Train/validation split (80 %/20 %, stratified).
4. Model: `xgboost.XGBClassifier`
   * `objective='binary:logistic'`
   * `eval_metric='logloss'`
   * `n_estimators=200`, `max_depth=5`, `learning_rate=0.1`.
5. Early stopping (10 rounds) on the validation set.
6. Persist model with **Joblib**: `models/ep_scoring_model_v{YYYYMMDD}.pkl` and update a symlink `models/ep_scoring_model_latest.pkl`.
7. Write a JSON manifest (`models/ep_scoring_model_manifest.json`) containing the feature order, model version, and training metrics (AUC, accuracy, precision, recall).
8. Log metrics to `logs/model_training.log`.

Idempotency: the script overwrites the `latest` symlink only after a successful training run.

## 4. Inference – EP Service Integration (`app/services/ep_service.py`)
```python
_MODEL = None
_MODEL_PATH = Path(__file__).parent.parent / "models" / "ep_scoring_model_latest.pkl"

def _load_model():
    global _model
    if _model is None:
        import joblib
        _model = joblib.load(_MODEL_PATH)
    return _model

def predict_ep_score(features: dict) -> float:
    # Build a 2‑D numpy array in the order stored in the manifest
    import numpy as np, json
    manifest = json.load(open(Path(__file__).parent.parent / "models" / "ep_scoring_model_manifest.json"))
    ordered = [features.get(col, 0.0) for col in manifest["feature_order"]]
    prob = _load_model().predict_proba(np.array([ordered]))[0, 1]
    return round(float(prob), 3)
```
`compute_ep_score` is replaced (or wrapped) to gather the required numeric fields, build the `features` dict, and return `predict_ep_score(features)`.

## 5. Scheduler – Daily Retraining
Add an APScheduler job in `app/tasks/scheduler.py`:
```python
scheduler.add_job(
    func=run_ep_model_training,
    trigger='cron',
    hour=16, minute=0,                     # 16:00 IST ≈ market close + buffer
    timezone='Asia/Kolkata',
    id='ep_model_training',
    name='Daily EP scoring model training',
    replace_existing=True,
)
```
`run_ep_model_training` lives in `app/services/model_training_service.py` and simply calls the training function (or runs the script via `subprocess`). Errors are logged; on failure the previous model remains active.

## 6. Configuration (`config.py`)
```python
class ProductionConfig(BaseConfig):
    EP_MODEL_PATH = os.getenv('EP_MODEL_PATH', 'models/ep_scoring_model_latest.pkl')
    EP_CONFIDENCE_HIGH = float(os.getenv('EP_CONFIDENCE_HIGH', 0.72))
    EP_CONFIDENCE_MEDIUM = float(os.getenv('EP_CONFIDENCE_MEDIUM', 0.55))
    EP_MODEL_TRAIN_HOUR = int(os.getenv('EP_MODEL_TRAIN_HOUR', 16))
    EP_MODEL_TRAIN_MINUTE = int(os.getenv('EP_MODEL_TRAIN_MINUTE', 0))
```
The loader in `ep_service.py` respects `EP_MODEL_PATH`.

## 7. Testing
| Test | Scope |
|------|-------|
| `test_predict_ep_score` (unit) | Mock `_load_model` to return a stub that yields a known probability; verify `compute_ep_score` returns the rounded value. |
| `test_training_pipeline` (integration) | Spin up an in‑memory SQLite DB with minimal `ep_features` and `daily_bars`; run the training function; assert a model file is created and validation AUC > 0.70. |
| `test_daily_job_registration` | Ensure APScheduler has a job with ID `ep_model_training` and the correct cron trigger. |
| `test_backward_compatibility` | Call the existing EP API endpoints after model swap; confirm the response schema still contains `confidence` and `ep_score`. |
All tests reside under `tests/` and are executed by the CI pipeline.

## 8. Deployment & Versioning
- Model artifacts are stored under `models/` (binary files). The CI pipeline runs the training script in a sandbox; on success it pushes the new artifact to the repository (binary files are allowed). 
- The CI adds a step that runs the training script to guarantee it completes before merge. 
- Documentation updates: a **Design** section is added to `docs/EP_Screener_Review.md` linking to this spec; the API docs note that `ep_score` now originates from a learned model.

## 9. Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Model drift (regime change) | Degraded scoring accuracy | Daily retraining keeps the model current; a weekly health alert based on validation AUC flags any regression. |
| Training job failure leaves no model | API errors if model file missing | The job writes to a temporary file and only swaps the `latest` symlink on success; on failure the previous model stays active. |
| Added dependencies (`xgboost`, `joblib`) cause build issues | CI breakage | Pin versions (`xgboost==2.0.3`, `joblib==1.3.2`) in `requirements.txt`; run `pip install -r requirements.txt` in CI. |
| Feature mismatch after schema change | Training script crashes | The script validates required columns before training and aborts with a clear error; the previous model remains in service. |
| Latency overhead on first request | Slight slowdown | Model is loaded once (singleton) and cached; subsequent predictions are sub‑millisecond. |

## 10. Next Steps (Implementation Plan)
1. **Finalize design** – this document is now committed.
2. **Scaffold code** – add training script, model loader, inference wrapper, scheduler entry, config entries.
3. **Write tests** – unit, integration, scheduler verification.
4. **CI integration** – ensure the training step runs and artifacts are published.
5. **Deploy to staging** – run a full EP refresh, verify scores and confidence mapping.
6. **Monitoring** – add log entry `Model training completed – AUC: X.XX` and alert on training failures.

---
*Prepared by the brainstorming subsystem on 2026‑06‑21.*