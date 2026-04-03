#!/usr/bin/env python3
"""Athena module smoke-test with backtest initialization."""
import sys
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('athena_test')

print("\n=== ATHENA MODULE SMOKE-TEST ===\n")

# Test 1: Config load
logger.info("Loading config...")
try:
    from athena.config import ATHENA_CONFIG
    logger.info(f"✓ Config OK: {len(ATHENA_CONFIG)} keys")
    assert ATHENA_CONFIG.get('symbols'), "No symbols in config"
    assert ATHENA_CONFIG.get('exchanges'), "No exchanges in config"
except Exception as e:
    logger.error(f"✗ Config failed: {e}")
    sys.exit(1)

# Test 2: Core modules import
logger.info("Importing core modules...")
try:
    from athena.data.fetcher import AthenaFetcher
    from athena.data.sentiment import AthenaSentiment
    from athena.features.engineer import AthenaEngineer
    from athena.model.signal import AthenaModel
    from athena.model.fusion import SignalFusion
    from athena.risk.manager import AthenaRisk
    from athena.execution.router import AthenaRouter
    from athena.monitor.dashboard import AthenaDashboard
    logger.info("✓ All core modules imported")
except Exception as e:
    logger.error(f"✗ Module import failed: {e}")
    sys.exit(1)

# Test 3: Initialize backtest components (no live keys needed)
logger.info("Initializing backtest components...")
try:
    cfg = ATHENA_CONFIG
    
    # Initialize without live trading
    fetcher = AthenaFetcher(cfg["exchanges"])
    engineer = AthenaEngineer()
    risk = AthenaRisk(cfg.get("risk", {}))
    fusion = SignalFusion(cfg)
    router = AthenaRouter(cfg["exchanges"], mode="backtest")
    dashboard = AthenaDashboard(risk)
    
    logger.info("✓ All components initialized for backtest mode")
except Exception as e:
    logger.error(f"✗ Component init failed: {e}")
    sys.exit(1)

# Test 4: Feature engineering pipeline
logger.info("Testing feature engineering pipeline...")
try:
    now_ms = int(time.time() * 1000)
    ohlcv = []
    price = 100.0
    for i in range(140):
        open_ = price
        close = open_ * (1 + (0.0005 if i % 2 == 0 else -0.0003))
        high = max(open_, close) * 1.001
        low = min(open_, close) * 0.999
        volume = 1000 + i * 3
        ohlcv.append([now_ms - (140 - i) * 60_000, open_, high, low, close, volume])
        price = close

    batch = {
        "ohlcv": ohlcv,
        "orderbook": {
            "bids": [[price * 0.999, 5.0], [price * 0.998, 4.0]],
            "asks": [[price * 1.001, 4.5], [price * 1.002, 6.0]],
            "timestamp": now_ms,
        },
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "sentiment": {"score": 0.1, "volume": 1.0, "trend": 0.05},
    }
    features = engineer.transform(batch)
    assert features is not None, "Features should not be None"
    assert isinstance(features, dict), "Features should be dict"
    logger.info(f"✓ Feature engineering OK: {len(features)} features computed")
except Exception as e:
    logger.error(f"✗ Feature engineering failed: {e}")
    sys.exit(1)

# Test 5: Risk manager
logger.info("Testing risk manager...")
try:
    from athena.model.signal import AthenaSignal

    sig = AthenaSignal(
        direction=1,
        confidence=0.8,
        symbol="BTC/USDT",
        exchange="binance",
        price=price,
        features=features,
    )
    decision = risk.check(sig)
    logger.info(f"✓ Risk manager OK: approved={decision.approved}, size=${decision.adjusted_size_usd:.2f}")
except Exception as e:
    logger.error(f"✗ Risk manager failed: {e}")
    sys.exit(1)

print("\n=== ALL SMOKE-TESTS PASSED ✓ ===\n")
sys.exit(0)
