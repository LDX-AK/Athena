import unittest

from athena.config import ATHENA_CONFIG
from athena.model.retrain_policy import AthenaRetrainPolicy


class TestRetrainPolicy(unittest.TestCase):
    def _config(self):
        cfg = dict(ATHENA_CONFIG)
        cfg["retrain"] = dict(ATHENA_CONFIG["retrain"])
        cfg["retrain"]["cooldown_hours"] = 24
        cfg["retrain"]["critical_alerts_required"] = 2
        cfg["retrain"]["emergency_bypass_enabled"] = True
        cfg["retrain"]["emergency_min_severity"] = 7
        cfg["retrain"]["emergency_cooldown_hours"] = 6
        return cfg

    def test_emergency_bypass_triggers(self):
        policy = AthenaRetrainPolicy(self._config())
        decision = policy.evaluate(
            drift_detected=True,
            alerts=["LOSS_STREAK", "REGIME_VOLATILITY", "SHARPE_DRIFT"],
        )
        self.assertTrue(decision.trigger)
        self.assertTrue(decision.reason.startswith("EMERGENCY-REGIME-BREAK"))

    def test_emergency_rate_limit(self):
        policy = AthenaRetrainPolicy(self._config())
        first = policy.evaluate(
            drift_detected=True,
            alerts=["LOSS_STREAK", "REGIME_VOLATILITY", "SHARPE_DRIFT"],
        )
        self.assertTrue(first.trigger)
        policy.mark_emergency_retrain_started()

        second = policy.evaluate(
            drift_detected=True,
            alerts=["LOSS_STREAK", "REGIME_VOLATILITY", "SHARPE_DRIFT"],
        )
        self.assertFalse(second.trigger)
        self.assertTrue(second.reason.startswith("emergency-rate-limited"))


if __name__ == "__main__":
    unittest.main()
