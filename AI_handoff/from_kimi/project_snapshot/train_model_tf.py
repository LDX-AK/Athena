#!/usr/bin/env python3
"""Timeframe-aware LightGBM training entrypoint for Athena."""

from __future__ import annotations

import argparse
import asyncio
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def default_model_path(timeframe: str) -> Path:
    tf = str(timeframe).strip().lower()
    if tf == "1m":
        return ROOT / "athena" / "model" / "athena_brain.pkl"
    return ROOT / "athena" / "model" / f"athena_brain_{tf}.pkl"


def default_csv_path(timeframe: str) -> Path:
    tf = str(timeframe).strip().lower()
    return ROOT / "data" / "raw" / "ohlcv" / f"BTCUSDT_{tf}_latest.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an Athena model for a specific timeframe")
    parser.add_argument("--timeframe", default="15m", help="Training timeframe, e.g. 1m, 5m, 15m")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair to train on")
    parser.add_argument("--exchange", default="binance", help="Exchange name for live historical fetch fallback")
    parser.add_argument("--csv-path", default=None, help="Optional OHLCV CSV path. If omitted, tries default CSV then live fetch.")
    parser.add_argument("--model-path", default=None, help="Optional output model path")
    parser.add_argument("--max-rows", type=int, default=8000, help="Maximum candles to use")
    parser.add_argument("--csv-window", choices=["first", "last"], default="last", help="Slice window when reading CSV")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> dict:
    from athena.config import ATHENA_CONFIG

    cfg = copy.deepcopy(ATHENA_CONFIG)
    cfg["symbols"] = [args.symbol]
    cfg["timeframe"] = args.timeframe
    cfg["runtime_timeframe"] = args.timeframe
    cfg["training_timeframe"] = args.timeframe
    cfg["model_path"] = str(Path(args.model_path or default_model_path(args.timeframe)).resolve()).replace("\\", "/")
    cfg.setdefault("flags", {})["MTF_FILTER_ENABLED"] = False
    return cfg


async def load_training_data(args: argparse.Namespace):
    csv_candidate = Path(args.csv_path).expanduser() if args.csv_path else default_csv_path(args.timeframe)
    if csv_candidate.exists():
        from athena.backtest.runner import load_ohlcv_from_csv

        return load_ohlcv_from_csv(
            str(csv_candidate),
            symbol=None,
            max_rows=args.max_rows if args.max_rows > 0 else None,
            window=args.csv_window,
        )

    from athena.data.fetcher import AthenaFetcher

    cfg = {"symbols": [args.symbol], "timeframe": args.timeframe}
    fetcher = AthenaFetcher({args.exchange: {}}, cfg)
    return await fetcher.fetch_historical(args.exchange, args.symbol, args.timeframe, limit=args.max_rows)


async def run_training(args: argparse.Namespace) -> Path:
    from athena.features.engineer import AthenaEngineer
    from athena.model.signal import AthenaTrainer

    cfg = build_config(args)
    historical_data = await load_training_data(args)
    output_path = Path(cfg["model_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    trainer = AthenaTrainer(AthenaEngineer(cfg), cfg)
    trainer.train(historical_data, save_path=str(output_path))
    return output_path


def main() -> None:
    args = parse_args()
    output_path = asyncio.run(run_training(args))
    print(f"Saved model: {output_path}")


if __name__ == "__main__":
    main()
