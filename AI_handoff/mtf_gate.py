"""
athena/filters/mtf_gate.py — MTF trend gate

1m execution + higher timeframe (default 15m) trend filter.
"""

from typing import Dict, List, Tuple
import logging

logger = logging.getLogger("athena.mtf")


class MTFGate:
    def __init__(self, config: Dict):
        flags = config.get("flags", {})
        self.enabled = bool(flags.get("MTF_FILTER_ENABLED", True))
        self.higher_tf = str(config.get("mtf_timeframe", "15m"))
        self.min_trend = float(config.get("mtf_min_trend", 0.0015))
        self.min_higher_candles = int(config.get("mtf_min_higher_candles", 12))

        self._ratio = self._tf_ratio(self.higher_tf)

    def _tf_ratio(self, tf: str) -> int:
        # Supports Xm format, falls back to 15.
        if tf.endswith("m"):
            try:
                value = int(tf[:-1])
                return max(1, value)
            except ValueError:
                pass
        return 15

    def _aggregate_to_higher_tf(self, ohlcv: List[List[float]]) -> List[List[float]]:
        ratio = self._ratio
        if ratio <= 1:
            return ohlcv

        full_len = (len(ohlcv) // ratio) * ratio
        if full_len <= 0:
            return []

        candles = []
        for i in range(0, full_len, ratio):
            chunk = ohlcv[i : i + ratio]
            ts = chunk[0][0]
            open_ = chunk[0][1]
            high = max(c[2] for c in chunk)
            low = min(c[3] for c in chunk)
            close = chunk[-1][4]
            volume = sum(c[5] for c in chunk)
            candles.append([ts, open_, high, low, close, volume])
        return candles

    def _ema(self, values: List[float], span: int) -> List[float]:
        if not values:
            return []
        alpha = 2 / (span + 1)
        out = [values[0]]
        for v in values[1:]:
            out.append(alpha * v + (1 - alpha) * out[-1])
        return out

    def allow_signal(self, ohlcv_1m: List[List[float]], direction: int) -> Tuple[bool, str]:
        if not self.enabled:
            return True, "mtf-disabled"

        if direction == 0:
            return False, "hold"

        higher = self._aggregate_to_higher_tf(ohlcv_1m)
        if len(higher) < self.min_higher_candles:
            return False, "mtf-insufficient-data"

        closes = [c[4] for c in higher]
        ema_fast = self._ema(closes, span=5)
        ema_slow = self._ema(closes, span=12)

        if not ema_fast or not ema_slow:
            return False, "mtf-empty-ema"

        fast = ema_fast[-1]
        slow = ema_slow[-1]
        trend_strength = abs(fast - slow) / (slow + 1e-9)

        if trend_strength < self.min_trend:
            return False, f"mtf-flat:{trend_strength:.5f}"

        trend_direction = 1 if fast > slow else -1
        if direction != trend_direction:
            return False, f"mtf-against-trend:{trend_direction}"

        return True, f"mtf-pass:{trend_strength:.5f}"
