# Athena Dashboard Package for Deepseek

## Goal
Provide Deepseek with the current dashboard state (screenshots + code + observed UX issues) to avoid duplicate redesign iterations.

## Included Assets
- Code files:
  - deepseek_package/code/streamlit_app.py
  - deepseek_package/code/core.py
  - deepseek_package/code/config.py
- Screenshots (current UI state):
  - deepseek_package/screenshots/capture_04032026_164601.jpg
  - deepseek_package/screenshots/capture_04032026_164629.jpg
  - deepseek_package/screenshots/capture_04032026_164715.jpg
  - deepseek_package/screenshots/capture_04032026_164737.jpg
  - deepseek_package/screenshots/capture_04032026_164819.jpg
  - deepseek_package/screenshots/capture_04032026_164902.jpg
  - deepseek_package/screenshots/capture_04032026_164925.jpg
- Runtime status report:
  - deepseek_package/health_report_2026-04-03_morning.md

## Current UX Problems (important)
- Sliders and toggles are still hard to see in dark/high-contrast usage.
- Borders were added, but not in the right places for visual clarity.
- Controls tab takes too much central screen space.
- Main title "Athena Control Deck" is oversized and wastes vertical space.
- Runtime Health explanatory block is too long/verbose for at-a-glance monitoring.

## Requested Layout Changes
1. Move Controls from tab into sidebar dropdown area (near Display/Refresh block).
2. Keep top area compact:
   - reduce title size,
   - preserve key file references,
   - minimize vertical padding.
3. Replace verbose Runtime Health section with compact top-right indicator:
   - format: Health - <seconds> - <GOOD|WARNING|STALE>
   - place inside top right status card near live files.
4. Keep internet note visible but concise, with stronger emphasis:
   - mention dedicated wired fiber line as preferred for live reliability.

## Functional Expectations
- Controls must still write runtime overrides into data/dashboard_overrides.json.
- Runtime should continue polling overrides every ~2s (already implemented in core.py).
- Apply/Reset/Save/Load parameter behavior must remain available after moving controls to sidebar.

## Suggested Modernization Ideas
- Add "connection quality" mini-panel per exchange (latency, last success, error streak).
- Add top sticky status strip with:
  - process alive,
  - telemetry lag,
  - active profile,
  - open positions.
- Add one-click mode pills (Safe / Balanced / Aggressive) in sidebar with active state highlight.
- Add incident timeline panel for warnings/errors with timestamps.
- Add compact mobile-first fallback layout for narrow screens.
- Add a lightweight "operator mode" that hides advanced controls by default.

## Note for Deepseek
Please review screenshots first to align visual changes with current pain points. Priority is clear control visibility, compact status readability, and reducing clutter in the main content area.
