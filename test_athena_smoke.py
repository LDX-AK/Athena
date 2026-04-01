#!/usr/bin/env python3
"""Athena module smoke-test with backtest initialization."""
import sys
import logging

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
    import numpy as np
    # Create dummy OHLCV data
    dummy_ohlcv = {
        'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 102.0, 'volume': 1000.0
    }
    features = engineer.compute_features(dummy_ohlcv, {})
    assert isinstance(features, dict), "Features should be dict"
    logger.info(f"✓ Feature engineering OK: {len(features)} features computed")
except Exception as e:
    logger.error(f"✗ Feature engineering failed: {e}")
    sys.exit(1)

# Test 5: Risk manager
logger.info("Testing risk manager...")
try:
    risk_ok = risk.check_position_size(100.0)  # 100 USD
    logger.info(f"✓ Risk manager OK: position approval = {risk_ok}")
except Exception as e:
    logger.error(f"✗ Risk manager failed: {e}")
    sys.exit(1)

print("\n=== ALL SMOKE-TESTS PASSED ✓ ===\n")
sys.exit(0)
