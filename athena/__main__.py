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
    args = parser.parse_args()
    asyncio.run(run(args.mode))


if __name__ == "__main__":
    main()
