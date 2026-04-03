import time
import unittest

from athena.features.engineer import AthenaEngineer


class TestFeaturePipeline(unittest.TestCase):
    def setUp(self):
        self.engineer = AthenaEngineer()

    def _build_batch(self):
        now_ms = int(time.time() * 1000)
        ohlcv = []
        price = 100.0

        for i in range(150):
            open_ = price
            close = open_ * (1 + (0.0007 if i % 3 else -0.0004))
            high = max(open_, close) * 1.0015
            low = min(open_, close) * 0.9985
            volume = 1200 + i * 2
            ohlcv.append([now_ms - (150 - i) * 60_000, open_, high, low, close, volume])
            price = close

        return {
            "ohlcv": ohlcv,
            "orderbook": {
                "bids": [[price * 0.999, 5.0], [price * 0.998, 4.0], [price * 0.997, 2.0]],
                "asks": [[price * 1.001, 4.5], [price * 1.002, 6.0], [price * 1.003, 2.5]],
                "timestamp": now_ms,
            },
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "sentiment": {"score": 0.12, "volume": 1.3, "trend": 0.04},
        }

    def test_transform_returns_features(self):
        features = self.engineer.transform(self._build_batch())
        self.assertIsNotNone(features)
        features = features or {}
        self.assertIsInstance(features, dict)
        self.assertGreater(len(features), 40)

    def test_transform_contains_core_keys(self):
        features = self.engineer.transform(self._build_batch())
        self.assertIsNotNone(features)
        features = features or {}
        required = [
            "ret_1", "rsi", "ob_imb_5", "trade_imbalance", "ret_60m",
            "rolling_sharpe_30", "vol_regime", "sentiment_score", "_symbol", "_exchange", "_last_price",
        ]
        for key in required:
            self.assertIn(key, features)

    def test_transform_no_nan(self):
        features = self.engineer.transform(self._build_batch())
        self.assertIsNotNone(features)
        features = features or {}
        numeric_values = [v for v in features.values() if isinstance(v, (int, float))]
        has_nan = any(v != v for v in numeric_values)
        self.assertFalse(has_nan)


if __name__ == "__main__":
    unittest.main()
