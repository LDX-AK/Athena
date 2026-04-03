import unittest

from athena.model.drift_monitor import AthenaDriftMonitor
from athena.config import ATHENA_CONFIG


class TestDriftMonitor(unittest.TestCase):
    def _config(self):
        config = dict(ATHENA_CONFIG)
        config["drift"] = dict(ATHENA_CONFIG["drift"])
        config["drift"]["window_trades"] = 10
        config["drift"]["consecutive_alerts"] = 2
        config["drift"]["consecutive_losses"] = 3
        return config

    def test_baseline_capture(self):
        monitor = AthenaDriftMonitor(self._config())
        trades = [{"pnl": 10.0 if i % 2 == 0 else -5.0, "confidence": 0.8} for i in range(10)]
        status = monitor.evaluate(trades)
        self.assertFalse(status.drift_detected)
        self.assertIn("baseline-captured", status.reasons)

    def test_detects_loss_streak_and_confidence_drift(self):
        monitor = AthenaDriftMonitor(self._config())
        baseline = [{"pnl": 12.0 if i % 2 == 0 else -4.0, "confidence": 0.9} for i in range(10)]
        monitor.evaluate(baseline)

        degraded = [
            {"pnl": -10.0, "confidence": 0.5},
            {"pnl": -8.0, "confidence": 0.5},
            {"pnl": -7.0, "confidence": 0.45},
            {"pnl": -6.0, "confidence": 0.45},
            {"pnl": -5.0, "confidence": 0.4},
            {"pnl": 1.0, "confidence": 0.4},
            {"pnl": -3.0, "confidence": 0.35},
            {"pnl": -2.0, "confidence": 0.35},
            {"pnl": -1.0, "confidence": 0.35},
            {"pnl": -4.0, "confidence": 0.3},
        ]
        status1 = monitor.evaluate(degraded)
        status2 = monitor.evaluate(degraded)

        self.assertIn("CONFIDENCE_DRIFT", status1.alerts)
        self.assertIn("LOSS_STREAK", status1.alerts)
        self.assertTrue(status2.drift_detected)


if __name__ == "__main__":
    unittest.main()
