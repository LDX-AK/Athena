from pathlib import Path
import importlib.util
import inspect
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class Test15mScriptSupport(unittest.TestCase):
    def _load_module(self, filename: str, module_name: str):
        module_path = REPO_ROOT / filename
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_train_model_tf_exists_and_defaults_to_15m_path(self):
        module = self._load_module("train_model_tf.py", "train_model_tf")
        self.assertEqual(
            module.default_model_path("15m"),
            REPO_ROOT / "athena/model/athena_brain_15m.pkl",
        )

    def test_compare_runner_uses_repo_relative_root(self):
        module = self._load_module("run_compare_15m_fast.py", "run_compare_15m_fast")
        self.assertEqual(module.ROOT, REPO_ROOT)
        self.assertTrue((module.ROOT / "athena/model/athena_brain_15m.pkl").exists())

    def test_walkforward_runner_exposes_no_rolling_final_candidate(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        self.assertIn("no_rolling_final", module.CANDIDATES)
        candidate = module.CANDIDATES["no_rolling_final"]
        self.assertFalse(candidate["feature_groups"]["rolling"])
        self.assertTrue(candidate["feature_groups"]["regime"])

    def test_walkforward_runner_exposes_core_compact_candidate(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        self.assertIn("core_compact", module.CANDIDATES)
        candidate = module.CANDIDATES["core_compact"]
        self.assertFalse(candidate["feature_groups"]["orderbook"])
        self.assertFalse(candidate["feature_groups"]["rolling"])
        self.assertTrue(candidate["feature_groups"]["regime"])

    def test_walkforward_parse_months_handles_csv_input(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        self.assertEqual(
            module.parse_months("2025-10, 2025-11,2025-12"),
            ["2025-10", "2025-11", "2025-12"],
        )
        self.assertEqual(module.parse_months(None, ["2025-04"]), ["2025-04"])

    def test_walkforward_training_cfg_keeps_base_label_risk(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        cfg = module.make_cfg("no_rolling_final", profile="conservative", for_training=True)
        self.assertEqual(cfg["risk"]["stop_loss_pct"], module.ATHENA_CONFIG["risk"]["stop_loss_pct"])
        self.assertEqual(cfg["risk"]["take_profit_pct"], module.ATHENA_CONFIG["risk"]["take_profit_pct"])

    def test_walkforward_month_file_respects_timeframe(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        path = module.month_file("2025-04", timeframe="30m")
        self.assertTrue(str(path).endswith("BTCUSDT_30m_2025_04.csv"))

    def test_walkforward_scaled_windows_and_hierarchy_for_30m(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        cfg = module.make_cfg(
            "no_rolling_final",
            profile="conservative",
            timeframe="30m",
            for_training=True,
        )
        self.assertEqual(cfg["timeframe"], "30m")
        self.assertEqual(cfg["runtime_timeframe"], "30m")
        self.assertEqual(cfg["training_timeframe"], "30m")
        self.assertEqual(cfg["mtf_timeframe"], "1h")
        self.assertLess(cfg["training"]["label_lookahead"], module.ATHENA_CONFIG["training"]["label_lookahead"])
        self.assertNotEqual(cfg["data"]["windows"], module.CANDIDATES["no_rolling_final"]["windows"])

    def test_walkforward_can_override_macro_filter_to_1h(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        cfg = module.make_cfg(
            "no_rolling_final",
            profile="conservative",
            timeframe="15m",
            macro_filter_tf="1h",
            for_training=False,
        )
        self.assertEqual(cfg["mtf_timeframe"], "1h")
        self.assertEqual(cfg["tf_filter"], "1h")
        self.assertTrue(cfg["flags"]["MTF_FILTER_ENABLED"])
        self.assertTrue(cfg["macro_filter"]["enabled"])
        self.assertEqual(cfg["macro_filter"]["timeframe"], "1h")

    def test_signal_diagnostics_runner_parses_horizons(self):
        module = self._load_module("scripts/run_signal_diagnostics.py", "run_signal_diagnostics")
        self.assertEqual(module.ROOT, REPO_ROOT)
        self.assertEqual(module.parse_horizons("3, 6,10"), [3, 6, 10])

    def test_walkforward_can_scope_direction_and_regime_filters(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        cfg = module.make_cfg(
            "core_compact",
            profile="conservative",
            timeframe="15m",
            direction_filter="short",
            regime_filter="normal",
            for_training=False,
        )
        self.assertEqual(cfg["experiment"]["direction_filter"], "short")
        self.assertEqual(cfg["experiment"]["regime_filter"], "normal")

    def test_train_candidate_accepts_direction_filter_for_one_sided_retrain(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        params = inspect.signature(module.train_candidate).parameters
        self.assertIn("direction_filter", params)
        self.assertIn("model_dir", params)

    def test_walkforward_can_attach_meta_filter_configuration(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        cfg = module.make_cfg(
            "core_compact",
            profile="aggressive",
            timeframe="15m",
            direction_filter="short",
            meta_allowed_hours=[5, 6, 18],
            meta_allowed_regimes=["quiet", "normal"],
            meta_max_confidence=0.65,
            for_training=False,
        )
        self.assertEqual(cfg["experiment"]["meta_filter"]["allowed_hours"], [5, 6, 18])
        self.assertEqual(cfg["experiment"]["meta_filter"]["allowed_regimes"], ["quiet", "normal"])
        self.assertEqual(cfg["experiment"]["meta_filter"]["max_confidence"], 0.65)

    def test_walkforward_can_enable_router_configuration(self):
        module = self._load_module("run_walkforward_15m.py", "run_walkforward_15m")
        cfg = module.make_cfg(
            "core_compact",
            profile="conservative",
            timeframe="15m",
            for_training=False,
            router_enabled=True,
        )
        self.assertTrue(cfg["router"]["enabled"])


if __name__ == "__main__":
    unittest.main()
