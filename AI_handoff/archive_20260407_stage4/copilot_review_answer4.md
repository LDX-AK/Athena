# Copilot Review: answer4

Date: 2026-04-02
Reviewer: GitHub Copilot (GPT-5.3-Codex)

## Goal
Assess proposal in answer4 and align it with current Athena runtime/dashboard contracts to define the safest Stage 4 strategy.

## Verdict
Proposal quality: good architecture, not ready for direct drop-in.

Final verdict: **7/10**.

Why:
- Strong async writer concept, buffering, and atomic stats writes.
- But current proposal conflicts with existing Streamlit file contracts and timestamp parsing.
- Needs contract alignment before implementation to avoid telemetry regressions.

## What Is Strong in answer4
1. Correct direction for non-blocking telemetry in runtime loop.
2. Atomic write pattern for live stats (tmp + replace) is robust.
3. Trade history as append-only stream is scalable.
4. Explicit graceful shutdown and flush intent is correct.

## Critical Gaps vs Current Codebase
1. Path and format mismatch with current dashboard readers.
- answer4 proposes:
  - `data/runtime/live_stats.json`
  - `data/runtime/trade_history.jsonl`
- current Streamlit reads:
  - `data/live_stats.json`
  - `data/trade_history.json` (JSON array)

2. Timestamp contract mismatch.
- answer4 examples use ISO timestamps (`ts`).
- current Streamlit expects `timestamp` in epoch seconds for `pd.to_datetime(..., unit='s')`.

3. MTF config naming drift in narrative snippets.
- answer4 text still mentions `MTF_TIMEFRAME` style keys.
- project currently uses lower-case runtime config keys (`mtf_timeframe`, etc.).

4. Dependency gap.
- answer4 uses `aiofiles`, but it is not currently declared in `requirements.txt`.

## Practical Risks If Applied As-Is
1. Empty/incorrect dashboard panels due to path and schema mismatch.
2. Broken equity curve parsing due to timestamp format mismatch.
3. Runtime writes may work, while UI appears stale or broken (false negative in ops).

## Recommended Strategy (Best Joint Path)
1. Introduce `StatsWriter` in runtime with backward-compatible output first:
- write `data/live_stats.json` (atomic overwrite)
- write `data/trade_history.json` (JSON array append with bounded size, e.g. last N records)
- keep existing Streamlit unchanged for first rollout

2. After stable paper run, do format migration to JSONL in a controlled step:
- add optional JSONL writer in parallel
- update Streamlit to support both JSON array and JSONL
- then switch default to JSONL

3. Enforce single telemetry contract in config:
- add `monitor` section with paths and flush interval
- make both writer and Streamlit read from same config source

4. Lifecycle safety in core:
- start writer before main loop
- ensure `stop()` + final flush in `try/finally`
- log writer failures as warnings, never crash trading loop

5. Dependency decision:
- Phase 1: use `asyncio.to_thread` + stdlib I/O (no new dependency)
- Phase 2: add `aiofiles` only if profiling shows benefit

## Acceptance Criteria for Stage 4
1. During paper mode, `live_stats.json` updates continuously without blocking.
2. Closed trades appear in history file and are rendered in Streamlit.
3. No runtime loop interruption when file write errors occur.
4. Graceful stop always flushes pending buffer.
5. Unit/integration smoke confirms dashboard parsing still works.

## Suggested Next Implementation Split
1. PR-A: Minimal compatible writer + core integration + smoke test.
2. PR-B: Streamlit dual-reader (JSON + JSONL) + optional migration path.
3. PR-C: Contract cleanup and docs update in change history and handoff package.
