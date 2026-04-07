#!/usr/bin/env python3
"""Download BTC/USDT OHLCV to monthly CSV files for walk-forward training and testing."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch monthly OHLCV CSV files from Binance")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair to fetch")
    parser.add_argument("--timeframe", default="15m", help="OHLCV timeframe")
    parser.add_argument("--start", default="2025-04", help="Start month inclusive (YYYY-MM)")
    parser.add_argument("--end", default="2025-09", help="End month inclusive (YYYY-MM)")
    parser.add_argument(
        "--output-dir",
        default="data/raw/ohlcv",
        help="Directory where monthly CSV files will be written",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing monthly CSVs")
    return parser.parse_args()


def iter_months(start_month: str, end_month: str):
    start = datetime.strptime(start_month, "%Y-%m")
    end = datetime.strptime(end_month, "%Y-%m")
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def timeframe_to_ms(timeframe: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    tf = timeframe.strip().lower()
    value = int(tf[:-1])
    unit = tf[-1]
    return value * units[unit]


def month_bounds_ms(year: int, month: int) -> tuple[int, int]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def fetch_month(exchange, symbol: str, timeframe: str, start_ms: int, end_ms: int):
    rows = []
    since = start_ms
    step_ms = timeframe_to_ms(timeframe)

    while since < end_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break

        added = 0
        for row in batch:
            ts = int(row[0])
            if ts >= end_ms:
                break
            if rows and ts <= rows[-1][0]:
                continue
            rows.append(row[:6])
            added += 1

        if added == 0:
            break

        since = int(rows[-1][0]) + step_ms
        time.sleep(max(getattr(exchange, "rateLimit", 200), 200) / 1000.0)

    return rows


def main() -> None:
    args = parse_args()
    import ccxt

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exchange = ccxt.binance({"enableRateLimit": True})
    symbol_slug = args.symbol.replace("/", "")

    for year, month in iter_months(args.start, args.end):
        out_path = output_dir / f"{symbol_slug}_{args.timeframe}_{year}_{month:02d}.csv"
        if out_path.exists() and not args.overwrite:
            print(f"skip {out_path} (already exists)")
            continue

        start_ms, end_ms = month_bounds_ms(year, month)
        rows = fetch_month(exchange, args.symbol, args.timeframe, start_ms, end_ms)
        if not rows:
            raise RuntimeError(f"No OHLCV rows fetched for {year}-{month:02d}")

        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df.to_csv(out_path, index=False)
        print(f"saved {out_path} rows={len(df)}")


if __name__ == "__main__":
    main()
