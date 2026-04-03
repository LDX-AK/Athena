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
import logging
from athena.data.fetcher    import AthenaFetcher
from athena.data.sentiment  import AthenaSentiment
from athena.features.engineer import AthenaEngineer
from athena.model.signal    import AthenaTrainer
from athena.model.fusion    import SignalFusion
from athena.model.drift_monitor import AthenaDriftMonitor
from athena.model.retrain_policy import AthenaRetrainPolicy
from athena.model.rl_shield import AthenaShield
from athena.filters.mtf_gate import MTFGate
from athena.risk.manager    import AthenaRisk
from athena.execution.router import AthenaRouter
from athena.monitor.dashboard import AthenaDashboard
from athena.monitor.stats_writer import StatsWriter
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
    drift     = AthenaDriftMonitor(cfg)
    retrain   = AthenaRetrainPolicy(cfg)
    shield    = AthenaShield(cfg, risk_manager=risk)
    mtf_gate  = MTFGate(cfg)
    router    = AthenaRouter(cfg["exchanges"], mode=mode)
    dashboard = AthenaDashboard(risk)
    writer    = StatsWriter(cfg)

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
    await writer.start()
    last_signal_symbol = None
    last_signal_direction = 0
    last_drift_alerts = []
    mtf_block_count = 0

    try:
        async for batch in fetcher.stream():
            try:
                symbol   = batch.get("symbol", "")
                exchange = batch.get("exchange", "")

                live_stats = risk.stats()
                live_stats.update({
                    "balance": router.paper_balance if mode == "paper" else risk.total_balance,
                    "open_positions": len(router.paper_positions) if mode == "paper" else len(risk.open_positions),
                    "lgbm_weight": flags.get("LGBM_WEIGHT", 0.70),
                    "sentiment_weight": flags.get("SENTIMENT_WEIGHT", 0.30),
                    "sentiment_enabled": bool(flags.get("SENTIMENT_ENABLED", True)),
                    "rl_enabled": bool(flags.get("RL_ENABLED", False)),
                    "sentiment_live": bool(flags.get("SENTIMENT_LIVE_ENABLED", False)),
                    "mtf_filter": bool(flags.get("MTF_FILTER_ENABLED", True)),
                    "kelly_enabled": bool(cfg.get("risk", {}).get("kelly_enabled", True)),
                    "unrealized_pnl": 0.0,
                    "last_signal_symbol": last_signal_symbol,
                    "last_signal_direction": last_signal_direction,
                    "drift_alerts": last_drift_alerts,
                    "mtf_blocks": mtf_block_count,
                })
                writer.update_live_stats(live_stats)

                # 0. Для paper-режима сначала проверяем закрытия по SL/TP на текущей свече
                if mode == "paper" and batch.get("ohlcv"):
                    candle = batch["ohlcv"][-1]
                    high = float(candle[2])
                    low = float(candle[3])
                    closed_results = await router.check_paper_exits(symbol, exchange, low, high)
                    for closed in closed_results:
                        risk.register_closed_position(symbol, exchange)
                        risk.update(closed)
                        dashboard.update(closed)
                        writer.log_trade(closed)
                        drift_status = drift.evaluate(risk.trade_history)
                        last_drift_alerts = drift_status.alerts
                        if drift_status.drift_detected:
                            logger.error(
                                "⚠️ DRIFT ACTIVE [%s]: alerts=%s | %s",
                                symbol,
                                drift_status.alerts,
                                ", ".join(drift_status.reasons),
                            )

                        retrain_decision = retrain.evaluate(
                            drift_detected=drift_status.drift_detected,
                            alerts=drift_status.alerts,
                        )
                        if retrain_decision.trigger:
                            is_emergency = retrain_decision.reason.startswith("EMERGENCY-REGIME-BREAK")
                            if retrain.dry_run:
                                logger.warning(
                                    "🧪 RETRAIN TRIGGER (dry-run): %s",
                                    retrain_decision.reason,
                                )
                                if is_emergency:
                                    retrain.mark_emergency_retrain_started()
                                else:
                                    retrain.mark_retrain_started()
                            else:
                                logger.warning(
                                    "🔄 RETRAIN REQUESTED: %s",
                                    retrain_decision.reason,
                                )
                                if is_emergency:
                                    retrain.mark_emergency_retrain_started()
                                else:
                                    retrain.mark_retrain_started()

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
                last_signal_symbol = signal.symbol
                last_signal_direction = signal.direction

                # 3.1 Multi-timeframe trend gate
                mtf_ok, mtf_reason = mtf_gate.allow_signal(batch.get("ohlcv", []), signal.direction)
                if not mtf_ok:
                    mtf_block_count += 1
                    logger.debug("⛔ %s: %s", symbol, mtf_reason)
                    continue

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

                # 7. Регистрируем открытие позиции (PnL считаем только на закрытии)
                if result.get("status") in {"paper_opened", "opened"}:
                    risk.register_open_position(signal, final_size, sl, tp)

            except Exception as e:
                logger.error(f"Ошибка в цикле [{symbol}]: {e}", exc_info=True)
    finally:
        await writer.stop()


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
