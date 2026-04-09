import copy
import pickle
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from athena.config import ATHENA_CONFIG
from athena.features.engineer import AthenaEngineer
from athena.model.fusion import SignalFusion
from athena.model.signal import AthenaModel, AthenaSignal, AthenaTrainer


class TestAthenaModelSchemaAlignment(unittest.TestCase):
    def setUp(self):
        X = pd.DataFrame(
            {
                "ret_1": [-0.3, -0.1, 0.0, 0.1, 0.2, 0.35],
                "rsi": [-0.8, -0.3, 0.0, 0.25, 0.55, 0.9],
            }
        )
        y = np.array([0, 0, 1, 1, 2, 2])
        model = LogisticRegression(max_iter=500)
        model.fit(X, y)

        self.tmpdir = tempfile.TemporaryDirectory()
        self.model_path = Path(self.tmpdir.name) / "schema_test_model.pkl"
        with self.model_path.open("wb") as fh:
            pickle.dump(model, fh)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_predict_ignores_extra_runtime_features(self):
        runtime_model = AthenaModel(str(self.model_path))
        signal = runtime_model.predict(
            {
                "ret_1": 0.18,
                "rsi": 0.42,
                "sentiment_score": 0.9,
                "sentiment_volume": 2.0,
                "_symbol": "BTC/USDT",
                "_exchange": "binance",
                "_last_price": 100_000.0,
            }
        )
        self.assertIsInstance(signal, AthenaSignal)
        self.assertIn(signal.direction, (-1, 0, 1))
        self.assertEqual(signal.symbol, "BTC/USDT")

    def test_predict_fills_missing_trained_features_with_zero(self):
        runtime_model = AthenaModel(str(self.model_path))
        signal = runtime_model.predict(
            {
                "ret_1": -0.05,
                "_symbol": "ETH/USDT",
                "_exchange": "binance",
                "_last_price": 2_500.0,
            }
        )
        self.assertIsInstance(signal, AthenaSignal)
        self.assertIn(signal.direction, (-1, 0, 1))
        self.assertEqual(signal.symbol, "ETH/USDT")

    def test_predict_uses_model_classes_for_binary_buy_hold_model(self):
        X = pd.DataFrame(
            {
                "ret_1": [-0.2, -0.1, 0.2, 0.4],
                "rsi": [-0.5, -0.2, 0.4, 0.8],
            }
        )
        y = np.array([1, 1, 2, 2])
        model = LogisticRegression(max_iter=500)
        model.fit(X, y)

        buy_hold_path = Path(self.tmpdir.name) / "buy_hold_model.pkl"
        with buy_hold_path.open("wb") as fh:
            pickle.dump(model, fh)

        runtime_model = AthenaModel(str(buy_hold_path))
        signal = runtime_model.predict(
            {
                "ret_1": 0.35,
                "rsi": 0.7,
                "_symbol": "BTC/USDT",
                "_exchange": "binance",
                "_last_price": 100_000.0,
            }
        )

        self.assertEqual(signal.direction, 1)


class TestAthenaTrainerLookback(unittest.TestCase):
    def test_feature_lookback_satisfies_engineer_windows(self):
        trainer = AthenaTrainer(AthenaEngineer(), ATHENA_CONFIG)
        lookback = trainer._feature_lookback()
        self.assertGreaterEqual(lookback, max(trainer.engineer.windows) + 10)


class TestAthenaTrainingConfig(unittest.TestCase):
    def test_config_exposes_training_and_feature_group_sections(self):
        self.assertIn("training", ATHENA_CONFIG)
        self.assertEqual(ATHENA_CONFIG["training"]["labeling_mode"], "atr")
        self.assertIn("feature_groups", ATHENA_CONFIG)
        self.assertTrue(ATHENA_CONFIG["feature_groups"]["sentiment"])
        self.assertEqual(ATHENA_CONFIG["training_timeframe"], ATHENA_CONFIG["timeframe"])
        self.assertEqual(ATHENA_CONFIG["runtime_timeframe"], ATHENA_CONFIG["timeframe"])

    def test_model_params_can_be_overridden_from_config(self):
        cfg = copy.deepcopy(ATHENA_CONFIG)
        cfg.setdefault("training", {})["model_params"] = {
            "num_leaves": 15,
            "max_depth": 4,
            "min_child_samples": 100,
            "n_estimators": 120,
        }
        trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
        params = trainer._model_params()

        self.assertEqual(params["num_leaves"], 15)
        self.assertEqual(params["max_depth"], 4)
        self.assertEqual(params["min_child_samples"], 100)
        self.assertEqual(params["n_estimators"], 120)

    def test_weighted_sentiment_is_limited_to_higher_timeframes(self):
        self.assertFalse(SignalFusion.timeframe_allows_weighted_sentiment("5m", "30m"))
        self.assertFalse(SignalFusion.timeframe_allows_weighted_sentiment("15m", "30m"))
        self.assertTrue(SignalFusion.timeframe_allows_weighted_sentiment("30m", "30m"))
        self.assertTrue(SignalFusion.timeframe_allows_weighted_sentiment("1h", "30m"))

    def test_create_labels_uses_atr_mode_when_enabled(self):
        cfg = copy.deepcopy(ATHENA_CONFIG)
        cfg.setdefault("training", {})
        cfg["training"].update(
            {
                "labeling_mode": "atr",
                "label_lookahead": 4,
                "atr_period": 3,
                "atr_tp_mult": 0.8,
                "atr_sl_mult": 0.4,
            }
        )
        trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
        df = pd.DataFrame(
            {
                "open": np.linspace(100.0, 110.0, 20),
                "high": np.linspace(100.4, 110.6, 20),
                "low": np.linspace(99.6, 109.4, 20),
                "close": np.linspace(100.0, 110.0, 20),
                "volume": np.linspace(10.0, 30.0, 20),
            }
        )

        labels = trainer.create_labels(df, tp_pct=0.25, sl_pct=0.25, lookahead=4)
        expected = trainer.create_labels_atr(
            df,
            lookahead=4,
            atr_period=3,
            atr_tp_mult=0.8,
            atr_sl_mult=0.4,
        )

        pd.testing.assert_series_equal(labels, expected)

    def test_create_labels_supports_intrabar_first_touch_mode(self):
        cfg = copy.deepcopy(ATHENA_CONFIG)
        cfg.setdefault("training", {})
        cfg["training"].update(
            {
                "labeling_mode": "atr_hilo",
                "label_lookahead": 2,
                "atr_period": 2,
                "atr_tp_mult": 0.5,
                "atr_sl_mult": 0.5,
            }
        )
        trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
        df = pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.1, 100.1, 100.2, 100.2],
                "high": [100.3, 100.4, 101.2, 100.5, 100.6, 100.7],
                "low": [99.7, 99.8, 99.9, 99.9, 100.0, 100.0],
                "close": [100.0, 100.1, 100.15, 100.16, 100.2, 100.22],
                "volume": [10, 11, 12, 13, 14, 15],
            }
        )

        labels = trainer.create_labels(df, tp_pct=0.25, sl_pct=0.25, lookahead=2)
        self.assertEqual(int(labels.iloc[1]), 1)

    def test_create_labels_can_scope_to_short_only_target(self):
        cfg = copy.deepcopy(ATHENA_CONFIG)
        cfg.setdefault("training", {})
        cfg["training"].update(
            {
                "labeling_mode": "legacy",
                "label_target": "short",
            }
        )
        trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
        df = pd.DataFrame(
            {
                "open": [100.0, 100.0, 101.0, 99.0, 100.0, 98.0],
                "high": [100.2, 101.2, 101.2, 100.2, 100.2, 99.2],
                "low": [99.8, 99.8, 98.8, 98.8, 97.8, 97.8],
                "close": [100.0, 101.0, 99.0, 100.0, 98.0, 99.0],
                "volume": [10, 11, 12, 13, 14, 15],
            }
        )

        labels = trainer.create_labels(df, tp_pct=0.005, sl_pct=0.005, lookahead=1)
        unique_labels = {int(value) for value in labels.tolist()}

        self.assertIn(-1, unique_labels)
        self.assertNotIn(1, unique_labels)


if __name__ == "__main__":
    unittest.main()
