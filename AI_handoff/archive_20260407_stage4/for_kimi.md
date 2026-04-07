# Athena v2 -> Kimi Review Package

## Context
This folder was prepared to simplify direct review by Kimi.
Included files:
- Athena_TZ.md
- change_history.md
- drift_monitor.py
- retrain_policy.py
- router.py (with confidence propagation)

## What changed (short)
1. Drift monitor was upgraded from simple threshold checks to richer drift detection:
- baseline capture on first full window
- relative drift checks (winrate/sharpe/confidence)
- volatility regime alert
- consecutive loss streak alert
- alert codes + reasons for traceability

2. Retrain policy now includes hysteresis/safety:
- cooldown between retrains
- weekly retrain budget
- critical-alert quorum before drift retrain
- dry-run mode retained for safe rollout

3. Execution router now propagates `confidence` into trade results,
so drift logic can analyze confidence decay on closed trades.

## Answers to current edge-case questions

### 1) Baseline behavior on first run (before N trades)
Current behavior:
- if trade history length < `window_trades`: no drift evaluation
- once first full window is available, monitor captures baseline snapshot and returns `baseline-captured`
- drift is not triggered on that same baseline-capture pass

Interpretation:
- safe cold-start, no false retrain spikes during startup

Potential improvement (optional):
- persist baseline across restarts (JSON metadata), so reboot does not reset baseline learning phase.

### 2) Simultaneous loss streak + volatility regime
Current behavior:
- both alert codes are emitted in one evaluation cycle
- `alerts_in_row` increments once per cycle (not once per alert)
- retrain policy checks critical-alert quorum using unique alert set

Impact:
- this combination is treated as stronger signal than single-alert drift
- with current policy it can satisfy critical condition in one cycle,
then trigger retrain when cooldown/budget allow

Potential improvement (optional):
- add severity scoring to alerts (e.g., LOSS_STREAK=2, REGIME_VOLATILITY=2) for graded decisions.

### 3) Cooldown under sharp regime change
Current behavior:
- cooldown blocks immediate retrain even if drift is severe
- this avoids retrain spam but can delay reaction to abrupt regime shifts

Risk:
- important retrain window may be missed in extreme volatility transitions

Suggested patch:
- add emergency bypass rule:
  - if `LOSS_STREAK` + `REGIME_VOLATILITY` + `SHARPE_DRIFT` co-occur
  - and magnitude exceeds hard threshold
  - allow one cooldown override retrain (rate-limited to 1 per X hours)

## Requested review focus for Kimi
Please review these files for edge cases and policy quality:
- drift_monitor.py
- retrain_policy.py
- router.py

Questions to review:
1. Is baseline cold-start logic robust enough for sparse trade periods?
2. Is critical-alert quorum sufficient, or should weighted severity be used?
3. Should cooldown bypass be introduced for extreme regime breaks?
4. Any obvious failure mode in confidence propagation from router -> trade_history?

## Notes
This package is a copy for review handoff.
Source of truth remains in the main project paths under `athena/`.

## Update after your last edge-case review
Implemented now (P0):
- confidence fallback fixed (`None` instead of `0.0` for legacy positions)
- Sharpe guard for tiny std (`std < 1e-6 => sharpe=0.0`)
- confidence coverage guard in drift monitor (skip confidence drift on sparse confidence data)
- emergency retrain bypass for severe regime breaks with its own emergency rate limit
- added unit tests for retrain policy emergency behavior

Please re-review current versions in this folder:
- `drift_monitor.py`
- `retrain_policy.py`
- `router.py`
- `change_history.md`
