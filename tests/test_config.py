import unittest

from athena.config import ATHENA_CONFIG


class TestAthenaConfig(unittest.TestCase):
    def test_required_top_level_keys(self):
        for key in ["exchanges", "symbols", "timeframe", "flags", "risk", "data"]:
            self.assertIn(key, ATHENA_CONFIG)

    def test_hybrid_weights_sum_to_one(self):
        flags = ATHENA_CONFIG["flags"]
        total = float(flags["LGBM_WEIGHT"]) + float(flags["SENTIMENT_WEIGHT"])
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_risk_limits_sane(self):
        risk = ATHENA_CONFIG["risk"]
        self.assertGreater(risk["max_position_pct"], 0)
        self.assertLessEqual(risk["max_position_pct"], 1)
        self.assertGreater(risk["max_daily_drawdown_pct"], 0)
        self.assertLessEqual(risk["max_daily_drawdown_pct"], 1)
        self.assertGreaterEqual(risk["min_confidence"], 0)
        self.assertLessEqual(risk["min_confidence"], 1)

    def test_mtf_settings_sane(self):
        self.assertIn("mtf_timeframe", ATHENA_CONFIG)
        self.assertIn("mtf_min_trend", ATHENA_CONFIG)
        self.assertIn("mtf_min_higher_candles", ATHENA_CONFIG)

        self.assertTrue(str(ATHENA_CONFIG["mtf_timeframe"]).endswith("m"))
        self.assertGreater(float(ATHENA_CONFIG["mtf_min_trend"]), 0.0)
        self.assertGreaterEqual(int(ATHENA_CONFIG["mtf_min_higher_candles"]), 2)


if __name__ == "__main__":
    unittest.main()
