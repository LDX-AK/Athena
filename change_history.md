# Athena Change History

## Rules
- This file tracks large/meaningful project changes.
- After each major change, append a new record with timestamp and summary.
- Keep entries short, factual, and test-oriented.

## Planned Fixes (Working List)

### P0 - Core Stability
1. Replace `ccxt.pro` usage with regular `ccxt` in runtime code paths.
2. Fix trade lifecycle in core loop: open -> monitor -> close -> PnL update.
3. Synchronize risk state with real open/closed positions.

### P1 - Strategy Logic
4. Implement MTF filter (1m execution + 15m trend gate) controlled by config flags.
5. Ensure dashboard reads real runtime outputs (stats/history writer in runtime).
6. Standardize module contracts (batch format, execution result, risk snapshot).

### P2 - Reliability and QA
7. Add startup scripts (train/backtest/paper) for predictable runs.
8. Add baseline tests for config and feature pipeline.
9. Run smoke-test (imports + backtest without live keys) after the above fixes.

## Completed Major Changes

### [2026-04-09] Formal v2/v3 separation protocol
- Locked a permanent branch model for parallel development:
  - `dev/v2-revival` for regression-driven Athena v2 recovery,
  - `dev/v3-regime-first` for the separate router-first Athena v3 track,
  - `main` reserved for shared infrastructure fixes.
- Added documented path helpers and isolated entrypoints:
  - `athena/track_paths.py`
  - `scripts/run_v2_regression.py`
  - `scripts/run_v3_walkforward.py`
- Artifact storage is now explicitly split across:
  - `data/results/v2/` vs `data/results/v3/`
  - `athena/model/v2/` vs `athena/model/v3/`
- Verification:
  - `.venv/bin/python -m unittest tests.test_track_paths tests.test_15m_scripts` → `Ran 17 tests in 0.623s, OK`

### [2026-04-01] GitHub synchronization after power outage
- Synced local repository with GitHub `main`.
- Committed and pushed:
  - `Athena_TZ.md`
  - `test_athena_smoke.py`
  - `test_imports.py`
- Commit: `64ab69b`
- Status: local `main` aligned with `origin/main`.

### [2026-04-01] Environment baseline recovery
- Recreated and configured `.venv` for project runtime.
- Reinstalled required Python packages in the project environment.
- Recorded environment instability around NumPy 2.x DLL loading on this machine.
- Temporary compatibility baseline kept during investigation.

### [2026-04-01 16:55] P0 runtime refactor: ccxt + paper lifecycle
- Replaced runtime imports from `ccxt.pro` to regular `ccxt` in fetcher and router.
- Switched market stream from websocket watchers to REST polling in `AthenaFetcher.stream()`.
- Added paper position exit checks (`SL/TP`) on each new candle in core loop.
- Stopped incorrect PnL updates on position open; risk is now updated on close events.
- Added risk position synchronization methods:
  - `register_open_position(...)`
  - `register_closed_position(...)`
- Updated requirements note to document regular `ccxt` runtime choice.

### [2026-04-01 17:10] QA baseline and run tooling
- Updated `test_athena_smoke.py` to match current APIs (`transform`, `risk.check`, current dataclasses).
- Added startup tooling:
  - `Makefile` targets for install/smoke/test/train/backtest/paper
  - `run.ps1` with unified launch modes for Windows
- Added baseline unit tests:
  - `tests/test_config.py`
  - `tests/test_feature_pipeline.py`
- Fixed test typing guards for optional feature output (`None` handling).

### [2026-04-01 17:25] Approved upcoming roadmap (from architecture review)
- Updated technical specification to v1.1.
- Confirmed near-term runtime strategy: regular `ccxt` during hardening phase.
- Added approved drift-control direction:
  - `AthenaDriftMonitor`
  - retrain trigger policy (schedule + drift)
  - safe rollout/rollback model policy
- Locked phased delivery model with re-check after each major step.

### [2026-04-01 17:40] Stage 1 implemented: drift monitor in runtime
- Added `athena/model/drift_monitor.py`.
- Added configurable drift section in `athena/config.py`:
  - `window_trades`, `min_win_rate`, `min_profit_factor`, `min_sharpe`, `consecutive_alerts`.
- Integrated drift evaluation into `athena/core.py` after each closed paper trade.
- Runtime now logs pre-alerts and hard drift state when thresholds fail repeatedly.

### [2026-04-01 17:50] Stage 2 implemented: retrain trigger policy (safe mode)
- Added `athena/model/retrain_policy.py`.
- Added retrain config block in `athena/config.py`:
  - `schedule_days`, `cooldown_hours`, `trigger_on_drift`, `dry_run`.
- Integrated retrain policy into `athena/core.py` after drift evaluation.
- Current behavior is safe by default: trigger is logged (`dry_run=True`), no auto-training yet.

### [2026-04-01 18:05] Kimi-driven hardening of drift/retrain logic
- Extended drift config with richer thresholds:
  - `winrate_drop`, `confidence_drop`, `sharpe_drop`
  - `volatility_multiplier`, `consecutive_losses`
- Enhanced `AthenaDriftMonitor`:
  - baseline snapshot on first full window,
  - confidence drift detection,
  - loss streak detection,
  - regime volatility detection,
  - alert codes separate from human-readable reasons.
- Passed signal confidence through execution results for drift analysis.
- Upgraded `AthenaRetrainPolicy`:
  - weekly retrain budget,
  - critical alert counting,
  - drift trigger with hysteresis instead of simple boolean trigger.
- Added baseline unit test for drift monitor: `tests/test_drift_monitor.py`.

### [2026-04-01 18:20] Kimi edge-case fixes (P0)
- Fixed confidence propagation failure mode for legacy positions:
  - `router.close_paper_position()` now returns `confidence=None` if not tracked,
    instead of forcing `0.0` (avoids false confidence drift).
- Hardened Sharpe computation in drift monitor:
  - when `std < 1e-6`, Sharpe is treated as `0.0`.
- Added confidence coverage guard in drift monitor:
  - if confidence data coverage in window is low, confidence drift is skipped.
- Added emergency retrain bypass in policy:
  - enabled for extreme combo (`LOSS_STREAK` + `REGIME_VOLATILITY` + high severity),
  - protected by emergency rate limit (`emergency_cooldown_hours`).
- Added retrain policy tests for emergency trigger and emergency rate limit:
  - `tests/test_retrain_policy.py`.

### [2026-04-01 18:40] Stage 3 implemented: MTF trend gate wired into runtime and backtest
- Added runtime MTF config controls in `athena/config.py`:
  - `mtf_timeframe`, `mtf_min_trend`, `mtf_min_higher_candles`.
- Integrated `MTFGate` in live loop (`athena/core.py`) before risk approval:
  - signals that fail higher-timeframe trend alignment are skipped with reason logging.
- Integrated `MTFGate` in entry logic of `athena/backtest/runner.py`:
  - entries now require both confidence threshold and MTF pass.
- Added tests:
  - `tests/test_mtf_gate.py` (trend pass/fail and insufficient-data behavior),
  - updated `tests/test_config.py` with MTF config sanity checks.
- Validation:
  - `python -m unittest tests.test_config tests.test_mtf_gate` → `OK`.

### [2026-04-02] Kimi handoff package prepared (awaiting send)
- Prepared `to_kimi` handoff update for Stage 4 discussion.
- Added `to_kimi/answer4.md` and `to_kimi/copilot_review_answer4.md`.
- Status: package is ready for review; not sent yet.

### [2026-04-02] Stage 4 implemented (v1): backward-compatible runtime telemetry writer
- Added `athena/monitor/stats_writer.py`:
  - non-blocking periodic flush via `asyncio` task,
  - atomic write for `data/live_stats.json`,
  - bounded JSON-array history for `data/trade_history.json`.
- Integrated writer into `athena/core.py`:
  - startup/shutdown lifecycle (`start()` / `stop()`),
  - safe shutdown via `finally`,
  - trade logging on paper close events,
  - periodic live stats snapshots with MTF/drift telemetry fields.
- Added monitor config block in `athena/config.py`:
  - `live_stats_path`, `trade_history_path`, `flush_interval_sec`, `max_history_trades`.
- Added tests for telemetry writer:
  - `tests/test_stats_writer.py` (file creation, timestamp presence, bounded history behavior).

### [2026-04-03 to 2026-04-08] Strict 15m research cycle expanded and verified
- Extended the walk-forward program with hierarchy / macro-filter / adaptive-mode experiments across `1h`, `30m`, and `15m` variants.
- Verified result: honest OOS remained negative across the tested branches; these runs are kept as negative controls in `data/results/`.
- Added feature/label redesign v1:
  - `atr_hilo` / `atr_first_touch` / `atr_intrabar` labeling modes,
  - compact ablation candidates `core_compact`, `price_action_core`, `atr_hilo_core`.
- Added runtime observability upgrades:
  - pipeline diagnostics in `live_stats.json`,
  - block-history charts in Streamlit,
  - Mermaid architecture/runtime diagrams in `docs/`.
- Added raw signal diagnostics by side / confidence / regime / hour and confirmed the core issue:
  - long side dragged results,
  - short side retained only a weak raw edge,
  - high-confidence signals were not reliably better.

### [2026-04-08] Scoped filters, dedicated short-only retrain, and v2 strategy archive
- Added strict walk-forward controls:
  - `--direction`, `--regime`, `--meta-hours`, `--meta-regimes`, `--meta-min-confidence`, `--meta-max-confidence`.
- Added one-sided training support via `label_target=short|long|both` and fixed binary-class inference mapping.
- Fresh verification evidence:
  - `python -m unittest discover -s tests` → `Ran 62 tests in 0.806s, OK`.
  - Q4 dedicated short-only holdout remained negative:
    - conservative `-0.1927%`, Sharpe `-3.26`, PF `0.66`
    - aggressive `-0.4136%`, Sharpe `-1.48`, PF `0.82`
  - diagnostics for the retrained short-only model showed a small positive raw edge (`edge_per_signal = +0.0001608`) that did not survive execution costs / trade geometry.
- Archived the v2 salvage branch snapshot into `backups/strategy_archive_2026-04-08/`.
- Decision: freeze `Athena v2 short-only / meta-filter salvage` as a documented baseline and pivot the active roadmap to `Athena v3: Regime-first + Session-aware + rolling retrain`.
