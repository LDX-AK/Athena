"""Lightweight market data fetcher with graceful offline fallbacks."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any, AsyncIterator, Dict, List

logger = logging.getLogger("athena.fetcher")


_TIMEFRAME_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class AthenaFetcher:
    """Fetches OHLCV/orderbook data for paper, backtest, and training workflows."""

    def __init__(self, exchanges: Dict[str, Dict[str, Any]], config: Dict[str, Any] | None = None):
        self.exchanges = exchanges or {}
        self.config = config or {}
        self.symbols = list(self.config.get("symbols", ["BTC/USDT"]))
        self.timeframe = str(self.config.get("timeframe", "1m"))
        self.poll_interval_sec = float(self.config.get("data", {}).get("poll_interval_sec", 5.0))
        self._synthetic_tick = 0

    async def fetch_historical(
        self,
        exchange_name: str,
        symbol: str,
        timeframe: str,
        limit: int = 1000,
    ) -> List[List[float]]:
        """Fetch OHLCV from ccxt when available, otherwise return deterministic synthetic candles."""
        try:
            import ccxt.async_support as ccxt_async  # type: ignore
        except Exception:
            ccxt_async = None

        if ccxt_async is not None:
            exchange_cls = getattr(ccxt_async, exchange_name, None)
            if exchange_cls is not None:
                params = dict(self.exchanges.get(exchange_name, {}))
                params.setdefault("enableRateLimit", True)
                exchange = exchange_cls(params)
                try:
                    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                    if ohlcv:
                        return ohlcv
                except Exception as exc:
                    logger.warning(
                        "Live historical fetch failed for %s %s %s: %s. Falling back to synthetic data.",
                        exchange_name,
                        symbol,
                        timeframe,
                        exc,
                    )
                finally:
                    try:
                        await exchange.close()
                    except Exception:
                        pass

        return self._synthetic_ohlcv(limit=limit, timeframe=timeframe)

    async def stream(self) -> AsyncIterator[Dict[str, Any]]:
        """Yield market snapshots suitable for `athena.core.run()` in paper/live loops."""
        exchange_names = list(self.exchanges.keys()) or ["binance"]

        while True:
            for exchange_name in exchange_names:
                for symbol in self.symbols:
                    ohlcv = await self.fetch_historical(exchange_name, symbol, self.timeframe, limit=240)
                    last_close = float(ohlcv[-1][4]) if ohlcv else 100_000.0
                    spread = max(last_close * 0.0002, 0.01)
                    yield {
                        "symbol": symbol,
                        "exchange": exchange_name,
                        "ohlcv": ohlcv,
                        "orderbook": {
                            "bids": [[last_close - spread, 5.0], [last_close - spread * 2, 3.0]],
                            "asks": [[last_close + spread, 4.5], [last_close + spread * 2, 2.5]],
                            "timestamp": int(time.time() * 1000),
                        },
                    }
            await asyncio.sleep(self.poll_interval_sec)

    def _synthetic_ohlcv(self, limit: int = 240, timeframe: str = "1m") -> List[List[float]]:
        minutes = _TIMEFRAME_MINUTES.get(str(timeframe), 1)
        now_ms = int(time.time() * 1000)
        rows: List[List[float]] = []
        base_price = 100_000.0

        for idx in range(limit):
            angle = (self._synthetic_tick + idx) / 18.0
            drift = idx / max(limit, 1) * 0.01
            close = base_price * (1 + 0.005 * math.sin(angle) + drift)
            open_ = rows[-1][4] if rows else close * 0.9995
            high = max(open_, close) * 1.001
            low = min(open_, close) * 0.999
            volume = 100 + (idx % 20) * 2
            ts = now_ms - (limit - idx) * minutes * 60_000
            rows.append([ts, open_, high, low, close, volume])

        self._synthetic_tick += 1
        return rows
