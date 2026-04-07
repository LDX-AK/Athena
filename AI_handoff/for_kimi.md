# Athena v2 -> Kimi 2.5 Review Package

## Focus of this handoff
This package is **no longer about Stage 4 telemetry**.  
The current issue is the 15m model's **poor generalization on fresh data**.

## Short context
We completed a Linux parity sync with the previously validated Windows-side setup.
That restored the old positive June benchmark, but the same model still fails on a fresh ~90 day holdout.

## Verified facts
- Linux regression tests pass:
  - `python -m unittest tests.test_signal_model tests.test_feature_pipeline` -> `Ran 8 tests in 0.299s, OK`
- Exact June benchmark is positive again.
- Fresh 90d holdout remains negative in all 4 scenarios.

## External opinions collected so far
### Deepseek says
- the model is overfit to June 2025,
- we should simplify the model,
- reduce features,
- add a runtime fallback,
- and validate with strict time splits.

### Copilot says
- the diagnosis is mostly correct,
- but no current mode is actually ready for paper/live,
- ATR / TP-SL-style labels are already partly implemented,
- the next loop should emphasize walk-forward validation and feature ablation.

## Please review
Send these files individually in this order:
1. `consolidated_15m_overfit_for_kimi.md`
2. `from_deepseek/answer2.md`
3. `copilot_review_deepseek_answer2.md`
4. `from_kimi/project_snapshot/README.md`
5. `from_kimi/project_snapshot/athena/config.py`
6. `from_kimi/project_snapshot/athena/features/engineer.py`
7. `from_kimi/project_snapshot/athena/model/signal.py`
8. `from_kimi/project_snapshot/athena/model/drift_monitor.py`
9. `from_kimi/project_snapshot/athena/model/retrain_policy.py`
10. `from_kimi/project_snapshot/athena/risk/manager.py`
11. `from_kimi/project_snapshot/train_model_tf.py`
12. `from_kimi/project_snapshot/run_compare_15m_fast.py`
13. `from_kimi/project_snapshot/tests/test_signal_model.py`
14. `from_kimi/project_snapshot/data/results/backtest_15m_comparison.json`
15. `from_kimi/project_snapshot/data/results/backtest_15m_holdout_90d_windows_ref.json`
16. `change_history.md`
17. `delta_summary.md`

## Important note
Do not refer to a whole folder when sending to Kimi.
Send only the individual files listed above.

## What we want from Kimi 2.5
1. Confirm or reject the overfit diagnosis.
2. Prioritize the next intervention order.
3. Suggest the best minimal-safe plan to get the 15m holdout to:
   - Sharpe `> 0.5`
   - Return `> 0%`
   before paper trading.
