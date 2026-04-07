from __future__ import annotations

import copy
from pathlib import Path
from typing import Dict, Iterable, Tuple

from athena.backtest.runner import AthenaBacktest
from athena.data.sentiment import AthenaSentiment
from athena.features.engineer import AthenaEngineer
from .dataset import MonthlyDatasetManager


class WalkForwardValidator:
    """Helper for loading time-based splits and evaluating saved models."""

    def __init__(
        self,
        base_config: Dict,
        dataset_manager: MonthlyDatasetManager | None = None,
        timeframe: str | None = None,
    ):
        self.base_config = copy.deepcopy(base_config)
        self.dataset_manager = dataset_manager or MonthlyDatasetManager()
        self.timeframe = str(
            timeframe
            or getattr(self.dataset_manager, "timeframe", None)
            or self.base_config.get("experiment", {}).get("timeframe")
            or self.base_config.get("training_timeframe")
            or self.base_config.get("runtime_timeframe")
            or self.base_config.get("timeframe", "15m")
        )

    def load_splits(
        self,
        train_months: Iterable[str],
        validation_months: Iterable[str],
        test_months: Iterable[str],
        symbol_slug: str = "BTCUSDT",
    ):
        return self.dataset_manager.train_val_test_split(
            train_months=train_months,
            val_months=validation_months,
            test_months=test_months,
            symbol=symbol_slug,
        )

    def profile_config(self, model_path: str | Path, profile: str = "conservative") -> Dict:
        cfg = copy.deepcopy(self.base_config)
        cfg["symbols"] = ["BTC/USDT"]
        cfg["timeframe"] = self.timeframe
        cfg["runtime_timeframe"] = self.timeframe
        cfg["training_timeframe"] = self.timeframe
        cfg["flags"]["MTF_FILTER_ENABLED"] = False
        cfg["model_path"] = str(model_path)

        if profile == "conservative":
            cfg["risk"]["max_position_pct"] = 0.01
            cfg["risk"]["min_confidence"] = 0.55
            cfg["risk"]["stop_loss_pct"] = 0.0025
            cfg["risk"]["take_profit_pct"] = 0.0050
        else:
            cfg["risk"]["max_position_pct"] = 0.03
            cfg["risk"]["min_confidence"] = 0.35
            cfg["risk"]["stop_loss_pct"] = 0.0040
            cfg["risk"]["take_profit_pct"] = 0.0100
        return cfg

    def run_backtest(self, model_path: str | Path, df, profile: str = "conservative") -> Dict:
        cfg = self.profile_config(model_path=model_path, profile=profile)
        backtest = AthenaBacktest(AthenaEngineer(cfg), AthenaSentiment(cfg), cfg)
        ohlcv_data = self.dataset_manager.to_ohlcv_list(df)
        return backtest.run(ohlcv_data, initial_balance=10_000.0, symbol="BTC/USDT") or {"total_trades": 0}

    @staticmethod
    def score_result(result: Dict) -> float:
        if not result:
            return -1e9
        sharpe = float(result.get("sharpe_ratio", -99.0) or -99.0)
        ret = float(result.get("total_return_pct", -99.0) or -99.0)
        pf = float(result.get("profit_factor", 0.0) or 0.0)
        mdd = float(result.get("max_drawdown_pct", 100.0) or 100.0)
        return sharpe * 100.0 + ret * 10.0 + min(pf, 3.0) * 5.0 - mdd
