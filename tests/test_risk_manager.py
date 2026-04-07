import copy
import unittest

from athena.config import ATHENA_CONFIG
from athena.model.signal import AthenaSignal
from athena.risk.manager import AthenaRisk


class TestAthenaRiskCircuitBreaker(unittest.TestCase):
    def _risk_cfg(self):
        cfg = copy.deepcopy(ATHENA_CONFIG["risk"])
        cfg.update(
            {
                "circuit_breaker_enabled": True,
                "cooldown_after_loss_sec": 0,
                "circuit_breaker_window_trades": 5,
                "circuit_breaker_min_win_rate": 0.35,
                "circuit_breaker_min_sharpe": 0.0,
                "circuit_breaker_max_consecutive_losses": 3,
                "circuit_breaker_reduce_size_factor": 0.25,
            }
        )
        return cfg

    def test_circuit_breaker_reduces_position_size_after_loss_cluster(self):
        risk = AthenaRisk(self._risk_cfg())
        signal = AthenaSignal(1, 0.9, "BTC/USDT", "binance", 100_000.0, {})

        baseline = risk.check(signal)
        self.assertTrue(baseline.approved)

        for _ in range(5):
            risk.update({"pnl": -25.0, "confidence": 0.4})

        degraded = risk.check(signal)
        self.assertTrue(degraded.approved)
        self.assertLess(degraded.adjusted_size_usd, baseline.adjusted_size_usd)
        self.assertIn("circuit", degraded.reason.lower())


if __name__ == "__main__":
    unittest.main()
