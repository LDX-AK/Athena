"""
athena/config.py — Единая конфигурация Athena AI-Bot v2

Все флаги включения/выключения модулей здесь.
Меняй параметры тут — не трогай логику в других файлах.
"""

import os
from dotenv import load_dotenv
load_dotenv()

ATHENA_CONFIG = {

    # ─── БИРЖИ ────────────────────────────────────────────────
    "exchanges": {
        "binance": {
            "apiKey": os.getenv("BINANCE_API_KEY", ""),
            "secret": os.getenv("BINANCE_SECRET", ""),
            "options": {"defaultType": "future"},
        },
        "bybit": {
            "apiKey": os.getenv("BYBIT_API_KEY", ""),
            "secret": os.getenv("BYBIT_SECRET", ""),
        },
        "okx": {
            "apiKey": os.getenv("OKX_API_KEY", ""),
            "secret": os.getenv("OKX_SECRET", ""),
            "password": os.getenv("OKX_PASSPHRASE", ""),
        },
    },

    # ─── ТОРГОВЫЕ ПАРЫ И ТАЙМФРЕЙМ ────────────────────────────
    "symbols":    ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
    "timeframe":  "1m",
    "tf_filter":  "15m",   # старший таймфрейм для фильтрации тренда
    "mtf_timeframe": "15m",
    "mtf_min_trend": 0.0015,
    "mtf_min_higher_candles": 12,

    # ─── ПУТИ К МОДЕЛЯМ ───────────────────────────────────────
    "model_path":          "athena/model/athena_brain.pkl",
    "rl_model_path":       "athena/model/athena_shield_ppo",
    "sentiment_csv_path":  "data/raw/sentiment",   # Kaggle CSV сюда

    # ══════════════════════════════════════════════════════════
    # ГЛАВНЫЕ ПЕРЕКЛЮЧАТЕЛИ — включай/выключай модули
    # ══════════════════════════════════════════════════════════
    "flags": {
        # Sentiment слой
        "SENTIMENT_ENABLED":      True,   # общий выключатель sentiment
        "SENTIMENT_LIVE_ENABLED": False,  # CryptoPanic API в live режиме
        "SENTIMENT_BACKTEST":     True,   # использовать CSV в бэктесте

        # Hybrid Signal веса (должны давать сумму 1.0)
        "LGBM_WEIGHT":      0.70,   # вес LightGBM сигнала
        "SENTIMENT_WEIGHT": 0.30,   # вес Sentiment сигнала

        # Multi-timeframe фильтр
        "MTF_FILTER_ENABLED": True,  # фильтр по 15m тренду

        # RL Risk Agent
        "RL_ENABLED":       False,  # PPO поверх риск-менеджера
        "RL_RETRAIN_EVERY": 100,    # переобучать каждые N сделок

        # Дашборд
        "STREAMLIT_ENABLED": True,
        "GRAFANA_ENABLED":   True,
    },

    # ─── РИСК-МЕНЕДЖМЕНТ ──────────────────────────────────────
    "risk": {
        "max_position_pct":        0.02,   # 2% депозита на сделку
        "max_daily_drawdown_pct":  0.05,   # стоп при -5% за день
        "min_confidence":          0.65,   # минимальный порог сигнала
        "cooldown_after_loss_sec": 300,    # пауза 5 мин после убытка
        "max_open_positions":      3,
        "stop_loss_pct":           0.003,  # SL 0.3%
        "take_profit_pct":         0.006,  # TP 0.6% (RR 1:2)
        # Dynamic Kelly (активен когда RL_ENABLED=False)
        "kelly_enabled":           True,
        "kelly_fraction":          0.25,   # консервативный Kelly (25%)
    },

    # ─── DRIFT-МОНИТОРИНГ ────────────────────────────────────
    "drift": {
        "enabled":              True,
        "window_trades":        30,
        "min_win_rate":         0.45,
        "min_profit_factor":    1.10,
        "min_sharpe":           0.70,
        "consecutive_alerts":   3,
        "winrate_drop":         0.10,
        "confidence_drop":      0.15,
        "sharpe_drop":          0.30,
        "volatility_multiplier": 2.0,
        "consecutive_losses":   5,
    },

    # ─── ПОЛИТИКА ПЕРЕОБУЧЕНИЯ ───────────────────────────────
    "retrain": {
        "enabled":                 True,
        "schedule_days":           10,
        "cooldown_hours":          24,
        "trigger_on_drift":        True,
        "dry_run":                 True,  # пока только логируем триггер, без auto-train
        "max_retrains_per_week":   3,
        "critical_alerts_required": 2,
        "emergency_bypass_enabled": True,
        "emergency_min_severity":   7,
        "emergency_cooldown_hours": 6,
    },

    # ─── ДАННЫЕ ───────────────────────────────────────────────
    "data": {
        "lookback_candles": 100,
        "orderbook_depth":  20,
        # Окна для multi-horizon фич (из DRW Kaggle решения)
        "windows": [5, 10, 15, 30, 60, 120],
    },

    # ─── МОНИТОРИНГ / ТЕЛЕМЕТРИЯ ─────────────────────────────
    "monitor": {
        "live_stats_path": "data/live_stats.json",
        "trade_history_path": "data/trade_history.json",
        "flush_interval_sec": 5,
        "max_history_trades": 1000,
    },

    # ─── ИНФРАСТРУКТУРА ───────────────────────────────────────
    "redis_url":   os.getenv("REDIS_URL",    "redis://localhost:6379"),
    "db_url":      os.getenv("DATABASE_URL", "postgresql://athena:athena@localhost:5432/athena"),
    "cryptopanic_api_key": os.getenv("CRYPTOPANIC_API_KEY", ""),
}
