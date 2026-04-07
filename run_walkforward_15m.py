#!/usr/bin/env python3
"""Train and evaluate a safer 15m Athena model using a strict time-based walk-forward split."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Dict, Iterable, List

from athena.backtest.runner import AthenaBacktest, load_ohlcv_from_csv
from athena.config import ATHENA_CONFIG
from athena.data.sentiment import AthenaSentiment
from athena.features.engineer import AthenaEngineer
from athena.model.signal import AthenaTrainer

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw" / "ohlcv"
RESULTS_DIR = ROOT / "data" / "results"
MODEL_DIR = ROOT / "athena" / "model"


CANDIDATES = {
    "deepseek_like_v1": {
        "windows": [10, 30, 60],
        "feature_groups": {"rolling": False, "sentiment": False},
        "model_params": {"n_estimators": 180, "max_depth": 4, "num_leaves": 15, "min_child_samples": 100},
    },
    "deepseek_like_v2": {
        "windows": [15, 60],
        "feature_groups": {"rolling": False, "sentiment": False, "regime": False},
        "model_params": {"n_estimators": 160, "max_depth": 4, "num_leaves": 15, "min_child_samples": 120},
    },
    "deepseek_control": {
        "windows": [5, 10, 15, 30, 60, 120],
        "feature_groups": {"sentiment": False},
        "model_params": {"n_estimators": 200, "max_depth": 4, "num_leaves": 15, "min_child_samples": 100},
    },
    "no_rolling_final": {
        "windows": [5, 10, 15, 30, 60, 120],
        "feature_groups": {"rolling": False, "sentiment": False, "regime": True},
        "model_params": {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 100,
            "subsample": 0.7,
            "colsample_bytree": 0.7,
        },
    },
}


def parse_months(value: str | None, default: Iterable[str] | None = None) -> List[str]:
    if value is None:
        return list(default or [])
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strict walk-forward training/evaluation for Athena 15m candidates")
    parser.add_argument(
        "--candidate",
        default="all",
        help="Candidate name to run, comma-separated list, or 'all'",
    )
    parser.add_argument("--train-months", help="Comma-separated train months like 2025-04,2025-05")
    parser.add_argument("--validation-months", help="Comma-separated validation months")
    parser.add_argument("--test-months", help="Comma-separated holdout/test months")
    parser.add_argument(
        "--output-json",
        help="Optional output JSON path; defaults to data/results/walkforward_15m_deepseek_like.json",
    )
    return parser.parse_args()


def resolve_candidate_names(value: str | None) -> List[str]:
    if not value or value == "all":
        return list(CANDIDATES.keys())
    names = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [name for name in names if name not in CANDIDATES]
    if unknown:
        raise KeyError(f"Unknown candidate(s): {', '.join(unknown)}")
    return names


def month_file(month: str) -> Path:
    return RAW_DIR / f"BTCUSDT_15m_{month.replace('-', '_')}.csv"


def load_months(months: Iterable[str]) -> List[List[float]]:
    rows: List[List[float]] = []
    for month in months:
        path = month_file(month)
        if not path.exists():
            raise FileNotFoundError(
                f"Missing monthly CSV: {path}. Run scripts/fetch_15m_monthly.py first."
            )
        rows.extend(load_ohlcv_from_csv(str(path), symbol=None, max_rows=None, window="first"))
    return rows


def make_cfg(candidate_name: str, profile: str, for_training: bool = False) -> dict:
    cfg = copy.deepcopy(ATHENA_CONFIG)
    cfg["symbols"] = ["BTC/USDT"]
    cfg["timeframe"] = "15m"
    cfg["runtime_timeframe"] = "15m"
    cfg["training_timeframe"] = "15m"
    cfg["flags"]["SENTIMENT_ENABLED"] = False
    cfg["flags"]["SENTIMENT_BACKTEST"] = False
    cfg["flags"]["MTF_FILTER_ENABLED"] = False
    cfg["data"]["lookback_candles"] = 200

    candidate = CANDIDATES[candidate_name]
    cfg["data"]["windows"] = list(candidate["windows"])
    for group_name, enabled in candidate["feature_groups"].items():
        cfg.setdefault("feature_groups", {})[group_name] = enabled
    cfg.setdefault("training", {}).setdefault("model_params", {}).update(candidate["model_params"])

    if not for_training:
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


def score_result(result: Dict) -> float:
    if not result:
        return -1e9
    sharpe = float(result.get("sharpe_ratio", -99.0) or -99.0)
    ret = float(result.get("total_return_pct", -99.0) or -99.0)
    pf = float(result.get("profit_factor", 0.0) or 0.0)
    mdd = float(result.get("max_drawdown_pct", 100.0) or 100.0)
    return sharpe * 100.0 + ret * 10.0 + min(pf, 3.0) * 5.0 - mdd


def run_profile(model_path: Path, candidate_name: str, months: Iterable[str], profile: str) -> Dict:
    cfg = make_cfg(candidate_name, profile)
    cfg["model_path"] = str(model_path)
    data = load_months(months)
    backtest = AthenaBacktest(AthenaEngineer(cfg), AthenaSentiment(cfg), cfg)
    return backtest.run(data, initial_balance=10_000.0, symbol="BTC/USDT") or {"total_trades": 0}


def train_candidate(candidate_name: str, train_months: Iterable[str]) -> Path:
    cfg = make_cfg(candidate_name, profile="conservative", for_training=True)
    out_path = MODEL_DIR / f"athena_brain_15m_{candidate_name}.pkl"
    trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
    trainer.train(load_months(train_months), save_path=str(out_path))
    return out_path


def main() -> None:
    args = parse_args()
    walk_forward = (
        ATHENA_CONFIG.get("experiment", {}).get("walk_forward")
        or ATHENA_CONFIG.get("training", {}).get("walk_forward", {})
    )
    train_months = parse_months(args.train_months, walk_forward.get("train_months", ["2025-04", "2025-05"]))
    validation_months = parse_months(args.validation_months, walk_forward.get("validation_months", ["2025-06"]))
    test_months = parse_months(args.test_months, walk_forward.get("test_months", ["2025-07", "2025-08", "2025-09"]))
    candidate_names = resolve_candidate_names(args.candidate)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    summary = {
        "train_months": train_months,
        "validation_months": validation_months,
        "test_months": test_months,
        "candidates": {},
    }

    best_name = None
    best_score = -1e18
    best_model_path: Path | None = None

    for candidate_name in candidate_names:
        print(f"\n=== candidate: {candidate_name} ===")
        model_path = train_candidate(candidate_name, train_months)
        validation = {
            "conservative": run_profile(model_path, candidate_name, validation_months, "conservative"),
            "aggressive": run_profile(model_path, candidate_name, validation_months, "aggressive"),
        }
        validation_score = (
            score_result(validation["conservative"]) + score_result(validation["aggressive"])
        ) / 2.0
        summary["candidates"][candidate_name] = {
            "model_path": str(model_path),
            "validation": validation,
            "validation_score": validation_score,
        }
        print(f"validation_score={validation_score:.2f}")
        if validation_score > best_score:
            best_score = validation_score
            best_name = candidate_name
            best_model_path = model_path

    assert best_name is not None and best_model_path is not None
    holdout = {
        "conservative": run_profile(best_model_path, best_name, test_months, "conservative"),
        "aggressive": run_profile(best_model_path, best_name, test_months, "aggressive"),
    }

    summary["best_candidate"] = best_name
    summary["best_model_path"] = str(best_model_path)
    summary["holdout"] = holdout

    out_json = Path(args.output_json) if args.output_json else RESULTS_DIR / "walkforward_15m_deepseek_like.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved walk-forward summary to {out_json}")
    print(json.dumps({"best_candidate": best_name, "holdout": holdout}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
