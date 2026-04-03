"""
athena/monitor/stats_writer.py - runtime telemetry writer

Writes backward-compatible dashboard files without blocking the trading loop:
- data/live_stats.json (atomic overwrite)
- data/trade_history.json (bounded JSON array)
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("athena.monitor")


class StatsWriter:
    def __init__(self, config: Dict):
        flags = config.get("flags", {})
        monitor = config.get("monitor", {})

        self.enabled = bool(flags.get("STREAMLIT_ENABLED", True))
        self.stats_path = Path(monitor.get("live_stats_path", "data/live_stats.json"))
        self.history_path = Path(monitor.get("trade_history_path", "data/trade_history.json"))
        self.flush_interval = float(monitor.get("flush_interval_sec", 5.0))
        self.max_history_trades = int(monitor.get("max_history_trades", 1000))

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._trade_buffer: List[Dict] = []
        self._last_stats: Optional[Dict] = None

        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    async def start(self):
        if not self.enabled or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._flush_loop())
        logger.info("StatsWriter started: %s | %s", self.stats_path, self.history_path)

    async def stop(self):
        if not self.enabled:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self._flush(force=True)
        logger.info("StatsWriter stopped")

    def update_live_stats(self, stats: Dict):
        if not self.enabled:
            return
        payload = dict(stats)
        payload["timestamp"] = int(time.time())
        self._last_stats = payload

    def log_trade(self, trade: Dict):
        if not self.enabled:
            return
        payload = dict(trade)
        payload["timestamp"] = int(time.time())
        self._trade_buffer.append(payload)

    async def _flush_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush(force=False)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("StatsWriter flush loop error: %s", exc)

    async def _flush(self, force: bool):
        if self._last_stats is None and not self._trade_buffer:
            return

        try:
            await asyncio.to_thread(self._sync_flush)
        except Exception as exc:
            logger.warning("StatsWriter flush failed: %s", exc)
            if force:
                self._emergency_write_trades()

    def _sync_flush(self):
        if self._last_stats is not None:
            tmp = self.stats_path.with_suffix(self.stats_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self._last_stats, fh, ensure_ascii=False)
            tmp.replace(self.stats_path)

        if self._trade_buffer:
            history = self._read_history()
            history.extend(self._trade_buffer)
            if len(history) > self.max_history_trades:
                history = history[-self.max_history_trades :]

            tmp = self.history_path.with_suffix(self.history_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(history, fh, ensure_ascii=False)
            tmp.replace(self.history_path)
            self._trade_buffer.clear()

    def _read_history(self) -> List[Dict]:
        if not self.history_path.exists():
            return []
        try:
            with self.history_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _emergency_write_trades(self):
        if not self._trade_buffer:
            return

        emergency_path = self.history_path.with_suffix(self.history_path.suffix + ".emergency")
        try:
            with emergency_path.open("a", encoding="utf-8") as fh:
                for item in self._trade_buffer:
                    fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("StatsWriter emergency write failed: %s", exc)
