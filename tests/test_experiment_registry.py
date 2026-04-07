import json
import tempfile
import unittest
from pathlib import Path

from athena.experiment.registry import ExperimentRegistry


class TestExperimentRegistry(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.registry = ExperimentRegistry(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_save_experiment_creates_result_and_metadata_entry(self):
        exp_id = self.registry.save_experiment(
            name="walkforward_check",
            results={"sharpe_ratio": 0.7, "profit_factor": 1.3, "total_return_pct": 0.2},
            config_snapshot={"timeframe": "15m"},
        )

        result_path = self.registry.results_dir / f"{exp_id}.json"
        self.assertTrue(result_path.exists())

        metadata = json.loads((self.registry.storage / "metadata.json").read_text(encoding="utf-8"))
        self.assertIn(exp_id, metadata["experiments"])
        self.assertEqual(metadata["experiments"][exp_id]["name"], "walkforward_check")

    def test_compare_experiments_returns_metrics_table(self):
        exp_id = self.registry.save_experiment(
            name="candidate_a",
            results={"sharpe_ratio": 1.1, "profit_factor": 1.4, "total_return_pct": 0.8, "win_rate": 0.55},
        )
        df = self.registry.compare_experiments([exp_id])
        self.assertEqual(list(df["exp_id"]), [exp_id])
        self.assertAlmostEqual(float(df.iloc[0]["sharpe"]), 1.1, places=6)


if __name__ == "__main__":
    unittest.main()
