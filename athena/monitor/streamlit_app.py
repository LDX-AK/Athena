"""
athena/monitor/streamlit_app.py — Athena Visual Dashboard

Run:
  python -m streamlit run athena/monitor/streamlit_app.py
"""

import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# --- Paths ---------------------------------------------------------------------
LIVE_STATS_PATH = Path("data/live_stats.json")
TRADE_HISTORY_PATH = Path("data/trade_history.json")
OVERRIDES_PATH = Path("data/dashboard_overrides.json")
SAVED_PARAMS_PATH = Path("data/saved_params.json")

# --- Page ----------------------------------------------------------------------
st.set_page_config(
    page_title="Athena Control Deck",
    page_icon="A",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
:root {
  --bg-1: #f6f8fb;
  --bg-2: #eef4ff;
  --ink: #12263a;
  --muted: #45617d;
  --good: #1f9d66;
  --bad: #d64545;
  --accent: #0b6cff;
  --card: #ffffff;
  --line: #d8e2f0;
}
.stApp {
  background:
    radial-gradient(1000px 500px at 100% -10%, #d7e7ff 0%, transparent 60%),
    radial-gradient(900px 450px at -10% 110%, #c7f2e6 0%, transparent 55%),
    linear-gradient(160deg, var(--bg-1), var(--bg-2));
}
.block-container { padding-top: 1.2rem; }
h1, h2, h3 { color: var(--ink); letter-spacing: .2px; }
.metric-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 12px 14px;
  box-shadow: 0 6px 18px rgba(13, 44, 90, 0.06);
}
.mono {
  font-family: "Consolas", "Courier New", monospace;
  color: var(--muted);
  font-size: 0.9rem;
}
.kbd {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 2px 8px;
  background: #fff;
}
/* Toggle hit-area highlight */
[data-testid="stToggle"] {
  background: #eef4ff;
  border: 1px solid #b0c8f0;
  border-radius: 10px;
  padding: 8px 14px;
  transition: background 0.15s;
}
[data-testid="stToggle"]:hover {
  background: #ddeaff;
  border-color: #5590d0;
}
</style>
""",
    unsafe_allow_html=True,
)


# --- IO helpers ----------------------------------------------------------------
def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _write_json(path: Path, payload) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_stats() -> dict:
    return _read_json(
        LIVE_STATS_PATH,
        {
            "balance": 10_000.0,
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "open_positions": 0,
            "rolling_sharpe_24h": 0.0,
            "vol_regime": 0.5,
            "sentiment": 0.0,
            "lgbm_weight": 0.70,
            "sentiment_weight": 0.30,
            "sentiment_enabled": True,
            "rl_enabled": False,
            "mtf_filter": True,
            "model_version": "unknown",
            "last_signal_symbol": None,
            "last_signal_direction": 0,
            "feature_skips": 0,
            "risk_blocks": 0,
            "size_blocks": 0,
            "orders_opened": 0,
            "signals_seen": 0,
            "batches_seen": 0,
            "last_mtf_reason": "not_checked",
            "last_risk_reason": "not_checked",
            "last_size_reason": "not_checked",
            "runtime_status": "unknown",
            "mtf_blocks_history": [],
            "risk_blocks_history": [],
            "size_blocks_history": [],
            "orders_opened_history": [],
            "runtime_action_counts": {},
        },
    )


def load_trades() -> pd.DataFrame:
    raw = _read_json(TRADE_HISTORY_PATH, [])
    if not isinstance(raw, list):
        return pd.DataFrame()
    if not raw:
        return pd.DataFrame()
    frame = pd.DataFrame(raw)
    if "timestamp" in frame.columns:
        # Normalize to naive UTC so horizon comparisons are always valid.
        frame["ts"] = pd.to_datetime(
            frame["timestamp"], unit="s", errors="coerce", utc=True
        ).dt.tz_convert(None)
    return frame


def load_overrides() -> dict:
    raw = _read_json(OVERRIDES_PATH, {})
    return raw if isinstance(raw, dict) else {}


def save_overrides(payload: dict) -> bool:
    payload = dict(payload)
    payload["updated_at"] = int(time.time())
    return _write_json(OVERRIDES_PATH, payload)


def apply_preset(name: str) -> bool:
    if name == "conservative":
        payload = {
            "lgbm_weight": 0.75,
            "sentiment_weight": 0.25,
            "sentiment_enabled": True,
            "mtf_filter_enabled": True,
            "min_confidence": 0.55,
            "preset": "conservative",
        }
    elif name == "balanced":
        payload = {
            "lgbm_weight": 0.65,
            "sentiment_weight": 0.35,
            "sentiment_enabled": True,
            "mtf_filter_enabled": True,
            "min_confidence": 0.45,
            "preset": "balanced",
        }
    else:
        payload = {
            "lgbm_weight": 0.55,
            "sentiment_weight": 0.45,
            "sentiment_enabled": True,
            "mtf_filter_enabled": False,
            "min_confidence": 0.35,
            "preset": "aggressive",
        }
    return save_overrides(payload)


def get_active_mode(overrides_payload: dict) -> str:
    preset = str(overrides_payload.get("preset", "")).strip().lower()
    if preset in {"conservative", "balanced", "aggressive"}:
        return preset.title()
    if overrides_payload:
        return "Custom"
    return "Default"


def list_saved_params() -> list:
    raw = _read_json(SAVED_PARAMS_PATH, {})
    if not isinstance(raw, dict):
        return []
    return sorted(raw.keys())


def save_named_params(name: str, payload: dict) -> bool:
    raw = _read_json(SAVED_PARAMS_PATH, {})
    if not isinstance(raw, dict):
        raw = {}
    raw[name] = dict(payload)
    raw[name]["saved_at"] = int(time.time())
    return _write_json(SAVED_PARAMS_PATH, raw)


def load_named_params(name: str) -> dict:
    raw = _read_json(SAVED_PARAMS_PATH, {})
    if not isinstance(raw, dict):
        return {}
    entry = dict(raw.get(name, {}))
    entry.pop("saved_at", None)
    return entry


# --- Data ----------------------------------------------------------------------
stats = load_stats()
trades = load_trades()
overrides = load_overrides()

# --- Header --------------------------------------------------------------------
header_left, header_right = st.columns([3, 2])
with header_left:
    st.title("Athena Control Deck")
    st.caption(
        f"Updated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"Model: {stats.get('model_version', 'unknown')}"
    )
with header_right:
    st.markdown(
        '<div class="metric-card"><span class="mono">Live files:</span><br>'
        f'<span class="kbd">{LIVE_STATS_PATH}</span> '
        f'<span class="kbd">{TRADE_HISTORY_PATH}</span></div>',
        unsafe_allow_html=True,
    )

# --- Top metrics ---------------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Balance", f"${stats.get('balance', 0):,.2f}", delta=f"${stats.get('total_pnl', 0):+.2f}")
with c2:
    st.metric("Daily PnL", f"${stats.get('daily_pnl', 0):+.2f}")
with c3:
    st.metric("Win Rate", f"{100 * stats.get('win_rate', 0):.1f}%", delta=f"{stats.get('total_trades', 0)} trades")
with c4:
    st.metric("Sharpe 24h", f"{stats.get('rolling_sharpe_24h', 0):.2f}")
with c5:
    st.metric("Open Positions", f"{stats.get('open_positions', 0)}")

st.divider()

# --- Charts --------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Equity & PnL")
    horizon = st.selectbox("Horizon", ["All", "24h", "6h", "1h"], index=1)
    trades_window = trades.copy()
    if not trades_window.empty and "ts" in trades_window.columns and horizon != "All":
        now = pd.Timestamp.now(tz="UTC").tz_localize(None)
        if horizon == "24h":
            cutoff = now - pd.Timedelta(hours=24)
        elif horizon == "6h":
            cutoff = now - pd.Timedelta(hours=6)
        else:
            cutoff = now - pd.Timedelta(hours=1)
        trades_window = trades_window[trades_window["ts"] >= cutoff]

    if not trades_window.empty and "balance" in trades_window.columns and "ts" in trades_window.columns:
        equity = trades_window[["ts", "balance"]].dropna().set_index("ts")
        st.line_chart(equity, height=280, width="stretch")
    else:
        st.info("No closed trades in selected horizon yet.")

    if not trades_window.empty and "pnl" in trades_window.columns and "ts" in trades_window.columns:
        pnl = trades_window[["ts", "pnl"]].dropna().set_index("ts")
        st.bar_chart(pnl, height=180, width="stretch")

with right:
    st.subheader("Market Pulse")
    sentiment = float(stats.get("sentiment", 0.0))
    vol_regime = float(stats.get("vol_regime", 0.5))

    sent_label = "Positive" if sentiment > 0.2 else ("Negative" if sentiment < -0.2 else "Neutral")
    st.metric("Sentiment", f"{sentiment:+.3f}", delta=sent_label)

    regime_label = "HOT" if vol_regime > 0.75 else ("QUIET" if vol_regime < 0.25 else "NORMAL")
    st.metric("Vol Regime", f"{vol_regime:.2f}", delta=regime_label)

    signal_dir = int(stats.get("last_signal_direction", 0) or 0)
    signal_text = "LONG" if signal_dir > 0 else ("SHORT" if signal_dir < 0 else "HOLD")
    st.metric("Last Signal", signal_text, delta=str(stats.get("last_signal_symbol") or "-"))

st.divider()

# --- Tabs ----------------------------------------------------------------------
tab_trades, tab_controls, tab_runtime = st.tabs(["Recent Trades", "Controls", "Runtime Status"])

with tab_trades:
    st.subheader("Latest Trades")
    if trades.empty:
        st.info("Trades file is empty right now.")
    else:
        view = trades.copy()
        if "direction" in view.columns:
            view["direction"] = view["direction"].map({1: "LONG", -1: "SHORT"}).fillna(view["direction"])
        if "pnl" in view.columns:
            view["pnl"] = view["pnl"].map(lambda x: f"{x:+.2f}" if pd.notna(x) else "")
        cols = [c for c in ["ts", "symbol", "exchange", "direction", "result", "pnl", "balance"] if c in view.columns]
        st.dataframe(view[cols].tail(50).iloc[::-1], width="stretch", hide_index=True)

with tab_controls:
    st.subheader("Live Overrides")
    st.caption("These controls write to data/dashboard_overrides.json and are applied by runtime every ~2s.")

    st.markdown(f"**Active Mode:** `{get_active_mode(overrides)}`")

    p1, p2, p3 = st.columns(3)
    with p1:
        if st.button("Preset: Conservative", use_container_width=True):
            if apply_preset("conservative"):
                st.toast("Conservative preset applied")
                st.rerun()
            else:
                st.error("Failed to write preset.")
    with p2:
        if st.button("Preset: Balanced", use_container_width=True):
            if apply_preset("balanced"):
                st.toast("Balanced preset applied")
                st.rerun()
            else:
                st.error("Failed to write preset.")
    with p3:
        if st.button("Preset: Aggressive", use_container_width=True):
            if apply_preset("aggressive"):
                st.toast("Aggressive preset applied")
                st.rerun()
            else:
                st.error("Failed to write preset.")

    st.markdown("### Parameters")

    with st.container(border=True):
        st.markdown("**LGBM weight**")
        lgbm_weight = st.slider(
            "LGBM weight",
            min_value=0.0,
            max_value=1.0,
            value=float(overrides.get("lgbm_weight", stats.get("lgbm_weight", 0.70))),
            step=0.05,
            label_visibility="collapsed",
        )
        mm_l, mm_c, mm_r = st.columns([1, 4, 1])
        with mm_l:
            st.caption("0.00")
        with mm_r:
            st.caption("1.00")
        st.caption(f"Current: {lgbm_weight:.2f}")

    with st.container(border=True):
        st.markdown("**Min confidence**")
        min_confidence = st.slider(
            "Min confidence",
            min_value=0.05,
            max_value=0.95,
            value=float(overrides.get("min_confidence", 0.45)),
            step=0.01,
            label_visibility="collapsed",
        )
        mm2_l, mm2_c, mm2_r = st.columns([1, 4, 1])
        with mm2_l:
            st.caption("0.05")
        with mm2_r:
            st.caption("0.95")
        st.caption(f"Current: {min_confidence:.2f}")

    sentiment_weight = round(1.0 - lgbm_weight, 2)
    st.markdown(f"**Sentiment weight (derived):** `{sentiment_weight:.2f}`")

    with st.container(border=True):
        st.markdown("**Feature Toggles** — click the switch to enable/disable")
        t1, t2 = st.columns(2)
        with t1:
            sentiment_enabled = st.toggle(
                "Sentiment enabled",
                value=bool(overrides.get("sentiment_enabled", stats.get("sentiment_enabled", True))),
            )
        with t2:
            mtf_filter_enabled = st.toggle(
                "MTF filter enabled",
                value=bool(overrides.get("mtf_filter_enabled", stats.get("mtf_filter", True))),
            )

    st.markdown("### Save / Load Profile")
    with st.container(border=True):
        sv1, sv2 = st.columns([3, 1])
        with sv1:
            save_name = st.text_input("Profile name", placeholder="e.g. my_conservative")
        with sv2:
            st.write("")
            if st.button("\U0001f4be Save", use_container_width=True, key="btn_save_params"):
                if save_name.strip():
                    payload_to_save = {
                        "lgbm_weight": float(lgbm_weight),
                        "sentiment_weight": float(sentiment_weight),
                        "sentiment_enabled": bool(sentiment_enabled),
                        "mtf_filter_enabled": bool(mtf_filter_enabled),
                        "min_confidence": float(min_confidence),
                    }
                    if save_named_params(save_name.strip(), payload_to_save):
                        st.toast(f"Profile '{save_name.strip()}' saved")
                        st.rerun()
                    else:
                        st.error("Failed to save profile.")
                else:
                    st.warning("Enter a profile name first.")
        saved_names = list_saved_params()
        if saved_names:
            ld1, ld2 = st.columns([3, 1])
            with ld1:
                load_name = st.selectbox("Load profile", saved_names, key="sel_load_params")
            with ld2:
                st.write("")
                if st.button("\U0001f4c2 Load", use_container_width=True, key="btn_load_params"):
                    if not load_name:
                        st.warning("No profile selected.")
                    else:
                        loaded = load_named_params(load_name)
                        if loaded:
                            loaded["preset"] = "custom"
                            if save_overrides(loaded):
                                st.toast(f"Profile '{load_name}' loaded")
                                st.rerun()
                            else:
                                st.error("Failed to apply loaded profile.")
                        else:
                            st.warning("Profile is empty.")
        else:
            st.caption("No saved profiles yet. Type a name above and click Save.")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Apply overrides", use_container_width=True):
            payload = {
                "lgbm_weight": float(lgbm_weight),
                "sentiment_weight": float(sentiment_weight),
                "sentiment_enabled": bool(sentiment_enabled),
                "mtf_filter_enabled": bool(mtf_filter_enabled),
                "min_confidence": float(min_confidence),
                "preset": "custom",
            }
            if save_overrides(payload):
                st.toast("Custom overrides saved")
                st.rerun()
            else:
                st.error("Failed to write overrides file.")

    with b2:
        if st.button("Reset overrides", use_container_width=True):
            if OVERRIDES_PATH.exists():
                OVERRIDES_PATH.unlink(missing_ok=True)
            st.toast("Overrides reset to defaults")
            st.rerun()

with tab_runtime:
    st.subheader("Module State")
    flags = {
        "Sentiment": bool(stats.get("sentiment_enabled", True)),
        "RL Shield": bool(stats.get("rl_enabled", False)),
        "MTF Filter": bool(stats.get("mtf_filter", True)),
        "Kelly": bool(stats.get("kelly_enabled", True)),
    }
    for name, state in flags.items():
        st.write(("ON  " if state else "OFF ") + name)

    st.markdown("### Pipeline Diagnostics")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        st.metric("Signals", f"{int(stats.get('signals_seen', 0))}")
    with d2:
        st.metric("MTF Blocks", f"{int(stats.get('mtf_blocks', 0))}")
    with d3:
        st.metric("Risk Blocks", f"{int(stats.get('risk_blocks', 0))}")
    with d4:
        st.metric("Orders Opened", f"{int(stats.get('orders_opened', 0))}")

    e1, e2, e3 = st.columns(3)
    with e1:
        st.metric("Feature Skips", f"{int(stats.get('feature_skips', 0))}")
    with e2:
        st.metric("Size Blocks", f"{int(stats.get('size_blocks', 0))}")
    with e3:
        st.metric("Runtime Status", str(stats.get("runtime_status", "unknown")))

    with st.container(border=True):
        st.markdown("**Last Decisions / Reasons**")
        st.write(f"`MTF:` {stats.get('last_mtf_reason', 'not_checked')}")
        st.write(f"`Risk:` {stats.get('last_risk_reason', 'not_checked')}")
        st.write(f"`Size:` {stats.get('last_size_reason', 'not_checked')}")
        drift_alerts = stats.get("drift_alerts") or []
        if drift_alerts:
            st.write(f"`Drift alerts:` {', '.join(map(str, drift_alerts))}")
        runtime_counts = stats.get("runtime_action_counts") or {}
        if runtime_counts:
            st.json(runtime_counts)

    if stats.get("mtf_blocks_history") or stats.get("risk_blocks_history"):
        st.subheader("Filter blocks over time")
        blocks_df = pd.DataFrame(
            {
                "mtf": stats.get("mtf_blocks_history", []),
                "risk": stats.get("risk_blocks_history", []),
            }
        )
        if not blocks_df.empty:
            st.area_chart(blocks_df, height=180, width="stretch")
            st.caption("Shows which gate is rejecting more signals in the recent runtime window.")

    st.markdown("### Active Overrides")
    if overrides:
        st.json(overrides)
    else:
        st.info("No runtime overrides file found.")

    st.markdown("### Runtime Health")
    st.caption(
        "Shows how many seconds ago the bot last wrote live_stats.json to disk. "
        "GOOD = data is fresh (<10 s). "
        "WARNING = slight lag (10–30 s) — bot may be busy or slow. "
        "STALE = bot probably stopped or crashed (>30 s)."
    )
    stats_age_sec = None
    if LIVE_STATS_PATH.exists():
        stats_age_sec = max(0.0, time.time() - LIVE_STATS_PATH.stat().st_mtime)

    if stats_age_sec is None:
        st.error("live_stats.json not found — bot is not running or has never been started.")
    else:
        if stats_age_sec <= 10:
            health = "GOOD"
        elif stats_age_sec <= 30:
            health = "WARNING"
        else:
            health = "STALE"
        st.metric("Telemetry lag", f"{stats_age_sec:.1f}s", delta=health)
        if health != "GOOD":
            st.warning("Data feed lag detected. For live mode keep stable wired fiber internet.")

    st.divider()
    _cl, _cr = st.columns([1, 2])
    with _cl:
        if st.button("\U0001f5d1 Clear trades history", use_container_width=True, type="secondary"):
            if _write_json(TRADE_HISTORY_PATH, []):
                st.toast("Trade history cleared.")
                st.rerun()
            else:
                st.error("Failed to clear trade history.")

# --- Sidebar -------------------------------------------------------------------
with st.sidebar:
    st.header("Display")
    refresh_sec = st.slider("Auto refresh (sec)", min_value=2, max_value=30, value=5, step=1)
    if st.button("Refresh now", use_container_width=True):
        st.rerun()

    st.divider()
    st.caption("Tip: for stable live operation, keep using wired fiber internet.")

# --- Auto refresh --------------------------------------------------------------
time.sleep(refresh_sec)
st.rerun()
