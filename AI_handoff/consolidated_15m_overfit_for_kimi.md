# Athena v2 — Consolidated 15m Overfit Review Package for Kimi 2.5

Date: 2026-04-07

## Current verified state
We restored Linux parity with the validated Windows-side 15m benchmark, then re-ran both the exact June benchmark and a fresh ~90 day holdout.

### Verified reference fingerprints
- model: `athena/model/athena_brain_15m.pkl`
  - SHA256: `ad644f5189aa6ddc8c3b32089d92f9690db51d913b46459a5e219432d5572be7`
  - size: `2657548`
- CSV: `data/raw/ohlcv/BTCUSDT_15m_2025_06.csv`
  - SHA256: `3bdde032e4f61657ea8bf58b7319e4b9be2bcff45c4d2232d3519a5542244c18`

### Proof commands already run
```bash
cd /home/Andrew/Athena
source .venv/bin/activate
python -m unittest tests.test_signal_model tests.test_feature_pipeline
python run_compare_15m_fast.py
```

### Regression proof
- `python -m unittest tests.test_signal_model tests.test_feature_pipeline`
- result: `Ran 8 tests in 0.299s, OK`

## Benchmark results
### 1) Exact June benchmark (`BTCUSDT_15m_2025_06.csv`)
- `sent_on__conservative`: 39 trades, 82.1% WR, `+0.11%`, Sharpe `15.54`, PF `5.82`
- `sent_on__aggressive`: 60 trades, 48.3% WR, `+0.35%`, Sharpe `4.42`, PF `1.79`
- `sent_off__conservative`: 156 trades, 66.7% WR, `+0.27%`, Sharpe `7.61`, PF `2.55`
- `sent_off__aggressive`: 61 trades, 50.8% WR, `+0.42%`, Sharpe `5.21`, PF `1.98`

### 2) Fresh ~90 day holdout (`data/results/backtest_15m_holdout_90d_windows_ref.json`)
- `sent_on__conservative`: 164 trades, 26.8% WR, `-0.21%`, Sharpe `-6.13`, PF `0.47`
- `sent_on__aggressive`: 1024 trades, 30.2% WR, `-1.75%`, Sharpe `-1.42`, PF `0.83`
- `sent_off__conservative`: 1599 trades, 32.3% WR, `-1.39%`, Sharpe `-3.96`, PF `0.61`
- `sent_off__aggressive`: 1199 trades, 28.7% WR, `-2.78%`, Sharpe `-1.96`, PF `0.77`

## Current interpretation
The deployment layer now appears healthy. The failure is in **generalization**:
- the model can reproduce the old June benchmark,
- but it does not survive on unseen data.

## External review input
### Deepseek position
Deepseek argues the model is overfit to a "golden June" regime and recommends:
- runtime fallback to baseline when recent metrics collapse,
- a simpler LightGBM,
- fewer features,
- TP/SL-first labels,
- strict train/validation/test time splits.

See: `from_deepseek/answer2.md`

### Copilot review of Deepseek
Copilot agrees with the diagnosis overall, with three corrections:
1. no current mode is actually battle-ready,
2. ATR / TP-SL-style labels are already partially present after the sync,
3. future selection should optimize for trading metrics and walk-forward stability, not just classifier accuracy.

See: `copilot_review_deepseek_answer2.md`

## What we want from Kimi 2.5
Please review the situation and recommend the best next step order.

### Questions
1. Do you agree the issue is now mostly overfitting / regime dependence rather than Linux parity?
2. Which should be done first for best signal quality:
   - runtime circuit breaker,
   - feature-group ablation,
   - simpler LightGBM,
   - reworked walk-forward validation?
3. Should sentiment be disabled by default for the next 15m retrain cycle?
4. Which feature families look most suspicious for overfit on 15m:
   - `rolling`
   - `sentiment`
   - `regime`
   - others?
5. What acceptance target would you use for the next holdout before allowing paper trading?

## Files to review
Please review these individual files:
- `from_deepseek/answer2.md`
- `copilot_review_deepseek_answer2.md`
- `change_history.md`
- `delta_summary.md`
- `from_kimi/project_snapshot/README.md`
- `from_kimi/project_snapshot/athena/config.py`
- `from_kimi/project_snapshot/athena/features/engineer.py`
- `from_kimi/project_snapshot/athena/model/signal.py`
- `from_kimi/project_snapshot/athena/model/drift_monitor.py`
- `from_kimi/project_snapshot/athena/model/retrain_policy.py`
- `from_kimi/project_snapshot/athena/risk/manager.py`
- `from_kimi/project_snapshot/train_model_tf.py`
- `from_kimi/project_snapshot/run_compare_15m_fast.py`
- `from_kimi/project_snapshot/tests/test_signal_model.py`
- `from_kimi/project_snapshot/data/results/backtest_15m_comparison.json`
- `from_kimi/project_snapshot/data/results/backtest_15m_holdout_90d_windows_ref.json`
