from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd


OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class MonthlyDatasetManager:
    """Manage monthly OHLCV datasets for walk-forward experiments."""

    def __init__(self, base_path: str | Path = "data/raw/ohlcv", timeframe: str = "15m"):
        self.base_path = Path(base_path)
        self.timeframe = str(timeframe)

    def list_available_months(self, symbol: str = "BTCUSDT") -> List[str]:
        pattern = f"{symbol}_{self.timeframe}_*.csv"
        months = []
        for path in sorted(self.base_path.glob(pattern)):
            parts = path.stem.split("_")
            if len(parts) >= 4 and parts[-2].isdigit() and parts[-1].isdigit():
                months.append(f"{parts[-2]}-{parts[-1]}")
        return sorted(dict.fromkeys(months))

    def month_path(self, month: str, symbol: str = "BTCUSDT") -> Path:
        normalized = str(month).replace("-", "_")
        return self.base_path / f"{symbol}_{self.timeframe}_{normalized}.csv"

    def load_month(self, month: str, symbol: str = "BTCUSDT") -> pd.DataFrame:
        path = self.month_path(month, symbol=symbol)
        if not path.exists():
            raise FileNotFoundError(f"Monthly OHLCV file not found: {path}")
        df = pd.read_csv(path)
        missing = [col for col in OHLCV_COLUMNS if col not in df.columns]
        if missing:
            raise ValueError(f"Monthly dataset {path} is missing columns: {', '.join(missing)}")
        return df[OHLCV_COLUMNS].sort_values("timestamp").reset_index(drop=True)

    def load_period(self, months: Iterable[str], symbol: str = "BTCUSDT") -> pd.DataFrame:
        months = list(months)
        if not months:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        frames = [self.load_month(month, symbol=symbol) for month in months]
        return pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)

    def train_val_test_split(
        self,
        train_months: Iterable[str],
        val_months: Iterable[str],
        test_months: Iterable[str],
        symbol: str = "BTCUSDT",
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return (
            self.load_period(train_months, symbol=symbol),
            self.load_period(val_months, symbol=symbol),
            self.load_period(test_months, symbol=symbol),
        )

    @staticmethod
    def to_ohlcv_list(df: pd.DataFrame) -> List[List[float]]:
        if df.empty:
            return []
        return df[OHLCV_COLUMNS].astype(float).values.tolist()
