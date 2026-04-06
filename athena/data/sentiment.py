"""Sentiment provider with optional CSV lookup and safe neutral fallbacks."""

from __future__ import annotations

import asyncio
import csv
import logging
from bisect import bisect_right
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger("athena.sentiment")


class AthenaSentiment:
    def __init__(self, config: Dict):
        self.config = config
        root = Path(config.get("sentiment_csv_path", "data/raw/sentiment"))
        if not root.is_absolute():
            root = Path(__file__).resolve().parents[2] / root
        self.csv_root = root
        self._loaded = False
        self._rows_by_symbol: Dict[str, List[Tuple[int, Dict[str, float]]]] = {}

    async def get_live(self, symbol: str) -> Dict[str, float]:
        await asyncio.sleep(0)
        return self.get_historical(symbol, None)

    def get_historical(self, symbol: str, timestamp_ms: int | None = None) -> Dict[str, float]:
        self._ensure_loaded()
        rows = self._rows_by_symbol.get(symbol.upper()) or self._rows_by_symbol.get("*") or []
        if not rows:
            return self._neutral()
        if timestamp_ms is None:
            return dict(rows[-1][1])

        timestamps = [item[0] for item in rows]
        idx = bisect_right(timestamps, int(timestamp_ms)) - 1
        if idx < 0:
            return self._neutral()
        return dict(rows[idx][1])

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self.csv_root.exists():
            logger.info("Sentiment CSV path not found: %s. Using neutral fallback.", self.csv_root)
            return

        for csv_path in sorted(self.csv_root.rglob("*.csv")):
            try:
                with csv_path.open("r", encoding="utf-8", errors="ignore") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        ts = self._extract_timestamp(row)
                        if ts is None:
                            continue
                        symbol = str(
                            row.get("symbol")
                            or row.get("Symbol")
                            or row.get("coin")
                            or row.get("asset")
                            or "*"
                        ).upper()
                        payload = {
                            "score": self._extract_float(row, ["score", "sentiment", "compound", "polarity"], 0.0),
                            "volume": self._extract_float(row, ["volume", "mentions", "count"], 0.0),
                            "trend": self._extract_float(row, ["trend", "momentum", "delta"], 0.0),
                        }
                        self._rows_by_symbol.setdefault(symbol, []).append((ts, payload))
            except Exception as exc:
                logger.warning("Skipping unreadable sentiment CSV %s: %s", csv_path, exc)

        for symbol, rows in self._rows_by_symbol.items():
            rows.sort(key=lambda item: item[0])

    @staticmethod
    def _extract_float(row: Dict[str, str], keys: List[str], default: float) -> float:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default

    @staticmethod
    def _extract_timestamp(row: Dict[str, str]) -> int | None:
        for key in ["timestamp", "Timestamp", "unix", "time", "Time", "date", "Date"]:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                ts = int(float(value))
                return ts * 1000 if ts < 1_000_000_000_000 else ts
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _neutral() -> Dict[str, float]:
        return {"score": 0.0, "volume": 0.0, "trend": 0.0}
