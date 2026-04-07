#!/usr/bin/env python3
"""Run a feature-group ablation matrix using the Athena Strategy Factory core."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from athena.config import ATHENA_CONFIG
from athena.experiment.ablation import AblationMatrix
from athena.experiment.dataset import MonthlyDatasetManager
from athena.experiment.registry import ExperimentRegistry
from athena.experiment.validator import WalkForwardValidator
from athena.features.engineer import AthenaEngineer
from athena.model.signal import AthenaTrainer

RESULTS_DIR = ROOT / "data" / "results"
MODEL_DIR = ROOT / "athena" / "model"


def main() -> None:
    base_cfg = ATHENA_CONFIG
    dataset = MonthlyDatasetManager(ROOT / "data" / "raw" / "ohlcv")
    registry = ExperimentRegistry(base_cfg.get("experiment", {}).get("storage_path", ROOT / "data" / "experiments"))
    validator = WalkForwardValidator(base_cfg, dataset)
    ablation = AblationMatrix(base_cfg)

    walk = base_cfg.get("experiment", {}).get("walk_forward") or base_cfg.get("training", {}).get("walk_forward", {})
    train_df, val_df, test_df = validator.load_splits(
        walk.get("train_months", ["2025-04", "2025-05"]),
        walk.get("validation_months", ["2025-06"]),
        walk.get("test_months", ["2025-07", "2025-08", "2025-09"]),
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    requested_scenarios = ["baseline", "no_rolling", "no_sentiment", "no_rolling_sentiment", "no_regime", "minimal"]
    scenario_plan = ablation.unique_scenarios(requested_scenarios)
    results = {}
    out_path = RESULTS_DIR / "ablation_matrix_15m.json"

    for scenario_name, disabled_groups in scenario_plan.items():
        cfg = ablation.apply_scenario(scenario_name)
        cfg["symbols"] = ["BTC/USDT"]
        cfg["timeframe"] = "15m"
        cfg["runtime_timeframe"] = "15m"
        cfg["training_timeframe"] = "15m"
        cfg["flags"]["SENTIMENT_ENABLED"] = False
        cfg["flags"]["SENTIMENT_BACKTEST"] = False
        cfg["flags"]["MTF_FILTER_ENABLED"] = False

        model_path = MODEL_DIR / f"athena_brain_15m_{scenario_name}.pkl"
        trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
        trainer.train(dataset.to_ohlcv_list(train_df), save_path=str(model_path))

        val_result = validator.run_backtest(model_path, val_df, profile="conservative")
        test_result = validator.run_backtest(model_path, test_df, profile="conservative")
        payload = {
            "disabled_groups": disabled_groups,
            "validation": val_result,
            "holdout": test_result,
            "validation_score": validator.score_result(val_result),
            "holdout_score": validator.score_result(test_result),
            "model_path": str(model_path),
        }
        results[scenario_name] = payload
        registry.save_experiment(
            name=f"ablation_{scenario_name}",
            results=payload,
            config_snapshot=cfg,
            model_path=model_path,
        )
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Saved ablation matrix to {out_path}")
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
