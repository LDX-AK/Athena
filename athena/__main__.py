import argparse
import asyncio

from athena.config import ATHENA_CONFIG
from athena.core import run


def _default_model_path(timeframe: str) -> str:
    tf = str(timeframe).strip().lower()
    if tf == "1m":
        return ATHENA_CONFIG.get("model_path", "athena/model/athena_brain.pkl")
    return f"athena/model/athena_brain_{tf}.pkl"


def _apply_runtime_overrides(args: argparse.Namespace) -> None:
    if args.timeframe:
        ATHENA_CONFIG["timeframe"] = args.timeframe
        ATHENA_CONFIG["runtime_timeframe"] = args.timeframe
        ATHENA_CONFIG["training_timeframe"] = args.timeframe
        ATHENA_CONFIG["model_path"] = args.model_path or _default_model_path(args.timeframe)

    if args.symbol:
        ATHENA_CONFIG["symbols"] = [args.symbol]

    if args.model_path and not args.timeframe:
        ATHENA_CONFIG["model_path"] = args.model_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Athena AI-Bot")
    parser.add_argument(
        "--mode",
        choices=["paper", "live", "backtest", "train", "train_rl"],
        default="paper",
        help="Run mode",
    )
    parser.add_argument(
        "--timeframe",
        default=None,
        help="Override runtime/training timeframe (for example: 15m)",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Optional single symbol override, e.g. BTC/USDT",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Optional model path override",
    )
    parser.add_argument(
        "--backtest-csv",
        default=None,
        help="Path to external OHLCV CSV for offline backtest",
    )
    parser.add_argument(
        "--backtest-symbol",
        default="BTC/USDT",
        help="Symbol to use/filter in backtest mode",
    )
    parser.add_argument(
        "--backtest-exchange",
        default="binance",
        help="Exchange name for REST backtest mode when no CSV is provided",
    )
    parser.add_argument(
        "--backtest-limit",
        type=int,
        default=20_000,
        help="Maximum number of candles to use in backtest mode (safe default for large CSV)",
    )
    parser.add_argument(
        "--backtest-csv-window",
        choices=["first", "last"],
        default="first",
        help="When using --backtest-csv, choose first or last N candles",
    )
    args = parser.parse_args()
    _apply_runtime_overrides(args)
    asyncio.run(
        run(
            args.mode,
            backtest_csv_path=args.backtest_csv,
            backtest_symbol=args.backtest_symbol,
            backtest_exchange=args.backtest_exchange,
            backtest_limit=args.backtest_limit,
            backtest_csv_window=args.backtest_csv_window,
        )
    )


if __name__ == "__main__":
    main()
