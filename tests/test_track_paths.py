from pathlib import Path
import unittest

from athena.track_paths import default_result_path, normalize_track, track_dir


class TestTrackPaths(unittest.TestCase):
    def test_normalize_track_accepts_only_v2_and_v3(self):
        self.assertEqual(normalize_track("V2"), "v2")
        self.assertEqual(normalize_track("v3"), "v3")
        with self.assertRaises(ValueError):
            normalize_track("main")

    def test_track_dir_separates_result_roots(self):
        self.assertTrue(str(track_dir("v2", "results")).endswith("data/results/v2"))
        self.assertTrue(str(track_dir("v3", "results")).endswith("data/results/v3"))
        self.assertTrue(str(track_dir("v2", "models")).endswith("athena/model/v2"))
        self.assertTrue(str(track_dir("v3", "models")).endswith("athena/model/v3"))

    def test_default_result_path_uses_track_subfolder(self):
        out = default_result_path("v2", timeframe="15m", candidate="core_compact", suffix="regression")
        self.assertIsInstance(out, Path)
        self.assertTrue(str(out).endswith("data/results/v2/walkforward_15m_core_compact_regression.json"))


if __name__ == "__main__":
    unittest.main()
