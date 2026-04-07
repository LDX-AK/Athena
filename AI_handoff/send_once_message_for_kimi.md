# One-Shot Message for Kimi 2.5

Use this as a single message when sending the updated package.

---

Hi Kimi,

We have a new review package focused on the Athena 15m model's **generalization failure / overfit problem**.

What is already verified:
- Linux parity with the validated Windows 15m setup is restored.
- The exact June benchmark is positive again.
- A fresh ~90 day holdout is still negative across all 4 scenarios.

This strongly suggests the main issue is no longer deployment, but **overfitting to the old June 2025 regime**.

Please review these files in this order:
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

What we need from you now:
1. Do you agree with the overfit diagnosis?
2. What should we prioritize first:
   - runtime circuit breaker,
   - feature-group ablation,
   - simpler LightGBM,
   - stricter walk-forward validation?
3. Should `sentiment` be disabled for the next 15m retrain cycle by default?
4. What concrete acceptance criteria would you require on the holdout before paper trading?

Goal:
Find the smallest robust set of changes that can move the 15m holdout to something like:
- Sharpe `> 0.5`
- Return `> 0%`
while preserving the restored Linux parity.

Thanks.

---
