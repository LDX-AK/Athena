# Deepseek answer2 — 15m overfit diagnosis and treatment

Date: 2026-04-07
Source: external review summary from Deepseek

## Core diagnosis
Deepseek's main conclusion is that the current 15m model is **overfit to the June 2025 regime**.
In short:
- on the exact June benchmark the model looks excellent,
- on a fresh ~90 day holdout it loses money consistently,
- therefore the issue is not deployment but **poor generalization**.

## Deepseek's proposed explanation
1. **"Golden June 2025" effect**
   - the model likely memorized a very favorable/trendy market regime.
2. **Model too complex for 15m**
   - LightGBM + 60+ features can overfit noise on a short intraday horizon.
3. **Labeling problem**
   - fixed lookahead on 15m can be unstable in crypto.
4. **Curse of dimensionality**
   - too many features relative to the number of effective trade examples.

## Deepseek's treatment plan
### Phase 1 — Stop the bleeding
- Temporarily lock the strategy to the least-bad configuration.
- Disable global sentiment (`SENTIMENT_ENABLED = False`) to reduce noise.
- Add a runtime guardrail:
  - if last 20 trades show `win_rate < 35%` and `sharpe < 0`,
  - automatically switch to baseline mode (`OBI + RSI`),
  - reduce risk size (example: `max_position_pct = 0.005`).

### Phase 2 — Train a simpler model
- Reduce features to roughly the **top-20** by importance.
- Remove suspicious overfit-heavy rolling stats first (`rolling_mean_*`, `rolling_skew_*`, etc.).
- Make LightGBM simpler:
  - `num_leaves = 15`
  - `max_depth = 4`
  - `min_child_samples = 100`

### Phase 3 — Improve labels
- Prefer **TP/SL-first labeling with a max bars horizon**,
  rather than learning a raw N-candle price move.
- Example target logic:
  - label `1` if TP is hit before SL,
  - label `-1` if SL is hit before TP,
  - label `0` if neither is hit inside `max_bars`.

### Phase 4 — Use time-based validation
- Train on **April–May 2025**,
- validate on **June 2025**,
- test on **July–September 2025**.

## Intended outcome
The model should stop being a "June specialist" and start surviving on unseen market regimes.
