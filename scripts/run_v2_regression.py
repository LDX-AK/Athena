#!/usr/bin/env python3
"""Launch strict Athena v2 regression runs with isolated artifacts."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from athena.track_paths import default_result_path, track_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Athena v2 regression experiments with isolated outputs")
    parser.add_argument("--candidate", default="core_compact", help="Candidate name from run_walkforward_15m.py")
    parser.add_argument("--timeframe", default="15m", help="Timeframe, e.g. 15m or 1h")
    parser.add_argument("--direction", default="both", choices=["both", "long", "short"])
    parser.add_argument("--regime", default="all", choices=["all", "quiet", "normal", "hot"])
    parser.add_argument("--train-months", help="Comma-separated train months")
    parser.add_argument("--validation-months", help="Comma-separated validation months")
    parser.add_argument("--test-months", help="Comma-separated holdout months")
    parser.add_argument("--suffix", default="regression", help="Label appended to the result filename")
    parser.add_argument("--output-json", help="Optional explicit output JSON path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_json = Path(args.output_json) if args.output_json else default_result_path(
        "v2", timeframe=args.timeframe, candidate=args.candidate, suffix=args.suffix
    )
    model_dir = track_dir("v2", "models")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(ROOT / "run_walkforward_15m.py"),
        "--candidate",
        args.candidate,
        "--timeframe",
        args.timeframe,
        "--direction",
        args.direction,
        "--regime",
        args.regime,
        "--output-json",
        str(output_json),
        "--model-dir",
        str(model_dir),
    ]
    if args.train_months:
        cmd += ["--train-months", args.train_months]
    if args.validation_months:
        cmd += ["--validation-months", args.validation_months]
    if args.test_months:
        cmd += ["--test-months", args.test_months]

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
