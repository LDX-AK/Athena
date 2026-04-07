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
        "bitfinex": {
            "apiKey": os.getenv("BITFINEX_API_KEY", ""),
            "secret": os.getenv("BITFINEX_SECRET", ""),
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
    "training_timeframe": "1m",
    "runtime_timeframe": "1m",
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
        "MTF_FILTER_ENABLED": False,  # ВРЕМЕННО выкл — включить после обучения LightGBM

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
        "min_confidence":          0.45,   # минимальный порог сигнала (0.65 после обучения LightGBM)
        "cooldown_after_loss_sec": 300,    # пауза 5 мин после убытка
        "max_open_positions":      3,
        "stop_loss_pct":           0.003,  # SL 0.3%
        "take_profit_pct":         0.006,  # TP 0.6% (RR 1:2)
        # Dynamic Kelly (активен когда RL_ENABLED=False)
        "kelly_enabled":           True,
        "kelly_fraction":          0.25,   # консервативный Kelly (25%)
        # Runtime circuit breaker for regime breaks / model degradation
        "circuit_breaker_enabled": True,
        "circuit_breaker_window_trades": 20,
        "circuit_breaker_min_win_rate": 0.35,
        "circuit_breaker_min_sharpe": 0.0,
        "circuit_breaker_max_consecutive_losses": 5,
        "circuit_breaker_reduce_size_factor": 0.25,
        "circuit_breaker_hard_pause": False,
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
        "public_exchanges": ["binance", "bybit", "bitfinex"],
        "exchange_symbols": {
            "binance": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            "bybit": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            "bitfinex": ["BTC/USD", "ETH/USD", "SOL/USD"],
        },
        "lookback_candles": 200,
        "orderbook_depth":  20,
        # Окна для multi-horizon фич (из DRW Kaggle решения)
        "windows": [5, 10, 15, 30, 60, 120],
    },

    # ─── ОБУЧЕНИЕ / LABELING / FEATURE GATING ───────────────
    "training": {
        "labeling_mode": "atr",  # legacy | atr
        "label_lookahead": 10,
        "atr_period": 14,
        "atr_tp_mult": 1.0,
        "atr_sl_mult": 0.5,
        "save_feature_importance": True,
        # Safer default model capacity for the next 15m retrain cycle
        "model_params": {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 100,
            "subsample": 0.7,
            "colsample_bytree": 0.7,
            "class_weight": "balanced",
            "random_state": 42,
            "verbose": -1,
        },
        "walk_forward": {
            "train_months": ["2025-04", "2025-05"],
            "validation_months": ["2025-06"],
            "test_months": ["2025-07", "2025-08", "2025-09"],
        },
    },
    "feature_groups": {
        "price": True,
        "indicators": True,
        "orderbook": True,
        "orderflow": True,
        "multihorizon": True,
        "regime": True,
        "rolling": True,
        "volatility": True,
        "volume": True,
        "time": True,
        "sentiment": True,
    },

    # ─── SENTIMENT РЕЖИМЫ (взвешивание или macro-gate) ─────
    "sentiment": {
        "mode": "weighted",  # weighted | macro_gate
        "macro_horizon": "1h",
        "macro_min_samples": 4,
        "macro_buy_threshold": 0.08,
        "macro_sell_threshold": -0.08,
        "macro_neutral_policy": "pass",  # pass | block
    },

    # ─── STRATEGY FACTORY / ЭКСПЕРИМЕНТЫ ────────────────────
    "experiment": {
        "storage_path": "data/experiments",
        "walk_forward": {
            "train_months": ["2025-04", "2025-05"],
            "validation_months": ["2025-06"],
            "test_months": ["2025-07", "2025-08", "2025-09"],
        },
        "ablation": {
            "enabled": True,
            "scenarios": [
                "baseline",
                "no_rolling",
                "no_sentiment",
                "no_rolling_sentiment",
                "no_regime",
                "minimal",
            ],
        },
        "model_registry": {
            "max_versions": 50,
            "auto_save_best": True,
            "best_metric": "sharpe_ratio",
        },
    },

    # ─── МОНИТОРИНГ / ТЕЛЕМЕТРИЯ ─────────────────────────────
    "monitor": {
        "live_stats_path": "data/live_stats.json",
        "trade_history_path": "data/trade_history.json",
        "dashboard_overrides_path": "data/dashboard_overrides.json",
        "flush_interval_sec": 5,
        "max_history_trades": 1000,
    },

    # ─── ИНФРАСТРУКТУРА ───────────────────────────────────────
    "redis_url":   os.getenv("REDIS_URL",    "redis://localhost:6379"),
    "db_url":      os.getenv("DATABASE_URL", "postgresql://athena:athena@localhost:5432/athena"),
    "cryptopanic_api_key": os.getenv("CRYPTOPANIC_API_KEY", ""),
}
