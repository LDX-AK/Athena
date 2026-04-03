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
import json
import logging
import time
from pathlib import Path
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
from athena.risk.pnl        import calc_unrealized_pnl
from athena.execution.router import AthenaRouter
from athena.monitor.dashboard import AthenaDashboard
from athena.monitor.stats_writer import StatsWriter
from athena.config          import ATHENA_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ATHENA » %(message)s"
)
logger = logging.getLogger("athena.core")


def _read_overrides(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _apply_runtime_overrides(
    overrides: dict,
    flags: dict,
    cfg: dict,
    fusion: SignalFusion,
    mtf_gate: MTFGate,
    risk: AthenaRisk,
):
    lgbm_weight = overrides.get("lgbm_weight")
    sentiment_weight = overrides.get("sentiment_weight")
    if isinstance(lgbm_weight, (int, float)) and isinstance(sentiment_weight, (int, float)):
        total = float(lgbm_weight) + float(sentiment_weight)
        if 0.99 <= total <= 1.01 and 0 <= lgbm_weight <= 1 and 0 <= sentiment_weight <= 1:
            fusion.update_weights(float(lgbm_weight), float(sentiment_weight))
            flags["LGBM_WEIGHT"] = float(lgbm_weight)
            flags["SENTIMENT_WEIGHT"] = float(sentiment_weight)

    if "sentiment_enabled" in overrides:
        enabled = bool(overrides.get("sentiment_enabled"))
        fusion.sentiment_enabled = enabled
        flags["SENTIMENT_ENABLED"] = enabled

    if "mtf_filter_enabled" in overrides:
        mtf_enabled = bool(overrides.get("mtf_filter_enabled"))
        mtf_gate.enabled = mtf_enabled
        flags["MTF_FILTER_ENABLED"] = mtf_enabled

    if "min_confidence" in overrides:
        min_conf = overrides.get("min_confidence")
        if isinstance(min_conf, (int, float)) and 0 <= float(min_conf) <= 1:
            risk.cfg["min_confidence"] = float(min_conf)
            cfg.setdefault("risk", {})["min_confidence"] = float(min_conf)


async def run(
    mode: str,
    backtest_csv_path: str | None = None,
    backtest_symbol: str = "BTC/USDT",
    backtest_exchange: str = "binance",
    backtest_limit: int = 50_000,
    backtest_csv_window: str = "first",
):
    cfg   = ATHENA_CONFIG
    flags = cfg.get("flags", {})

    logger.info("⚡ ═══════════════════════════════════════")
    logger.info("⚡  ATHENA AI-BOT v2  |  Starting up...")
    logger.info(f"⚡  Mode:      {mode.upper()}")
    logger.info(f"⚡  Exchanges: {list(cfg['exchanges'].keys())}")
    logger.info(f"⚡  Symbols:   {cfg['symbols']}")
    logger.info(f"⚡  Sentiment: {'ON' if flags.get('SENTIMENT_ENABLED') else 'OFF'}")
    logger.info(f"⚡  RL Shield: {'ON' if flags.get('RL_ENABLED') else 'OFF'}")
    if mode == "backtest" and backtest_csv_path:
        logger.info(f"⚡  Backtest CSV: {backtest_csv_path}")
    logger.info("⚡ ═══════════════════════════════════════")

    sentiment = AthenaSentiment(cfg)
    engineer  = AthenaEngineer()

    # ── Режимы запуска ────────────────────────────────────────
    if mode == "train":
        fetcher = AthenaFetcher(cfg["exchanges"])
        await _train_lgbm(fetcher, engineer, cfg)
        return

    if mode == "train_rl":
        risk   = AthenaRisk(cfg["risk"])
        shield = AthenaShield(cfg, risk_manager=risk)
        shield.train(total_timesteps=100_000)
        return

    if mode == "backtest":
        fetcher = None if backtest_csv_path else AthenaFetcher(cfg["exchanges"])
        await _backtest(
            fetcher,
            engineer,
            sentiment,
            cfg,
            csv_path=backtest_csv_path,
            symbol=backtest_symbol,
            exchange_name=backtest_exchange,
            limit=backtest_limit,
            csv_window=backtest_csv_window,
        )
        return

    # ── Инициализация runtime-компонентов (paper / live) ─────
    fetcher   = AthenaFetcher(cfg["exchanges"])
    risk      = AthenaRisk(cfg["risk"])
    fusion    = SignalFusion(cfg)
    drift     = AthenaDriftMonitor(cfg)
    retrain   = AthenaRetrainPolicy(cfg)
    shield    = AthenaShield(cfg, risk_manager=risk)
    mtf_gate  = MTFGate(cfg)
    router    = AthenaRouter(cfg["exchanges"], mode=mode)
    dashboard = AthenaDashboard(risk)
    writer    = StatsWriter(cfg)
    monitor_cfg = cfg.get("monitor", {})
    overrides_path = Path(monitor_cfg.get("dashboard_overrides_path", "data/dashboard_overrides.json"))
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    last_override_check = 0.0
    last_override_payload = None

    # ── Основной торговый цикл (paper / live) ─────────────────
    logger.info(f"🔄 Запуск торгового цикла [{mode.upper()}]...")
    await writer.start()
    last_signal_symbol = None
    last_signal_direction = 0
    last_drift_alerts = []
    mtf_block_count = 0
    current_prices = {}
    model_version = str(cfg.get("model_version") or Path(cfg.get("model_path", "")).name or "unknown")

    def emit_live_stats():
        unrealized_pnl = calc_unrealized_pnl(router, current_prices) if mode == "paper" else 0.0
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
            "unrealized_pnl": unrealized_pnl,
            "model_version": model_version,
            "last_signal_symbol": last_signal_symbol,
            "last_signal_direction": last_signal_direction,
            "drift_alerts": last_drift_alerts,
            "mtf_blocks": mtf_block_count,
        })
        writer.update_live_stats(live_stats)

    try:
        async for batch in fetcher.stream():
            try:
                now_ts = time.time()
                if now_ts - last_override_check >= 2.0:
                    last_override_check = now_ts
                    payload = _read_overrides(overrides_path)
                    if payload and payload != last_override_payload:
                        _apply_runtime_overrides(payload, flags, cfg, fusion, mtf_gate, risk)
                        last_override_payload = payload
                        logger.info("🎛️ Runtime overrides applied: %s", ", ".join(sorted(payload.keys())))

                symbol   = batch.get("symbol", "")
                exchange = batch.get("exchange", "")

                if batch.get("ohlcv"):
                    try:
                        current_prices[symbol] = float(batch["ohlcv"][-1][4])
                    except (TypeError, ValueError, IndexError):
                        pass

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
                    emit_live_stats()
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
                    emit_live_stats()
                    continue

                # 4. Проверка риск-менеджера
                decision = risk.check(signal)
                if not decision.approved:
                    logger.debug(f"⛔ {symbol}: {decision.reason}")
                    emit_live_stats()
                    continue

                # 5. RL Shield — корректируем размер позиции
                rl_state   = risk.get_ppo_state()
                shield_dec = shield.get_size_multiplier(rl_state)
                final_size = decision.adjusted_size_usd * shield_dec.size_multiplier

                if final_size < 10.0:
                    logger.debug(f"⛔ Размер слишком мал: ${final_size:.2f}")
                    emit_live_stats()
                    continue

                # 6. Вычисляем SL/TP и исполняем
                sl, tp = risk.calculate_sl_tp(signal.price, signal.direction)
                result = await router.execute(signal, final_size, sl, tp)

                # 7. Регистрируем открытие позиции (PnL считаем только на закрытии)
                if result.get("status") in {"paper_opened", "opened"}:
                    risk.register_open_position(signal, final_size, sl, tp)

                emit_live_stats()

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


async def _backtest(fetcher, engineer, sentiment, cfg,
                    csv_path: str | None = None,
                    symbol: str = "BTC/USDT",
                    exchange_name: str = "binance",
                    limit: int = 50_000,
                    csv_window: str = "first"):
    """Бэктест с sentiment."""
    from athena.backtest.runner import AthenaBacktest, load_ohlcv_from_csv

    logger.info("📈 Загружаем данные для бэктеста...")
    logging.getLogger("athena.fusion").setLevel(logging.WARNING)

    if csv_path:
        data = load_ohlcv_from_csv(
            csv_path,
            symbol=symbol,
            max_rows=limit if limit > 0 else None,
            window=csv_window,
        )
    else:
        if fetcher is None:
            raise ValueError("fetcher is required for REST backtest")
        data = await fetcher.fetch_historical(exchange_name, symbol, "1m", limit=limit)

    bt   = AthenaBacktest(engineer, sentiment, cfg)
    metrics = bt.run(data, symbol=symbol)
    if not metrics:
        logger.warning("Бэктест завершён без сделок")
