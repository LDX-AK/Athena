import argparse
import asyncio
from athena.core import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Athena AI-Bot")
    parser.add_argument(
        "--mode",
        choices=["paper", "live", "backtest", "train", "train_rl"],
        default="paper",
        help="Run mode",
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
