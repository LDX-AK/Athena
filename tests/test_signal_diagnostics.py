import copy
import time
import unittest

import pandas as pd

from athena.config import ATHENA_CONFIG
from athena.analysis.diagnostics import build_signal_records, summarize_signal_records


class TestSignalDiagnostics(unittest.TestCase):
    def _build_ohlcv(self):
        now_ms = int(time.time() * 1000)
        rows = []
        price = 100.0
        for i in range(180):
            open_ = price
            close = open_ * (1 + (0.0012 if i % 4 else -0.0005))
            high = max(open_, close) * 1.0015
            low = min(open_, close) * 0.9985
            volume = 1000 + i * 3
            rows.append([now_ms - (180 - i) * 900_000, open_, high, low, close, volume])
            price = close
        return rows

    def test_build_signal_records_generates_forward_return_columns(self):
        cfg = copy.deepcopy(ATHENA_CONFIG)
        cfg["model_path"] = "none"
        cfg["timeframe"] = "15m"
        cfg["runtime_timeframe"] = "15m"
        cfg["flags"]["SENTIMENT_ENABLED"] = False

        records = build_signal_records(
            self._build_ohlcv(),
            cfg,
            symbol="BTC/USDT",
            horizons=[3, 6],
        )

        self.assertFalse(records.empty)
        for key in [
            "direction",
            "confidence",
            "vol_regime",
            "regime_bucket",
            "hour",
            "signed_return_3",
            "signed_return_6",
        ]:
            self.assertIn(key, records.columns)

    def test_summarize_signal_records_reports_confidence_side_and_regime_breakdowns(self):
        records = pd.DataFrame(
            {
                "direction": [1, 1, -1, -1],
                "confidence": [0.72, 0.61, 0.51, 0.43],
                "signed_return_6": [0.020, -0.010, 0.030, -0.020],
                "vol_regime": [0.80, 0.55, 0.20, 0.10],
                "hour": [9, 10, 15, 16],
            }
        )

        report = summarize_signal_records(records, primary_horizon=6)

        self.assertEqual(report["summary"]["total_signals"], 4)
        self.assertAlmostEqual(report["summary"]["edge_per_signal"], 0.005, places=6)
        self.assertIn("0.65-1.00", [row["bucket"] for row in report["confidence_breakdown"]])
        self.assertEqual(report["side_breakdown"]["long"]["count"], 2)
        self.assertEqual(report["side_breakdown"]["short"]["count"], 2)
        self.assertEqual(report["regime_breakdown"]["hot"]["count"], 1)
        self.assertEqual(report["regime_breakdown"]["quiet"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
