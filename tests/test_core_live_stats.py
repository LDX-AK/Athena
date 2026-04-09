import unittest
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch


def _install_import_stubs():
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = ModuleType("ccxt")

    if "aiohttp" not in sys.modules:
        sys.modules["aiohttp"] = ModuleType("aiohttp")

    if "numpy" not in sys.modules:
        np = ModuleType("numpy")

        class _NdArray:
            pass

        np.ndarray = _NdArray
        np.float32 = float
        np.inf = float("inf")
        sys.modules["numpy"] = np

    if "pandas" not in sys.modules:
        pd = ModuleType("pandas")

        class _DataFrame:
            pass

        pd.DataFrame = _DataFrame
        pd.Series = list
        sys.modules["pandas"] = pd


class TestCoreLiveStats(unittest.IsolatedAsyncioTestCase):
    async def test_run_updates_live_stats_with_unrealized_pnl(self):
        _install_import_stubs()

        import athena.core as core

        class FakeFetcher:
            def __init__(self, exchanges):
                self.exchanges = exchanges

            async def stream(self):
                yield {
                    "symbol": "BTC/USDT",
                    "exchange": "binance",
                    "ohlcv": [[0, 100.0, 111.0, 99.0, 110.0, 1000.0]],
                }

        class FakeSentiment:
            def __init__(self, cfg):
                self.cfg = cfg

            async def get_live(self, symbol):
                return {"score": 0.1}

        class FakeEngineer:
            def transform(self, batch):
                return {"vol_regime": 0.5}

        class FakeRisk:
            def __init__(self, risk_cfg):
                self.risk_cfg = risk_cfg
                self.trade_history = []
                self.open_positions = {}
                self.total_balance = 10000.0
                self.current_vol_regime = 0.0
                self.current_sentiment = 0.0

            def stats(self):
                return {
                    "daily_pnl": 0.0,
                    "total_pnl": 0.0,
                    "total_trades": 0,
                    "win_rate": 0.0,
                }

            def check(self, signal):
                return SimpleNamespace(approved=True, adjusted_size_usd=100.0, reason="")

            def calculate_sl_tp(self, price, direction):
                return 90.0, 120.0

            def get_ppo_state(self):
                return {}

            def register_open_position(self, signal, final_size, sl, tp):
                self.open_positions[f"{signal.exchange}:{signal.symbol}"] = {
                    "entry": signal.price,
                    "size_usd": final_size,
                    "sl": sl,
                    "tp": tp,
                }

            def register_closed_position(self, symbol, exchange):
                return None

            def update(self, closed):
                return None

        class FakeFusion:
            def __init__(self, cfg):
                self.cfg = cfg

            def predict(self, features, sent_data):
                return SimpleNamespace(
                    symbol="BTC/USDT",
                    exchange="binance",
                    direction=1,
                    confidence=0.8,
                    price=100.0,
                )

        class FakeDrift:
            def __init__(self, cfg):
                self.cfg = cfg

            def evaluate(self, history):
                return SimpleNamespace(drift_detected=False, alerts=[], reasons=[])

        class FakeRetrain:
            def __init__(self, cfg):
                self.cfg = cfg
                self.dry_run = True

            def evaluate(self, drift_detected, alerts):
                return SimpleNamespace(trigger=False, reason="")

            def mark_emergency_retrain_started(self):
                return None

            def mark_retrain_started(self):
                return None

        class FakeShield:
            def __init__(self, cfg, risk_manager):
                self.cfg = cfg
                self.risk_manager = risk_manager

            def get_size_multiplier(self, state):
                return SimpleNamespace(size_multiplier=1.0)

            def train(self, total_timesteps=1000):
                return None

        class FakeMTFGate:
            def __init__(self, cfg):
                self.cfg = cfg

            def allow_signal(self, ohlcv, direction):
                return True, "ok"

        class FakeRouter:
            def __init__(self, exchanges, mode="paper"):
                self.mode = mode
                self.exchanges = exchanges
                self.commission_rate = 0.0004
                self.paper_balance = 10000.0
                self.paper_positions = {
                    "binance:BTC/USDT": {
                        "symbol": "BTC/USDT",
                        "entry": 100.0,
                        "direction": 1,
                        "size_usd": 1000.0,
                        "commission": 0.4,
                    }
                }

            async def check_paper_exits(self, symbol, exchange, low, high):
                return []

            async def execute(self, signal, final_size, sl, tp):
                return {"status": "paper_opened"}

        class FakeDashboard:
            def __init__(self, risk):
                self.risk = risk

            def update(self, result):
                return None

        class FakeWriter:
            instances = []

            def __init__(self, cfg):
                self.cfg = cfg
                self.last_stats = None
                FakeWriter.instances.append(self)

            async def start(self):
                return None

            async def stop(self):
                return None

            def update_live_stats(self, stats):
                self.last_stats = dict(stats)

            def log_trade(self, trade):
                return None

        cfg = {
            "exchanges": {"binance": {}},
            "symbols": ["BTC/USDT"],
            "model_path": "athena/model/athena_brain.pkl",
            "risk": {},
            "flags": {
                "SENTIMENT_ENABLED": False,
                "RL_ENABLED": False,
                "SENTIMENT_LIVE_ENABLED": False,
                "MTF_FILTER_ENABLED": True,
                "LGBM_WEIGHT": 0.7,
                "SENTIMENT_WEIGHT": 0.3,
            },
        }

        with (
            patch.object(core, "ATHENA_CONFIG", cfg),
            patch.object(core, "AthenaFetcher", FakeFetcher),
            patch.object(core, "AthenaSentiment", FakeSentiment),
            patch.object(core, "AthenaEngineer", FakeEngineer),
            patch.object(core, "AthenaRisk", FakeRisk),
            patch.object(core, "SignalFusion", FakeFusion),
            patch.object(core, "AthenaDriftMonitor", FakeDrift),
            patch.object(core, "AthenaRetrainPolicy", FakeRetrain),
            patch.object(core, "AthenaShield", FakeShield),
            patch.object(core, "MTFGate", FakeMTFGate),
            patch.object(core, "AthenaRouter", FakeRouter),
            patch.object(core, "AthenaDashboard", FakeDashboard),
            patch.object(core, "StatsWriter", FakeWriter),
        ):
            await core.run("paper")

        self.assertTrue(FakeWriter.instances, "Writer was not instantiated")
        stats = FakeWriter.instances[-1].last_stats
        self.assertIsNotNone(stats, "live_stats were not updated")
        self.assertIn("unrealized_pnl", stats)
        self.assertIn("model_version", stats)
        self.assertIn("feature_skips", stats)
        self.assertIn("risk_blocks", stats)
        self.assertIn("orders_opened", stats)
        self.assertIn("runtime_status", stats)
        self.assertIn("last_mtf_reason", stats)
        self.assertIn("mtf_blocks_history", stats)
        self.assertIn("risk_blocks_history", stats)
        self.assertEqual(stats["model_version"], "athena_brain.pkl")
        self.assertEqual(stats["feature_skips"], 0)
        self.assertEqual(stats["risk_blocks"], 0)
        self.assertEqual(stats["orders_opened"], 1)
        self.assertEqual(stats["runtime_status"], "order_opened")
        self.assertEqual(stats["last_mtf_reason"], "ok")
        self.assertIsInstance(stats["mtf_blocks_history"], list)
        self.assertIsInstance(stats["risk_blocks_history"], list)
        self.assertGreaterEqual(len(stats["mtf_blocks_history"]), 1)
        self.assertGreaterEqual(len(stats["risk_blocks_history"]), 1)
        self.assertEqual(stats["mtf_blocks_history"][-1], 0)
        self.assertEqual(stats["risk_blocks_history"][-1], 0)
        self.assertAlmostEqual(stats["unrealized_pnl"], 99.2, places=6)


if __name__ == "__main__":
    unittest.main()
