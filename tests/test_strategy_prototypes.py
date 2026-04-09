import unittest

from athena.strategy.prototypes import QuietMeanReversionPrototype


class TestQuietMeanReversionPrototype(unittest.TestCase):
    def setUp(self):
        self.prototype = QuietMeanReversionPrototype({})

    def test_oversold_quiet_setup_triggers_long(self):
        decision = self.prototype.decide(
            {
                "rsi": -0.35,
                "bb_pos": 0.10,
                "vwap_dist": -0.004,
                "ema_9_dist": -0.002,
                "ema_50_dist": -0.004,
            }
        )
        self.assertEqual(decision.direction, 1)
        self.assertGreaterEqual(decision.confidence, 0.55)
        self.assertIn("long", decision.reason)

    def test_overbought_quiet_setup_triggers_short(self):
        decision = self.prototype.decide(
            {
                "rsi": 0.32,
                "bb_pos": 0.90,
                "vwap_dist": 0.0035,
                "ema_9_dist": 0.002,
                "ema_50_dist": 0.003,
            }
        )
        self.assertEqual(decision.direction, -1)
        self.assertGreaterEqual(decision.confidence, 0.55)
        self.assertIn("short", decision.reason)

    def test_neutral_setup_stays_flat(self):
        decision = self.prototype.decide(
            {
                "rsi": 0.02,
                "bb_pos": 0.52,
                "vwap_dist": 0.0003,
                "ema_9_dist": 0.0001,
                "ema_50_dist": 0.0002,
            }
        )
        self.assertEqual(decision.direction, 0)
        self.assertEqual(decision.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
