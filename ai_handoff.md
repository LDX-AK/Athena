# Athena — AI Handoff & Recommendations Log

## Purpose
This file is the coordination layer between multiple AI assistants (GitHub Copilot, Kimi, Claude, Perplexity, etc.).
It tracks **pending recommendations**, **open design questions**, and **cross-session context** so any AI can pick up where the previous one left off.

## Directory structure
```
AI_handoff/
├── from_claude/       ← Claude
├── from_kimi/         ← Kimi
├── from_perplexity/   ← Perplexity
├── from_gemini/       ← Google Gemini
├── from_grok/         ← xAI Grok
├── from_deepseek/     ← DeepSeek
├── from_mistral/      ← Mistral Le Chat
└── *.py / *.md        ← outgoing context packages for any AI
ai_handoff.md          ← this file (coordination log)
change_history.md      ← implemented changes log
```

## How to use
- **Reading AI**: scan all entries below, especially `Status: Pending` items
- **Writing AI**: append a new dated block after completing analysis or implementation
- **Do NOT remove entries** — mark them `Status: Done` or `Status: Superseded`
- Companion file for implemented changes: `change_history.md`

---

## Entry Format

```
### [YYYY-MM-DD] <Source AI> — <topic>
Source: <model name, session>
Status: Pending | In Progress | Done | Superseded
Decided by: <who/when, if resolved>

<content>
```

---

## Entries

---

### [2026-04-02] Claude — Stage 4 review & priority queue
Source: Claude (from_claude/answer1.md)
Status: Pending — awaiting Kimi confirmation + Copilot implementation

#### Priority queue (recommended order):

1. **`unrealized_pnl` wiring** (~15 min) — do FIRST
   - In `core.py`, replace `"unrealized_pnl": 0.0` with real calculation:
   ```python
   def _calc_unrealized_pnl(router, current_prices: dict) -> float:
       total = 0.0
       for key, pos in router.paper_positions.items():
           symbol = pos["symbol"]
           price  = current_prices.get(symbol, pos["entry"])
           pnl    = (price - pos["entry"]) / pos["entry"] * pos["size_usd"] * pos["direction"]
           pnl   -= pos["commission"]
           total += pnl
       return total
   ```
   - `current_prices` built each iteration from `batch["ohlcv"][-1][4]` per symbol

2. **Paper smoke window** (3–5 days) — run paper mode and verify:
   - Both `data/live_stats.json` and `data/trade_history.json` are created
   - `timestamp` increments every ~5 sec in live_stats
   - After first SL/TP close — `trade_history.json` is non-empty
   - Streamlit equity curve renders correctly

3. **Stage 4 v2 — JSONL migration** — only after smoke confirms v1 stable
   - Migration path: dual-write JSON + JSONL in parallel first
   - Update Streamlit to support both formats (dual-reader)
   - Remove JSON array writer after 1 week stable
   - See also: Q2 in `consolidated_stage4_for_kimi.md`

4. **Add `model_version` field to telemetry** — together with v2
   - Field: hash or train timestamp of current LightGBM model
   - Purpose: correlate drift alerts with specific model version in dashboard

5. **Move `update_live_stats()` to end of iteration** in `core.py` (minor)
   - Currently called at top of loop → stats reflect previous batch
   - Move to after signal processing for accurate snapshot

#### Edge case noted by Claude:
- `_sync_flush()` in `stats_writer.py` does read-modify-write on entire history file
  at every flush interval. At `max_history=1000` this is ~fine. If limit grows,
  becomes a bottleneck. JSONL in v2 eliminates this by design (append-only).

#### Stage 4 v2 migration path (recommended):
- Do NOT migrate before paper smoke confirms v1 stable
- Dual-write first, then update Streamlit, then remove JSON writer after 1 week

---

### [2026-04-02] Copilot — Stage 4 v1 implementation summary
Source: GitHub Copilot (this session)
Status: Done

#### Implemented:
- `athena/monitor/stats_writer.py` — `StatsWriter` class, non-blocking, atomic writes
- `athena/core.py` — integrated writer lifecycle (start/stop/finally), telemetry snapshot
- `athena/config.py` — added `monitor` section (paths, flush_interval, max_history_trades)
- `tests/test_stats_writer.py` — 2 async tests, both passing

#### Known gaps left for next iteration (v2):
- `unrealized_pnl` hardcoded to `0.0` (tagged TODO in core.py)
- JSON array format kept for Streamlit backward-compat — not JSONL yet
- `model_version` field not yet in telemetry

#### Test status at handoff:
- `test_config`: 4/4 OK
- `test_mtf_gate`: 3/3 OK
- `test_stats_writer`: 2/2 OK
- `test_drift_monitor`: OK
- `test_retrain_policy`: OK

---

### [2026-04-02] DeepSeek — Stage 4 validation pass
Source: DeepSeek (AI_handoff/from_deepseek/answer1.md)
Status: Reviewed by Copilot

#### DeepSeek conclusions (aligned with existing direction):
- Stage 4 v1 is implemented correctly for backward-compat operation.
- Keep v1 architecture for now; move JSONL changes to Stage 4 v2 after paper soak.
- Current read-modify-write history logic is acceptable at `max_history_trades=1000`.
- `unrealized_pnl` remains the main functional gap to implement next.

#### DeepSeek proposals accepted:
- Keep v1 as-is for paper mode while collecting stability evidence.
- Treat JSONL migration as v2 scope (not P0 for current branch).
- Keep `update_live_stats()` snapshot approach with periodic flush task.

#### DeepSeek proposals to defer/refine:
- JSONL implementation details from answer1 are conceptual and need concrete code design before implementation.
- `emergency` fallback format is acceptable for now; no immediate parser change required.

#### Copilot verdict on DeepSeek answer:
- Score: **8.7/10**
- Usefulness: High
- Blocking issues: None

---

## Open Questions for Next AI Session

| # | Question | Raised by | Status |
|---|----------|-----------|--------|
| Q1 | Is v1 JSON array format safe for production paper run? | Copilot | Answered: Yes (Claude + DeepSeek) |
| Q2 | Dual-format Streamlit reader — now or after smoke? | Copilot | Answered: After smoke (Claude + DeepSeek) |
| Q3 | Is current field set sufficient for dashboard? | Copilot | Partial: add `model_version` (Claude) |
| Q4 | Edge cases in atomic write under high trade rate? | Copilot | Answered: not a blocker at 1000 limit (Claude + DeepSeek) |
| Q5 | Confirm `unrealized_pnl` calculation logic via paper_positions | Copilot | Pending Kimi review |
| Q6 | Should JSONL migration be a separate PR or same branch? | — | Pending |
