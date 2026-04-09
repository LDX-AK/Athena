import unittest

from athena.filters.regime_router import RegimeRouter


class TestRegimeRouter(unittest.TestCase):
    def setUp(self):
        self.router = RegimeRouter({})

    def test_quiet_asia_prefers_no_trade_with_penalty(self):
        decision = self.router.decide(
            {
                "vol_regime": 0.10,
                "session_asia": 1.0,
                "session_europe": 0.0,
                "session_us": 0.0,
                "session_overlap": 0.0,
                "is_weekend": 0.0,
            },
            timestamp_ms=1712286000000,
            raw_confidence=0.80,
        )

        self.assertEqual(decision["regime"], "quiet")
        self.assertEqual(decision["session"], "asia")
        self.assertEqual(decision["route"], "no_trade")
        self.assertLess(decision["adjusted_confidence"], 0.80)
        self.assertIn("quiet", decision["reason"])

    def test_normal_overlap_prefers_directional_with_small_boost(self):
        decision = self.router.decide(
            {
                "vol_regime": 0.50,
                "session_asia": 0.0,
                "session_europe": 1.0,
                "session_us": 1.0,
                "session_overlap": 1.0,
                "is_weekend": 0.0,
            },
            timestamp_ms=1712583000000,
            raw_confidence=0.60,
        )

        self.assertEqual(decision["regime"], "normal")
        self.assertEqual(decision["session"], "eu_us_overlap")
        self.assertEqual(decision["route"], "directional")
        self.assertGreaterEqual(decision["adjusted_confidence"], 0.60)

    def test_hot_us_prefers_breakout(self):
        decision = self.router.decide(
            {
                "vol_regime": 0.90,
                "session_asia": 0.0,
                "session_europe": 0.0,
                "session_us": 1.0,
                "session_overlap": 0.0,
                "is_weekend": 0.0,
            },
            timestamp_ms=1712593800000,
            raw_confidence=0.70,
        )

        self.assertEqual(decision["regime"], "hot")
        self.assertEqual(decision["session"], "us")
        self.assertEqual(decision["route"], "breakout")
        self.assertGreater(decision["confidence_multiplier"], 1.0)


if __name__ == "__main__":
    unittest.main()
