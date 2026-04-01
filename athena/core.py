"""
athena/core.py — Athena AI-Bot v2 главный цикл

Запуск:
  python -m athena --mode paper      # бумажная торговля
  python -m athena --mode live       # реальная торговля
  python -m athena --mode backtest   # бэктест
  python -m athena --mode train      # обучение LightGBM
  python -m athena --mode train_rl   # обучение PPO Shield

Архитектура потока данных:
  AthenaFetcher (WebSocket)
        ↓ batch {ohlcv, orderbook}
  AthenaSentiment (CSV/API)
        ↓ sentiment {score, volume, trend}
  AthenaEngineer
        ↓ ~60 features
  SignalFusion (LightGBM 70% + Sentiment 30%)
        ↓ AthenaSignal {direction, confidence}
  AthenaRisk.check()
        ↓ AthenaDecision {approved, size_usd}
  AthenaShield.get_size_multiplier()  ← PPO (если включён)
        ↓ final_size_usd
  AthenaRouter.execute()
        ↓ result {pnl, ...}
  AthenaRisk.update() + AthenaDashboard.update()
"""

import asyncio
import argparse
import logging
import numpy as np
from athena.data.fetcher    import AthenaFetcher
from athena.data.sentiment  import AthenaSentiment
from athena.features.engineer import AthenaEngineer
from athena.model.signal    import AthenaTrainer
from athena.model.fusion    import SignalFusion
from athena.model.rl_shield import AthenaShield
from athena.risk.manager    import AthenaRisk
from athena.execution.router import AthenaRouter
from athena.monitor.dashboard import AthenaDashboard
from athena.config          import ATHENA_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ATHENA » %(message)s"
)
logger = logging.getLogger("athena.core")


async def run(mode: str):
    cfg   = ATHENA_CONFIG
    flags = cfg.get("flags", {})

    logger.info("⚡ ═══════════════════════════════════════")
    logger.info("⚡  ATHENA AI-BOT v2  |  Starting up...")
    logger.info(f"⚡  Mode:      {mode.upper()}")
    logger.info(f"⚡  Exchanges: {list(cfg['exchanges'].keys())}")
    logger.info(f"⚡  Symbols:   {cfg['symbols']}")
    logger.info(f"⚡  Sentiment: {'ON' if flags.get('SENTIMENT_ENABLED') else 'OFF'}")
    logger.info(f"⚡  RL Shield: {'ON' if flags.get('RL_ENABLED') else 'OFF'}")
    logger.info("⚡ ═══════════════════════════════════════")

    # ── Инициализация всех компонентов ────────────────────────
    fetcher   = AthenaFetcher(cfg["exchanges"])
    sentiment = AthenaSentiment(cfg)
    engineer  = AthenaEngineer()
    risk      = AthenaRisk(cfg["risk"])
    fusion    = SignalFusion(cfg)
    shield    = AthenaShield(cfg, risk_manager=risk)
    router    = AthenaRouter(cfg["exchanges"], mode=mode)
    dashboard = AthenaDashboard(risk)

    # ── Режимы запуска ────────────────────────────────────────
    if mode == "train":
        await _train_lgbm(fetcher, engineer, cfg)
        return

    if mode == "train_rl":
        shield.train(total_timesteps=100_000)
        return

    if mode == "backtest":
        await _backtest(fetcher, engineer, sentiment, cfg)
        return

    # ── Основной торговый цикл (paper / live) ─────────────────
    logger.info(f"🔄 Запуск торгового цикла [{mode.upper()}]...")

    async for batch in fetcher.stream():
        try:
            symbol   = batch.get("symbol", "")
            exchange = batch.get("exchange", "")

            # 1. Получаем live sentiment (из кэша или API)
            sent_data = await sentiment.get_live(symbol)
            batch["sentiment"] = sent_data

            # 2. Строим фичи (~60 признаков)
            features = engineer.transform(batch)
            if features is None:
                continue

            # Обновляем состояние риск-менеджера для PPO
            risk.current_vol_regime  = features.get("vol_regime", 0.5)
            risk.current_sentiment   = sent_data.get("score", 0.0)

            # 3. Hybrid Signal Fusion
            signal = fusion.predict(features, sent_data)

            # 4. Проверка риск-менеджера
            decision = risk.check(signal)
            if not decision.approved:
                logger.debug(f"⛔ {symbol}: {decision.reason}")
                continue

            # 5. RL Shield — корректируем размер позиции
            rl_state   = risk.get_ppo_state()
            shield_dec = shield.get_size_multiplier(rl_state)
            final_size = decision.adjusted_size_usd * shield_dec.size_multiplier

            if final_size < 10.0:
                logger.debug(f"⛔ Размер слишком мал: ${final_size:.2f}")
                continue

            # 6. Вычисляем SL/TP и исполняем
            sl, tp = risk.calculate_sl_tp(signal.price, signal.direction)
            result = await router.execute(signal, final_size, sl, tp)

            # 7. Обновляем состояние
            risk.update(result)
            dashboard.update(result)

        except Exception as e:
            logger.error(f"Ошибка в цикле [{symbol}]: {e}", exc_info=True)


async def _train_lgbm(fetcher, engineer, cfg):
    """Обучение LightGBM модели."""
    logger.info("🧠 Загружаем данные для обучения...")
    data = await fetcher.fetch_historical("binance", "BTC/USDT", "1m", limit=259200)
    trainer = AthenaTrainer(engineer, cfg)
    trainer.train(data, save_path=cfg["model_path"])


async def _backtest(fetcher, engineer, sentiment, cfg):
    """Бэктест с sentiment."""
    from athena.backtest.runner import AthenaBacktest
    logger.info("📈 Загружаем данные для бэктеста...")
    data = await fetcher.fetch_historical("binance", "BTC/USDT", "1m", limit=50_000)
    bt   = AthenaBacktest(engineer, sentiment, cfg)
    bt.run(data)
