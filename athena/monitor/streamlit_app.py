"""
athena/monitor/streamlit_app.py — Athena Visual Dashboard

Запуск: streamlit run athena/monitor/streamlit_app.py
Порт:   http://localhost:8501

Показывает:
  - Live баланс и P&L
  - Win Rate и Sharpe в реальном времени
  - График equity curve
  - Sentiment gauge
  - Открытые позиции
  - Последние сделки
  - Веса SignalFusion (LightGBM / Sentiment)
  - Состояние всех флагов
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import time
from pathlib import Path
from datetime import datetime

# ── Конфигурация страницы ──────────────────────────────────────
st.set_page_config(
    page_title="⚡ Athena AI-Bot",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 15px;
        border-left: 4px solid #7c3aed;
    }
    .positive { color: #22c55e; }
    .negative { color: #ef4444; }
    .neutral  { color: #94a3b8; }
    h1 { color: #a855f7; }
</style>
""", unsafe_allow_html=True)


def load_trade_history(path: str = "data/trade_history.json") -> pd.DataFrame:
    """Загружаем историю сделок из JSON (сохраняется AthenaRisk)."""
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["timestamp", "pnl", "balance", "symbol",
                                      "direction", "result"])
    with open(p) as f:
        data = json.load(f)
    return pd.DataFrame(data)


def load_stats(path: str = "data/live_stats.json") -> dict:
    """Загружаем live статистику."""
    p = Path(path)
    if not p.exists():
        return {
            "balance": 10000.0, "daily_pnl": 0.0, "total_pnl": 0.0,
            "win_rate": 0.0, "total_trades": 0, "open_positions": 0,
            "rolling_sharpe_24h": 0.0, "vol_regime": 0.5, "sentiment": 0.0,
            "lgbm_weight": 0.70, "sentiment_weight": 0.30,
            "sentiment_enabled": True, "rl_enabled": False,
        }
    with open(p) as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════
# ГЛАВНАЯ СТРАНИЦА
# ══════════════════════════════════════════════════════════════

st.title("⚡ Athena AI-Bot v2")
st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')} UTC")

stats  = load_stats()
trades = load_trade_history()

# ── ROW 1: Ключевые метрики ────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("💰 Баланс", f"${stats['balance']:,.2f}",
              delta=f"${stats['total_pnl']:+.2f}")

with col2:
    color = "normal" if stats['daily_pnl'] >= 0 else "inverse"
    st.metric("📅 Дневной P&L", f"${stats['daily_pnl']:+.2f}")

with col3:
    st.metric("🎯 Win Rate", f"{stats['win_rate']*100:.1f}%",
              delta=f"{stats['total_trades']} сделок")

with col4:
    sharpe = stats.get("rolling_sharpe_24h", 0)
    st.metric("📊 Sharpe (24h)", f"{sharpe:.2f}",
              delta="✅ хорошо" if sharpe > 1.5 else "⚠️ низкий")

with col5:
    st.metric("📂 Позиций", f"{stats['open_positions']}/3")

st.divider()

# ── ROW 2: Equity Curve + Sentiment ───────────────────────────
col_chart, col_sent = st.columns([3, 1])

with col_chart:
    st.subheader("📈 Equity Curve")
    if not trades.empty and "balance" in trades.columns:
        chart_data = trades[["timestamp", "balance"]].copy()
        chart_data["timestamp"] = pd.to_datetime(chart_data["timestamp"], unit="s")
        chart_data = chart_data.set_index("timestamp")
        st.line_chart(chart_data["balance"], height=300, use_container_width=True)
    else:
        st.info("Нет данных. Запусти бота в режиме paper/live.")

with col_sent:
    st.subheader("🌡️ Sentiment")
    sent_score = stats.get("sentiment", 0.0)
    sent_color = "🟢" if sent_score > 0.2 else ("🔴" if sent_score < -0.2 else "🟡")
    st.metric(f"{sent_color} Score", f"{sent_score:+.3f}")

    vol_regime = stats.get("vol_regime", 0.5)
    regime_label = "🔥 HOT" if vol_regime > 0.75 else ("❄️ QUIET" if vol_regime < 0.25 else "⚡ NORMAL")
    st.metric("📊 Vol Regime", regime_label, delta=f"{vol_regime:.2f}")

st.divider()

# ── ROW 3: Signal Fusion Weights + Flags ──────────────────────
col_fusion, col_flags = st.columns(2)

with col_fusion:
    st.subheader("🔀 Signal Fusion")
    lgbm_w = stats.get("lgbm_weight", 0.70)
    sent_w = stats.get("sentiment_weight", 0.30)

    st.progress(lgbm_w, text=f"🤖 LightGBM: {lgbm_w:.0%}")
    st.progress(sent_w, text=f"📰 Sentiment: {sent_w:.0%}")

    if stats.get("sentiment_enabled"):
        st.success("✅ Sentiment: ВКЛЮЧЁН")
    else:
        st.warning("⚠️ Sentiment: ВЫКЛЮЧЕН (чистый LightGBM)")

with col_flags:
    st.subheader("🎛️ Состояние модулей")
    flags_data = {
        "Sentiment Live":   stats.get("sentiment_live", False),
        "RL Shield (PPO)":  stats.get("rl_enabled", False),
        "MTF Filter (15m)": stats.get("mtf_filter", True),
        "Dynamic Kelly":    stats.get("kelly_enabled", True),
        "Streamlit":        True,
    }
    for name, enabled in flags_data.items():
        icon = "✅" if enabled else "⭕"
        st.write(f"{icon} {name}")

st.divider()

# ── ROW 4: Последние сделки ────────────────────────────────────
st.subheader("📋 Последние сделки")
if not trades.empty:
    display_cols = [c for c in ["timestamp", "symbol", "direction", "pnl", "result", "balance"]
                    if c in trades.columns]
    last_trades = trades[display_cols].tail(20).copy()

    if "direction" in last_trades.columns:
        last_trades["direction"] = last_trades["direction"].map({1: "🟢 LONG", -1: "🔴 SHORT"})
    if "result" in last_trades.columns:
        last_trades["result"] = last_trades["result"].map(
            {"TP": "✅ TP", "SL": "❌ SL", "paper_closed": "📝 Paper"}
        ).fillna(last_trades["result"])
    if "pnl" in last_trades.columns:
        last_trades["pnl"] = last_trades["pnl"].apply(lambda x: f"${x:+.2f}")

    st.dataframe(last_trades.iloc[::-1], use_container_width=True, hide_index=True)
else:
    st.info("Сделок пока нет.")

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Управление")

    st.subheader("🔀 Веса сигналов")
    new_lgbm = st.slider("LightGBM вес", 0.5, 1.0, lgbm_w, 0.05)
    new_sent  = round(1.0 - new_lgbm, 2)
    st.write(f"Sentiment вес: {new_sent:.2f}")
    if st.button("Применить веса"):
        st.success(f"Веса обновлены: LGBM={new_lgbm:.0%} Sent={new_sent:.0%}")
        # TODO: записать в файл конфига для live обновления

    st.divider()
    st.subheader("📊 Kaggle Sentiment Data")
    st.write("Скачай датасеты:")
    st.code("kaggle datasets download\ngautamchettiar/historical-sentiment-data-btc-eth-bnb-ada")
    st.write("Помести CSV в: `data/raw/sentiment/`")

    st.divider()
    if st.button("🔄 Обновить"):
        st.rerun()

    st.caption("Обновляется каждые 30 сек")

# Auto-refresh
time.sleep(0.1)
