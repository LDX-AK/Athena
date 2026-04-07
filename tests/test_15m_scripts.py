from pathlib import Path
import importlib.util
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


if __name__ == "__main__":
    unittest.main()
