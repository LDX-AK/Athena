import pickle
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from athena.model.signal import AthenaModel, AthenaSignal


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


if __name__ == "__main__":
    unittest.main()
