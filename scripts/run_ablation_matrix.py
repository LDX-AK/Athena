#!/usr/bin/env python3
"""Run a feature-group ablation matrix using the Athena Strategy Factory core."""

from __future__ import annotations

import copy
import json
import sys
from collections import OrderedDict
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


def build_redesign_plan(ablation: AblationMatrix) -> OrderedDict[str, dict]:
    requested_scenarios = ["baseline", "no_rolling", "no_regime", "core_compact", "price_action_core"]
    plan: OrderedDict[str, dict] = OrderedDict()

    for scenario_name, disabled_groups in ablation.unique_scenarios(requested_scenarios).items():
        plan[scenario_name] = {
            "disabled_groups": disabled_groups,
            "training_overrides": {},
        }

    plan["atr_hilo_core"] = {
        "disabled_groups": ["orderbook", "rolling", "time", "sentiment"],
        "training_overrides": {
            "labeling_mode": "atr_hilo",
            "atr_tp_mult": 0.8,
            "atr_sl_mult": 0.6,
        },
    }
    return plan


def apply_redesign_overrides(cfg: dict, disabled_groups: list[str], training_overrides: dict) -> dict:
    feature_groups = cfg.setdefault("feature_groups", {})
    for group in AblationMatrix.DEFAULT_GROUPS:
        feature_groups.setdefault(group, True)
    for group in disabled_groups:
        feature_groups[group] = False

    training_cfg = cfg.setdefault("training", {})
    training_cfg.update(training_overrides or {})
    return cfg


def main() -> None:
    base_cfg = ATHENA_CONFIG
    timeframe = str(base_cfg.get("experiment", {}).get("timeframe", "15m"))
    dataset = MonthlyDatasetManager(ROOT / "data" / "raw" / "ohlcv", timeframe=timeframe)
    registry = ExperimentRegistry(base_cfg.get("experiment", {}).get("storage_path", ROOT / "data" / "experiments"))
    validator = WalkForwardValidator(base_cfg, dataset, timeframe=timeframe)
    ablation = AblationMatrix(base_cfg)

    walk = base_cfg.get("experiment", {}).get("walk_forward") or base_cfg.get("training", {}).get("walk_forward", {})
    train_df, val_df, test_df = validator.load_splits(
        walk.get("train_months", ["2025-04", "2025-05"]),
        walk.get("validation_months", ["2025-06"]),
        walk.get("test_months", ["2025-07", "2025-08", "2025-09"]),
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    scenario_plan = build_redesign_plan(ablation)
    results = {}
    out_path = RESULTS_DIR / f"ablation_matrix_{timeframe}.json"

    for scenario_name, spec in scenario_plan.items():
        cfg = apply_redesign_overrides(
            copy.deepcopy(base_cfg),
            spec.get("disabled_groups", []),
            spec.get("training_overrides", {}),
        )
        cfg["symbols"] = ["BTC/USDT"]
        cfg["timeframe"] = timeframe
        cfg["runtime_timeframe"] = timeframe
        cfg["training_timeframe"] = timeframe
        cfg["flags"]["SENTIMENT_ENABLED"] = False
        cfg["flags"]["SENTIMENT_BACKTEST"] = False
        cfg["flags"]["MTF_FILTER_ENABLED"] = False

        model_path = MODEL_DIR / f"athena_brain_{timeframe}_{scenario_name}.pkl"
        trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
        trainer.train(dataset.to_ohlcv_list(train_df), save_path=str(model_path))

        val_result = validator.run_backtest(model_path, val_df, profile="conservative")
        test_result = validator.run_backtest(model_path, test_df, profile="conservative")
        payload = {
            "disabled_groups": spec.get("disabled_groups", []),
            "labeling_mode": cfg.get("training", {}).get("labeling_mode", "legacy"),
            "training_overrides": spec.get("training_overrides", {}),
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
