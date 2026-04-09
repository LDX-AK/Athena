#!/usr/bin/env python3
"""Train and evaluate Athena models with a strict time-based walk-forward split across timeframes."""

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
BASE_TIMEFRAME = str(ATHENA_CONFIG.get("experiment", {}).get("timeframe", "15m"))


CANDIDATES = {
    "deepseek_like_v1": {
        "windows": [10, 30, 60],
        "feature_groups": {"rolling": False, "sentiment": False},
        "model_params": {"n_estimators": 180, "max_depth": 4, "num_leaves": 15, "min_child_samples": 100},
        "training_overrides": {},
    },
    "deepseek_like_v2": {
        "windows": [15, 60],
        "feature_groups": {"rolling": False, "sentiment": False, "regime": False},
        "model_params": {"n_estimators": 160, "max_depth": 4, "num_leaves": 15, "min_child_samples": 120},
        "training_overrides": {},
    },
    "deepseek_control": {
        "windows": [5, 10, 15, 30, 60, 120],
        "feature_groups": {"sentiment": False},
        "model_params": {"n_estimators": 200, "max_depth": 4, "num_leaves": 15, "min_child_samples": 100},
        "training_overrides": {},
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
        "training_overrides": {},
    },
    "core_compact": {
        "windows": [5, 10, 15, 30, 60, 120],
        "feature_groups": {
            "orderbook": False,
            "rolling": False,
            "time": False,
            "sentiment": False,
            "regime": True,
        },
        "model_params": {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 100,
            "subsample": 0.7,
            "colsample_bytree": 0.7,
        },
        "training_overrides": {},
    },
    "price_action_core": {
        "windows": [5, 10, 15, 30, 60, 120],
        "feature_groups": {
            "orderbook": False,
            "orderflow": False,
            "rolling": False,
            "time": False,
            "sentiment": False,
            "regime": True,
        },
        "model_params": {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 100,
            "subsample": 0.7,
            "colsample_bytree": 0.7,
        },
        "training_overrides": {},
    },
    "atr_hilo_core": {
        "windows": [5, 10, 15, 30, 60, 120],
        "feature_groups": {
            "orderbook": False,
            "rolling": False,
            "time": False,
            "sentiment": False,
            "regime": True,
        },
        "model_params": {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 100,
            "subsample": 0.7,
            "colsample_bytree": 0.7,
        },
        "training_overrides": {
            "labeling_mode": "atr_hilo",
            "atr_tp_mult": 0.8,
            "atr_sl_mult": 0.6,
        },
    },
}


def parse_months(value: str | None, default: Iterable[str] | None = None) -> List[str]:
    if value is None:
        return list(default or [])
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_csv_strings(value: str | None, default: Iterable[str] | None = None) -> List[str]:
    if value is None:
        return list(default or [])
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def parse_csv_ints(value: str | None, default: Iterable[int] | None = None) -> List[int]:
    if value is None:
        return list(default or [])
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def tf_to_minutes(timeframe: str) -> int:
    tf = str(timeframe).strip().lower()
    if tf.endswith("m"):
        return max(1, int(tf[:-1]))
    if tf.endswith("h"):
        return max(1, int(tf[:-1]) * 60)
    if tf.endswith("d"):
        return max(1, int(tf[:-1]) * 1440)
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def scaled_windows_for_timeframe(timeframe: str, windows: Iterable[int]) -> List[int]:
    base_minutes = tf_to_minutes(BASE_TIMEFRAME)
    target_minutes = tf_to_minutes(timeframe)
    scaled = [max(2, int(round(int(window) * base_minutes / target_minutes))) for window in windows]
    return sorted(dict.fromkeys(scaled))


def scaled_lookahead_for_timeframe(timeframe: str, base_lookahead: int) -> int:
    base_minutes = tf_to_minutes(BASE_TIMEFRAME)
    target_minutes = tf_to_minutes(timeframe)
    return max(2, int(round(int(base_lookahead) * base_minutes / target_minutes)))


def resolve_mtf_timeframe(timeframe: str) -> str:
    hierarchy = ATHENA_CONFIG.get("timeframe_hierarchy", {})
    context = str(hierarchy.get("context", "1h"))
    confirm = str(hierarchy.get("confirm", "30m"))
    signal = str(hierarchy.get("signal", "15m"))
    entry = str(hierarchy.get("entry", "5m"))

    if timeframe == entry:
        return signal
    if timeframe == signal:
        return confirm
    if timeframe == confirm:
        return context
    return context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strict walk-forward training/evaluation for Athena candidates")
    parser.add_argument(
        "--candidate",
        default="all",
        help="Candidate name to run, comma-separated list, or 'all'",
    )
    parser.add_argument(
        "--timeframe",
        default=BASE_TIMEFRAME,
        help="Runtime/training timeframe, e.g. 5m, 15m, 30m, 1h",
    )
    parser.add_argument("--train-months", help="Comma-separated train months like 2025-04,2025-05")
    parser.add_argument("--validation-months", help="Comma-separated validation months")
    parser.add_argument("--test-months", help="Comma-separated holdout/test months")
    parser.add_argument(
        "--macro-filter-tf",
        help="Override the higher-timeframe trend filter, e.g. 1h or 30m; use 'off' to disable it",
    )
    parser.add_argument(
        "--macro-filter-threshold",
        type=float,
        help="Optional override for the higher-timeframe trend threshold",
    )
    parser.add_argument(
        "--macro-filter-allow-neutral",
        action="store_true",
        help="Allow both directions when the higher-timeframe trend is neutral instead of blocking flat regimes",
    )
    parser.add_argument(
        "--adaptive-mode",
        action="store_true",
        help="Enable the experimental adaptive risk-profile controller during validation/holdout backtests",
    )
    parser.add_argument(
        "--router-enabled",
        action="store_true",
        help="Enable the v3 two-level regime/session router during validation and holdout backtests",
    )
    parser.add_argument(
        "--direction",
        default="both",
        choices=["both", "long", "short"],
        help="Optionally scope the strategy to long-only or short-only signals",
    )
    parser.add_argument(
        "--regime",
        default="all",
        choices=["all", "quiet", "normal", "hot"],
        help="Optionally scope entries to a specific volatility regime bucket",
    )
    parser.add_argument(
        "--meta-hours",
        help="Comma-separated UTC trading hours allowlist for the diagnostics-driven meta-filter",
    )
    parser.add_argument(
        "--meta-regimes",
        help="Comma-separated regime allowlist for the meta-filter, e.g. quiet,normal",
    )
    parser.add_argument(
        "--meta-min-confidence",
        type=float,
        help="Optional lower confidence bound for the meta-filter",
    )
    parser.add_argument(
        "--meta-max-confidence",
        type=float,
        help="Optional upper confidence bound for the meta-filter",
    )
    parser.add_argument(
        "--output-json",
        help="Optional output JSON path; defaults to data/results/walkforward_<tf>_deepseek_like.json",
    )
    parser.add_argument(
        "--model-dir",
        help="Optional directory for trained model artifacts; useful for keeping v2/v3 outputs separated",
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


def month_file(month: str, timeframe: str = "15m") -> Path:
    return RAW_DIR / f"BTCUSDT_{timeframe}_{month.replace('-', '_')}.csv"


def load_months(months: Iterable[str], timeframe: str = "15m") -> List[List[float]]:
    rows: List[List[float]] = []
    for month in months:
        path = month_file(month, timeframe=timeframe)
        if not path.exists():
            raise FileNotFoundError(
                f"Missing monthly CSV: {path}. Run scripts/fetch_15m_monthly.py --timeframe {timeframe} first."
            )
        rows.extend(load_ohlcv_from_csv(str(path), symbol=None, max_rows=None, window="first"))
    return rows


def make_cfg(
    candidate_name: str,
    profile: str,
    timeframe: str = "15m",
    for_training: bool = False,
    adaptive_mode: bool = False,
    macro_filter_tf: str | None = None,
    macro_filter_threshold: float | None = None,
    macro_filter_allow_neutral: bool | None = None,
    direction_filter: str = "both",
    regime_filter: str = "all",
    meta_allowed_hours: List[int] | None = None,
    meta_allowed_regimes: List[str] | None = None,
    meta_min_confidence: float | None = None,
    meta_max_confidence: float | None = None,
    router_enabled: bool = False,
) -> dict:
    timeframe = str(timeframe).strip()
    cfg = copy.deepcopy(ATHENA_CONFIG)
    cfg["symbols"] = ["BTC/USDT"]
    cfg["timeframe"] = timeframe
    cfg["runtime_timeframe"] = timeframe
    cfg["training_timeframe"] = timeframe
    cfg.setdefault("adaptive_mode", {})["enabled"] = bool(adaptive_mode) and not for_training

    hierarchy = ATHENA_CONFIG.get("timeframe_hierarchy", {})
    context_tf = str(hierarchy.get("context", "1h"))
    higher_tf = resolve_mtf_timeframe(timeframe)
    macro_cfg = dict(cfg.get("macro_filter", {}))

    if macro_filter_tf:
        if str(macro_filter_tf).strip().lower() == "off":
            cfg["tf_filter"] = timeframe
            cfg["mtf_timeframe"] = timeframe
            cfg.setdefault("flags", {})["MTF_FILTER_ENABLED"] = False
            macro_cfg["enabled"] = False
        else:
            override_tf = str(macro_filter_tf).strip()
            cfg["tf_filter"] = override_tf
            cfg["mtf_timeframe"] = override_tf
            cfg.setdefault("flags", {})["MTF_FILTER_ENABLED"] = True
            macro_cfg["enabled"] = True
            macro_cfg["timeframe"] = override_tf
    else:
        cfg["tf_filter"] = higher_tf
        cfg["mtf_timeframe"] = higher_tf
        cfg.setdefault("flags", {})["MTF_FILTER_ENABLED"] = timeframe != context_tf
        macro_cfg.setdefault("enabled", False)
        macro_cfg.setdefault("timeframe", str(cfg["mtf_timeframe"]))

    if macro_filter_threshold is not None:
        macro_cfg["trend_threshold"] = float(macro_filter_threshold)
        cfg["mtf_min_trend"] = float(macro_filter_threshold)
    if macro_filter_allow_neutral is not None:
        macro_cfg["allow_neutral"] = bool(macro_filter_allow_neutral)

    cfg["macro_filter"] = macro_cfg
    direction_filter = str(direction_filter).strip().lower()
    regime_filter = str(regime_filter).strip().lower()
    cfg.setdefault("experiment", {})["direction_filter"] = direction_filter
    cfg["experiment"]["regime_filter"] = regime_filter
    cfg.setdefault("training", {})["label_target"] = direction_filter if direction_filter in {"long", "short"} else "both"
    cfg.setdefault("router", {})["enabled"] = bool(router_enabled) and not for_training

    meta_filter = {}
    if meta_allowed_hours:
        meta_filter["allowed_hours"] = [int(hour) % 24 for hour in meta_allowed_hours]
    if meta_allowed_regimes:
        meta_filter["allowed_regimes"] = [str(name).strip().lower() for name in meta_allowed_regimes if str(name).strip()]
    if meta_min_confidence is not None:
        meta_filter["min_confidence"] = float(meta_min_confidence)
        if not for_training:
            cfg["risk"]["min_confidence"] = float(meta_min_confidence)
    if meta_max_confidence is not None:
        meta_filter["max_confidence"] = float(meta_max_confidence)
    cfg["experiment"]["meta_filter"] = meta_filter

    candidate = CANDIDATES[candidate_name]
    scaled_windows = scaled_windows_for_timeframe(timeframe, candidate["windows"])
    cfg.setdefault("data", {})["windows"] = scaled_windows
    cfg["data"]["lookback_candles"] = max(200, max(scaled_windows) + 20)
    cfg.setdefault("training", {})["label_lookahead"] = scaled_lookahead_for_timeframe(
        timeframe,
        int(ATHENA_CONFIG.get("training", {}).get("label_lookahead", 10)),
    )

    for group_name, enabled in candidate["feature_groups"].items():
        cfg.setdefault("feature_groups", {})[group_name] = enabled
    cfg.setdefault("training", {}).setdefault("model_params", {}).update(candidate["model_params"])
    cfg.setdefault("training", {}).update(candidate.get("training_overrides", {}))
    cfg.setdefault("training", {}).update(candidate.get("training_overrides", {}))

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
    sharpe = float(result.get("sharpe_ratio", result.get("sharpe", -10.0)))
    ret = float(result.get("return_pct", result.get("total_return_pct", -100.0)))
    pf = float(result.get("profit_factor", 0.0))
    mdd = abs(float(result.get("max_drawdown_pct", result.get("max_drawdown", 100.0))))
    return sharpe * 100.0 + ret * 10.0 + min(pf, 3.0) * 5.0 - mdd


def run_profile(
    model_path: Path,
    candidate_name: str,
    months: Iterable[str],
    profile: str,
    timeframe: str,
    adaptive_mode: bool = False,
    macro_filter_tf: str | None = None,
    macro_filter_threshold: float | None = None,
    macro_filter_allow_neutral: bool | None = None,
    direction_filter: str = "both",
    regime_filter: str = "all",
    meta_allowed_hours: List[int] | None = None,
    meta_allowed_regimes: List[str] | None = None,
    meta_min_confidence: float | None = None,
    meta_max_confidence: float | None = None,
    router_enabled: bool = False,
) -> Dict:
    cfg = make_cfg(
        candidate_name,
        profile,
        timeframe=timeframe,
        adaptive_mode=adaptive_mode,
        macro_filter_tf=macro_filter_tf,
        macro_filter_threshold=macro_filter_threshold,
        macro_filter_allow_neutral=macro_filter_allow_neutral,
        direction_filter=direction_filter,
        regime_filter=regime_filter,
        meta_allowed_hours=meta_allowed_hours,
        meta_allowed_regimes=meta_allowed_regimes,
        meta_min_confidence=meta_min_confidence,
        meta_max_confidence=meta_max_confidence,
        router_enabled=router_enabled,
    )
    cfg["model_path"] = str(model_path)
    data = load_months(months, timeframe=timeframe)
    backtest = AthenaBacktest(AthenaEngineer(cfg), AthenaSentiment(cfg), cfg)
    return backtest.run(data, initial_balance=10_000.0, symbol="BTC/USDT") or {"total_trades": 0}


def train_candidate(
    candidate_name: str,
    train_months: Iterable[str],
    timeframe: str,
    direction_filter: str = "both",
    model_dir: Path | None = None,
) -> Path:
    cfg = make_cfg(
        candidate_name,
        profile="conservative",
        timeframe=timeframe,
        for_training=True,
        direction_filter=direction_filter,
    )
    model_suffix = "" if direction_filter == "both" else f"_{direction_filter}"
    model_root = Path(model_dir) if model_dir is not None else MODEL_DIR
    model_root.mkdir(parents=True, exist_ok=True)
    out_path = model_root / f"athena_brain_{timeframe}_{candidate_name}{model_suffix}.pkl"
    trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
    trainer.train(load_months(train_months, timeframe=timeframe), save_path=str(out_path))
    return out_path


def main() -> None:
    args = parse_args()
    walk_forward = (
        ATHENA_CONFIG.get("experiment", {}).get("walk_forward")
        or ATHENA_CONFIG.get("training", {}).get("walk_forward", {})
    )
    timeframe = str(args.timeframe).strip()
    adaptive_mode = bool(args.adaptive_mode)
    router_enabled = bool(args.router_enabled)
    macro_filter_tf = args.macro_filter_tf
    macro_filter_threshold = args.macro_filter_threshold
    macro_filter_allow_neutral = True if args.macro_filter_allow_neutral else None
    direction_filter = str(args.direction).strip().lower()
    regime_filter = str(args.regime).strip().lower()
    direction_filter = str(args.direction).strip().lower()
    regime_filter = str(args.regime).strip().lower()
    meta_allowed_hours = parse_csv_ints(args.meta_hours)
    meta_allowed_regimes = parse_csv_strings(args.meta_regimes)
    meta_min_confidence = args.meta_min_confidence
    meta_max_confidence = args.meta_max_confidence
    model_dir = Path(args.model_dir) if args.model_dir else MODEL_DIR
    train_months = parse_months(args.train_months, walk_forward.get("train_months", ["2025-04", "2025-05"]))
    validation_months = parse_months(args.validation_months, walk_forward.get("validation_months", ["2025-06"]))
    test_months = parse_months(args.test_months, walk_forward.get("test_months", ["2025-07", "2025-08", "2025-09"]))
    candidate_names = resolve_candidate_names(args.candidate)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "timeframe": timeframe,
        "adaptive_mode": adaptive_mode,
        "router_enabled": router_enabled,
        "macro_filter_tf": macro_filter_tf,
        "macro_filter_threshold": macro_filter_threshold,
        "macro_filter_allow_neutral": macro_filter_allow_neutral,
        "direction_filter": direction_filter,
        "regime_filter": regime_filter,
        "meta_allowed_hours": meta_allowed_hours,
        "meta_allowed_regimes": meta_allowed_regimes,
        "meta_min_confidence": meta_min_confidence,
        "meta_max_confidence": meta_max_confidence,
        "train_months": train_months,
        "validation_months": validation_months,
        "test_months": test_months,
        "candidates": {},
    }

    best_name = None
    best_score = -1e18
    best_model_path: Path | None = None

    for candidate_name in candidate_names:
        print(f"\n=== timeframe: {timeframe} | candidate: {candidate_name} ===")
        model_path = train_candidate(
            candidate_name,
            train_months,
            timeframe=timeframe,
            direction_filter=direction_filter,
            model_dir=model_dir,
        )
        validation = {
            "conservative": run_profile(
                model_path,
                candidate_name,
                validation_months,
                "conservative",
                timeframe=timeframe,
                adaptive_mode=adaptive_mode,
                macro_filter_tf=macro_filter_tf,
                macro_filter_threshold=macro_filter_threshold,
                macro_filter_allow_neutral=macro_filter_allow_neutral,
                direction_filter=direction_filter,
                regime_filter=regime_filter,
                meta_allowed_hours=meta_allowed_hours,
                meta_allowed_regimes=meta_allowed_regimes,
                meta_min_confidence=meta_min_confidence,
                meta_max_confidence=meta_max_confidence,
                router_enabled=router_enabled,
            ),
            "aggressive": run_profile(
                model_path,
                candidate_name,
                validation_months,
                "aggressive",
                timeframe=timeframe,
                adaptive_mode=adaptive_mode,
                macro_filter_tf=macro_filter_tf,
                macro_filter_threshold=macro_filter_threshold,
                macro_filter_allow_neutral=macro_filter_allow_neutral,
                direction_filter=direction_filter,
                regime_filter=regime_filter,
                meta_allowed_hours=meta_allowed_hours,
                meta_allowed_regimes=meta_allowed_regimes,
                meta_min_confidence=meta_min_confidence,
                meta_max_confidence=meta_max_confidence,
                router_enabled=router_enabled,
            ),
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
        "conservative": run_profile(
            best_model_path,
            best_name,
            test_months,
            "conservative",
            timeframe=timeframe,
            adaptive_mode=adaptive_mode,
            macro_filter_tf=macro_filter_tf,
            macro_filter_threshold=macro_filter_threshold,
            macro_filter_allow_neutral=macro_filter_allow_neutral,
            direction_filter=direction_filter,
            regime_filter=regime_filter,
            meta_allowed_hours=meta_allowed_hours,
            meta_allowed_regimes=meta_allowed_regimes,
            meta_min_confidence=meta_min_confidence,
            meta_max_confidence=meta_max_confidence,
            router_enabled=router_enabled,
        ),
        "aggressive": run_profile(
            best_model_path,
            best_name,
            test_months,
            "aggressive",
            timeframe=timeframe,
            adaptive_mode=adaptive_mode,
            macro_filter_tf=macro_filter_tf,
            macro_filter_threshold=macro_filter_threshold,
            macro_filter_allow_neutral=macro_filter_allow_neutral,
            direction_filter=direction_filter,
            regime_filter=regime_filter,
            meta_allowed_hours=meta_allowed_hours,
            meta_allowed_regimes=meta_allowed_regimes,
            meta_min_confidence=meta_min_confidence,
            meta_max_confidence=meta_max_confidence,
            router_enabled=router_enabled,
        ),
    }

    summary["best_candidate"] = best_name
    summary["best_model_path"] = str(best_model_path)
    summary["holdout"] = holdout

    out_json = Path(args.output_json) if args.output_json else RESULTS_DIR / f"walkforward_{timeframe}_deepseek_like.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved walk-forward summary to {out_json}")
    print(json.dumps({"best_candidate": best_name, "holdout": holdout}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
