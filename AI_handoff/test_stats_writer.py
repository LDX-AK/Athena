import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from athena.monitor.stats_writer import StatsWriter


class TestStatsWriter(unittest.IsolatedAsyncioTestCase):
    async def test_writes_live_stats_and_trade_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = str(Path(tmpdir) / "live_stats.json")
            history_path = str(Path(tmpdir) / "trade_history.json")

            cfg = {
                "flags": {"STREAMLIT_ENABLED": True},
                "monitor": {
                    "live_stats_path": stats_path,
                    "trade_history_path": history_path,
                    "flush_interval_sec": 0.05,
                    "max_history_trades": 1000,
                },
            }

            writer = StatsWriter(cfg)
            await writer.start()
            writer.update_live_stats({"balance": 10100.0, "daily_pnl": 100.0, "total_pnl": 100.0, "total_trades": 1, "win_rate": 1.0, "open_positions": 0})
            writer.log_trade({"symbol": "BTC/USDT", "pnl": 10.0, "result": "TP", "direction": 1, "balance": 10010.0})
            await asyncio.sleep(0.12)
            await writer.stop()

            self.assertTrue(Path(stats_path).exists())
            self.assertTrue(Path(history_path).exists())

            with open(stats_path, "r", encoding="utf-8") as fh:
                stats = json.load(fh)
            self.assertIn("timestamp", stats)
            self.assertEqual(stats["balance"], 10100.0)

            with open(history_path, "r", encoding="utf-8") as fh:
                history = json.load(fh)
            self.assertEqual(len(history), 1)
            self.assertIn("timestamp", history[0])
            self.assertEqual(history[0]["symbol"], "BTC/USDT")

    async def test_history_is_bounded_by_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "trade_history.json"
            seed = [{"symbol": "X", "pnl": float(i)} for i in range(5)]
            with open(history_path, "w", encoding="utf-8") as fh:
                json.dump(seed, fh)

            cfg = {
                "flags": {"STREAMLIT_ENABLED": True},
                "monitor": {
                    "live_stats_path": str(Path(tmpdir) / "live_stats.json"),
                    "trade_history_path": str(history_path),
                    "flush_interval_sec": 0.05,
                    "max_history_trades": 3,
                },
            }

            writer = StatsWriter(cfg)
            await writer.start()
            writer.log_trade({"symbol": "A", "pnl": 10.0})
            writer.log_trade({"symbol": "B", "pnl": 20.0})
            await asyncio.sleep(0.12)
            await writer.stop()

            with open(history_path, "r", encoding="utf-8") as fh:
                history = json.load(fh)

            self.assertEqual(len(history), 3)
            self.assertEqual(history[-1]["symbol"], "B")


if __name__ == "__main__":
    unittest.main()
