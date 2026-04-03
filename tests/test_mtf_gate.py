import time
import unittest

from athena.config import ATHENA_CONFIG
from athena.filters.mtf_gate import MTFGate


class TestMTFGate(unittest.TestCase):
    def _config(self):
        cfg = dict(ATHENA_CONFIG)
        cfg["flags"] = dict(ATHENA_CONFIG.get("flags", {}))
        cfg["flags"]["MTF_FILTER_ENABLED"] = True
        cfg["mtf_timeframe"] = "15m"
        cfg["mtf_min_trend"] = 0.001
        cfg["mtf_min_higher_candles"] = 8
        return cfg

    def _ohlcv(self, drift_per_candle: float, count: int = 240):
        now_ms = int(time.time() * 1000)
        out = []
        price = 100.0
        for i in range(count):
            open_ = price
            close = open_ * (1.0 + drift_per_candle)
            high = max(open_, close) * 1.0008
            low = min(open_, close) * 0.9992
            volume = 1000.0 + i
            out.append([now_ms - (count - i) * 60_000, open_, high, low, close, volume])
            price = close
        return out

    def test_allows_signal_in_trend_direction(self):
        gate = MTFGate(self._config())
        ohlcv = self._ohlcv(0.0008)
        ok, reason = gate.allow_signal(ohlcv, direction=1)
        self.assertTrue(ok, reason)

    def test_blocks_signal_against_trend(self):
        gate = MTFGate(self._config())
        ohlcv = self._ohlcv(0.0008)
        ok, reason = gate.allow_signal(ohlcv, direction=-1)
        self.assertFalse(ok)
        self.assertIn("mtf-against-trend", reason)

    def test_blocks_on_insufficient_data(self):
        gate = MTFGate(self._config())
        # 15m ratio needs enough 1m candles; 60 is too short for min_higher_candles=8.
        ohlcv = self._ohlcv(0.0008, count=60)
        ok, reason = gate.allow_signal(ohlcv, direction=1)
        self.assertFalse(ok)
        self.assertEqual(reason, "mtf-insufficient-data")


if __name__ == "__main__":
    unittest.main()
