import copy
import unittest

from athena.config import ATHENA_CONFIG
from athena.experiment.ablation import AblationMatrix


class TestAblationMatrix(unittest.TestCase):
    def test_generate_scenarios_contains_expected_feature_group_variants(self):
        matrix = AblationMatrix(copy.deepcopy(ATHENA_CONFIG))
        scenarios = matrix.generate_scenarios()

        for key in [
            "baseline",
            "no_rolling",
            "no_sentiment",
            "no_rolling_sentiment",
            "no_regime",
            "core_compact",
            "price_action_core",
        ]:
            self.assertIn(key, scenarios)

        applied = matrix.apply_scenario("no_rolling_sentiment")
        self.assertFalse(applied["feature_groups"]["rolling"])
        self.assertFalse(applied["feature_groups"]["sentiment"])
        self.assertTrue(applied["feature_groups"]["price"])

        compact = matrix.apply_scenario("core_compact")
        self.assertFalse(compact["feature_groups"]["orderbook"])
        self.assertFalse(compact["feature_groups"]["rolling"])
        self.assertFalse(compact["feature_groups"]["sentiment"])
        self.assertTrue(compact["feature_groups"]["price"])

    def test_unique_scenarios_skip_effective_duplicates_when_sentiment_is_globally_off(self):
        cfg = copy.deepcopy(ATHENA_CONFIG)
        cfg["flags"]["SENTIMENT_ENABLED"] = False
        cfg["flags"]["SENTIMENT_BACKTEST"] = False

        matrix = AblationMatrix(cfg)
        unique = matrix.unique_scenarios(["baseline", "no_sentiment", "no_rolling", "no_rolling_sentiment"])

        self.assertEqual(list(unique.keys()), ["baseline", "no_rolling"])
        self.assertEqual(unique["baseline"], [])
        self.assertEqual(unique["no_rolling"], ["rolling"])


if __name__ == "__main__":
    unittest.main()
