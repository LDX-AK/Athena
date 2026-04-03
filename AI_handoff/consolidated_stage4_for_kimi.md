# Consolidated Stage 4 Package for Kimi

Date: 2026-04-02
Status: Implemented in codebase (backward-compatible v1)

## Purpose
This note consolidates:
1. Your Stage 4 recommendations (answer4 and answer4.1)
2. Copilot review constraints
3. What was actually implemented now in Athena

Goal: align on the best final strategy before optional v2 migration.

## Implemented Now (Stage 4 v1)
1. Added runtime telemetry writer:
- `stats_writer.py`
- Non-blocking periodic flush via asyncio task
- Atomic overwrite for live stats file
- Bounded history file behavior

2. Integrated writer lifecycle in runtime:
- started before stream loop
- guaranteed stop in `finally`
- trade events logged on paper close path
- live stats snapshots updated continuously

3. Added monitor config section:
- `live_stats_path`
- `trade_history_path`
- `flush_interval_sec`
- `max_history_trades`

4. Added tests:
- `test_stats_writer.py`

## Compatibility Choices (Intentional)
To avoid breaking existing dashboard, Stage 4 v1 keeps current contracts:
- `data/live_stats.json`
- `data/trade_history.json`
- `timestamp` in epoch seconds

No mandatory dependency was added (`asyncio.to_thread` used instead of aiofiles).

## Known Trade-offs in v1
1. History remains JSON array (not JSONL yet) for compatibility.
2. `unrealized_pnl` currently reported as `0.0` placeholder in runtime stats.
3. This is a safe intermediate step prioritizing stability in paper mode.

## Request for Your Review
Please evaluate if this v1 is acceptable as production-safe paper baseline, and advise on v2 migration timing:

1. Should we keep JSON-array history for one more iteration, then move to JSONL?
2. Do you recommend immediate dual-format reader in Streamlit (JSON + JSONL) now, or after paper soak?
3. Is current telemetry field set sufficient, or should we add/remove fields before v2 migration?
4. Any edge case concerns around atomic writes + bounded history under high event rates?

## Proposed Next Step (if approved)
Stage 4 v2 (optional, after your review):
1. JSONL migration for trade history
2. Streamlit dual-reader support
3. Optional aiofiles optimization only if profiling justifies

## Files Included for Review
- `answer4.md`
- `answer4.1.md`
- `copilot_review_answer4.md`
- `stats_writer.py`
- `core.py`
- `config.py`
- `test_stats_writer.py`
- `delta_summary.md`
- `change_history.md`
