# Project Snapshot for Kimi 2.5

Included directly from the live project on 2026-04-07.

## Python files
- `athena/config.py`
- `athena/features/engineer.py`
- `athena/model/signal.py`
- `athena/risk/manager.py`
- `train_model_tf.py`
- `run_compare_15m_fast.py`
- `tests/test_signal_model.py`

## Brain/model files
- `athena/model/athena_brain_15m.pkl` (current reference brain in use)
- `athena/model/athena_brain_15m_20260407_backup.pkl`
- `athena/model/athena_brain_15m_linux_retrained_backup_20260407.pkl`

## JSON result files
- `data/results/backtest_15m_comparison.json`
- `data/results/backtest_15m_holdout_90d_windows_ref.json`
- `data/results/backtest_15m_3m_retrained.json`
- `data/results/backtest_15m_3m_matrix.json`

## Verified fingerprints
- active model SHA256: `ad644f5189aa6ddc8c3b32089d92f9690db51d913b46459a5e219432d5572be7`
- June benchmark CSV SHA256: `3bdde032e4f61657ea8bf58b7319e4b9be2bcff45c4d2232d3519a5542244c18`
