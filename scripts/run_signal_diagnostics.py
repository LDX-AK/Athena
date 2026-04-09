#!/usr/bin/env python3
"""Run a raw signal-edge diagnostic report for an Athena model."""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from athena.analysis.diagnostics import build_signal_records, summarize_signal_records
from athena.config import ATHENA_CONFIG
from athena.backtest.runner import load_ohlcv_from_csv
RAW_DIR = ROOT / "data" / "raw" / "ohlcv"
RESULTS_DIR = ROOT / "data" / "results"


def parse_months(value: str) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part.strip()]


def month_file(month: str, timeframe: str) -> Path:
    return RAW_DIR / f"BTCUSDT_{timeframe}_{month.replace('-', '_')}.csv"


def load_months(months: list[str], timeframe: str) -> list[list[float]]:
    rows: list[list[float]] = []
    for month in months:
        path = month_file(month, timeframe)
        rows.extend(load_ohlcv_from_csv(str(path), window="first"))
    return rows


def parse_horizons(value: str) -> list[int]:
    return [max(1, int(part.strip())) for part in str(value).split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run raw signal diagnostics for Athena models")
    parser.add_argument("--model-path", required=True, help="Path to trained model .pkl")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--months", default="2025-10,2025-11,2025-12")
    parser.add_argument("--horizons", default="3,6,10")
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--output-json")
    args = parser.parse_args()

    logging.getLogger("athena.fusion").setLevel(logging.WARNING)
    logging.getLogger("athena.model").setLevel(logging.WARNING)

    cfg = copy.deepcopy(ATHENA_CONFIG)
    cfg["timeframe"] = args.timeframe
    cfg["runtime_timeframe"] = args.timeframe
    cfg["training_timeframe"] = args.timeframe
    cfg["model_path"] = str(Path(args.model_path).resolve())
    cfg.setdefault("flags", {})["SENTIMENT_ENABLED"] = False
    cfg["flags"]["SENTIMENT_BACKTEST"] = False
    cfg["flags"]["MTF_FILTER_ENABLED"] = False

    months = parse_months(args.months)
    horizons = parse_horizons(args.horizons)
    primary_horizon = max(horizons)

    ohlcv = load_months(months, args.timeframe)
    records = build_signal_records(ohlcv, cfg, symbol="BTC/USDT", horizons=horizons)
    report = summarize_signal_records(records, primary_horizon=primary_horizon, min_confidence=args.min_confidence)

    payload = {
        "model_path": cfg["model_path"],
        "timeframe": args.timeframe,
        "months": months,
        "horizons": horizons,
        **report,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output_json) if args.output_json else RESULTS_DIR / f"signal_diagnostics_{Path(args.model_path).stem}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = payload["summary"]
    above = summary.get("above_threshold", {})
    print(f"Saved diagnostics to {output_path}")
    print(
        f"Signals={summary.get('total_signals', 0)} | "
        f"edge={summary.get('edge_per_signal', 0.0):+.6f} | "
        f"win_rate={summary.get('win_rate', 0.0):.2%}"
    )
    if above:
        print(
            f"Above conf>={above.get('threshold', 0.0):.2f}: "
            f"count={above.get('count', 0)} | edge={above.get('edge_per_signal', 0.0):+.6f} | "
            f"win_rate={above.get('win_rate', 0.0):.2%}"
        )


if __name__ == "__main__":
    main()
