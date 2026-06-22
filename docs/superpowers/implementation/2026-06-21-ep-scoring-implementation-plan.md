# EP Scoring Model Redesign – Implementation Plan

**Design Spec:** [../specs/2026-06-21-ep-scoring-model-design.md](../specs/2026-06-21-ep-scoring-model-design.md)

---

## 1. Goal & Scope

Replace the hand‑crafted weighted‑sum logic in `compute_ep_score` with an XGBoost‑based classifier that predicts the probability of a ≥ 40 % price move within 5 days. The probability is mapped to the existing confidence tiers (`HIGH ≥ 0.72`, `MEDIUM ≥ 0.55`, otherwise `LOW`).

All work is limited to adding new code, tests, CI steps and deployment wiring – **no existing production code will be removed** until the new model is verified.

---

## 2. High‑Level Task List & Estimated Effort
| # | Task | Owner | Estimated Effort |
|---|------|-------|-------------------|
| 1 | **Finalize design** – lock the spec in `docs/superpowers/specs/2026‑06‑21‑ep‑scoring‑model‑design.md` | — | 0.5 d |
| 2 | **Add dependencies** – add `xgboost==2.0.3` and `joblib==1.3.2` to `requirements.txt` (pin versions) | — | 0.2 d |
| 3 | **Scaffold training script** – `scripts/train_ep_scoring_model.py` (data load, feature engineering, model training, early‑stop, artifact persistence) | — | 1.0 d |
| 4 | **Model‑serving helpers** – implement loader & prediction wrapper in `app/services/ep_service.py` (uses manifest for feature order) | — | 0.8 d |
| 5 | **Configuration** – add `EP_MODEL_PATH`, `EP_CONFIDENCE_HIGH`, `EP_CONFIDENCE_MEDIUM`, `EP_MODEL_TRAIN_HOUR/MINUTE` to `config.py` | — | 0.3 d |
| 6 | **Scheduler integration** – register daily job in `app/tasks/scheduler.py` and thin wrapper in `app/services/model_training_service.py` | — | 0.5 d |
| 7 | **Tests** – create `tests/test_ep_scoring.py` with unit, integration, scheduler and backward‑compatibility tests; achieve ≥ 80 % coverage of inference code | — | 1.2 d |
| 8 | **CI pipeline** – extend `.github/workflows/ci.yml` (or equivalent) to install new deps, run the training script, store the model artifact, and execute the new tests | — | 0.8 d |
| 9 | **Deployment notes** – update Dockerfile (or runtime image) to copy `models/` directory, ensure `EP_MODEL_PATH` env var is set, document rollout steps | — | 0.5 d |
|10 | **Rollback strategy** – script to repoint `models/ep_scoring_model_latest.pkl` symlink to the previous version, disable the scheduler job, and restart the service | — | 0.4 d |
|11 | **Documentation & changelog** – add a short entry to `CHANGELOG.md` and update `docs/EP_Screener_Review.md` with a link to the spec | — | 0.2 d |
|**Total**| | | **6.9 person‑days** |

> *Effort assumes a single developer familiar with the codebase; parallel work can reduce calendar time.*

---

## 3. File Locations & Responsibilities
| File | Responsibility |
|------|----------------|
| `scripts/train_ep_scoring_model.py` | Load data via the SQL query from the spec, perform feature engineering, train XGBoost, persist model (`models/ep_scoring_model_vYYYYMMDD.pkl`) and manifest (`models/ep_scoring_model_manifest.json`). |
| `app/services/ep_service.py` | Singleton loader (`_load_model`), `predict_ep_score` wrapper, reads manifest for feature order, respects `EP_MODEL_PATH` env var. |
| `app/services/model_training_service.py` | Thin wrapper that invokes the training function (or runs the script as a subprocess) – used by the scheduler. |
| `app/tasks/scheduler.py` | APScheduler job registration (ID `ep_model_training`, cron at `EP_MODEL_TRAIN_HOUR:EP_MODEL_TRAIN_MINUTE`). |
| `config.py` | New configuration entries (see spec). |
| `requirements.txt` | Add `xgboost==2.0.3` and `joblib==1.3.2`. |
| `tests/test_ep_scoring.py` | Unit test for `predict_ep_score`, integration test for training pipeline, scheduler registration test, backward‑compatibility test. |
| `.github/workflows/ci.yml` (or CI config) | Install deps, run `pytest`, run `python scripts/train_ep_scoring_model.py --dry-run` (or a fixture), upload model artifact, fail build on training errors. |
| `models/` (runtime) | Stores versioned model files and manifest; `ep_scoring_model_latest.pkl` is a symlink pointing to the most recent successful model. |

---

## 4. Test Coverage Plan
- **Unit tests** (`test_predict_ep_score`): mock `joblib.load` to return a stub model with a deterministic `predict_proba`. Verify rounding and confidence‑tier mapping logic. Target **≥ 90 %** line coverage of `ep_service.py`.
- **Integration test** (`test_training_pipeline`): spin up an in‑memory SQLite DB, populate minimal `ep_features` and `daily_bars`, run the training function, assert a model file is written and validation AUC > 0.70. Target **≥ 80 %** of the training script.
- **Scheduler test** (`test_daily_job_registration`): inspect APScheduler after app start, confirm job ID `ep_model_training` exists with correct cron trigger.
- **Backward‑compatibility test** (`test_api_response`): hit the existing EP API endpoint (using the test client) after model swap; assert response schema still contains `confidence` and `ep_score` fields.
- **Overall CI coverage goal**: **≥ 85 %** for new EP‑scoring code.

---

## 5. CI Integration Details
1. **Install new deps** – extend the `pip install -r requirements.txt` step.
2. **Run lint & type‑check** – unchanged, but add `flake8`/`mypy` paths for new files.
3. **Training step** – after unit tests, execute `python scripts/train_ep_scoring_model.py --no‑push` (dry‑run flag to avoid committing artefacts). Capture exit code; on failure, CI aborts.
4. **Artifact handling** – if the step succeeds, upload the generated `models/ep_scoring_model_*.pkl` as a CI artifact for downstream jobs (e.g., staging deployment).
5. **Test execution** – `pytest -q --cov=app/services/ep_service.py --cov=scripts/train_ep_scoring_model.py`.
6. **Cache** – optionally cache `~/.cache/xgboost` to speed up repeated runs.

---

## 6. Deployment & Rollout Notes
| Phase | Action |
|-------|--------|
| **Staging** | Deploy the new Docker image (or runtime) with the freshly built model artifact. Verify EP API responses, confidence tiers and latency (≤ 5 ms per request). |
| **Canary** | Enable the new model for a small traffic slice (e.g., 5 % of users) via an environment variable (`EP_CANARY=true`). Monitor AUC on live data and error logs. |
| **Full rollout** | Switch the `ep_scoring_model_latest.pkl` symlink to the new version globally, remove the canary flag, and restart the service. |
| **Post‑deployment monitoring** | Log `Model training completed – AUC: X.XX` (already in `logs/model_training.log`). Set up an alert if the latest validation AUC drops below 0.70 or if the job fails. |

---

## 7. Rollback Strategy
1. **Model artifact versioning** – every successful training creates a timestamped `.pkl` file. The previous model is never deleted.
2. **Symlink swap** – the service loads the model via the `ep_scoring_model_latest.pkl` symlink. To rollback, repoint the symlink to the previous timestamped file and restart the service (or send a `SIGUSR1` to trigger reload).
3. **Scheduler safeguard** – if the daily training job fails, the code leaves the existing `latest` symlink untouched, guaranteeing continuity.
4. **Feature‑flag disable** – set `EP_MODEL_PATH` to a known‑good fallback (e.g., a static model bundled with the repo) and redeploy; the service will load that model instead of the failing one.
5. **Verification after rollback** – run the smoke‑test suite (`pytest -k test_predict_ep_score`) against the rolled‑back deployment to ensure the API again returns sensible confidence values.

---

## 8. Open Issues & Risks (from the spec)
- **Model drift** – mitigated by daily retraining and weekly health alerts.
- **Dependency build failures** – pinning versions in `requirements.txt` and verifying CI step resolves this.
- **Feature mismatch** – training script validates required columns before training; any schema change will abort with a clear error and keep the previous model active.
- **Cold‑start latency** – the model is loaded lazily on first request and cached; the impact is bounded to a single request.

---

## 9. Acceptance Criteria
- All new files compile (`python -m py_compile` passes).
- CI pipeline passes with 100 % test success and the training step completing without errors.
- Staging deployment shows EP API returning `confidence` and `ep_score` derived from the model.
- Rollback procedure documented and verified by a manual dry‑run.
- Documentation links to the design spec are present.

---

*Implementation plan generated by the `writing-plans` specialist on 2026‑06‑21.*