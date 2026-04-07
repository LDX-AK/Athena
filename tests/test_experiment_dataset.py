import tempfile
import unittest
from pathlib import Path

import pandas as pd

from athena.experiment.dataset import MonthlyDatasetManager


class TestMonthlyDatasetManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)

        april = pd.DataFrame(
            {
                "timestamp": [1, 2],
                "open": [100, 101],
                "high": [101, 102],
                "low": [99, 100],
                "close": [100.5, 101.5],
                "volume": [10, 12],
            }
        )
        may = pd.DataFrame(
            {
                "timestamp": [3, 4],
                "open": [102, 103],
                "high": [103, 104],
                "low": [101, 102],
                "close": [102.5, 103.5],
                "volume": [14, 16],
            }
        )
        april.to_csv(self.base / "BTCUSDT_15m_2025_04.csv", index=False)
        may.to_csv(self.base / "BTCUSDT_15m_2025_05.csv", index=False)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_list_available_months(self):
        manager = MonthlyDatasetManager(self.base)
        self.assertEqual(manager.list_available_months("BTCUSDT"), ["2025-04", "2025-05"])

    def test_train_val_test_split_returns_ordered_dataframes(self):
        manager = MonthlyDatasetManager(self.base)
        train_df, val_df, test_df = manager.train_val_test_split(
            train_months=["2025-04"],
            val_months=["2025-05"],
            test_months=[],
        )
        self.assertEqual(len(train_df), 2)
        self.assertEqual(len(val_df), 2)
        self.assertTrue(test_df.empty)
        self.assertListEqual(train_df["timestamp"].tolist(), [1, 2])
        self.assertListEqual(val_df["timestamp"].tolist(), [3, 4])


if __name__ == "__main__":
    unittest.main()
