"""Rule-based first prototypes for Athena v3 route-aware trading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class PrototypeDecision:
    direction: int
    confidence: float
    reason: str
    name: str


class QuietMeanReversionPrototype:
    """Cheap first prototype for quiet-regime mean reversion."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        cfg = dict((self.config.get("prototypes", {}) or {}).get("quiet_mean_reversion", {}))
        self.enabled = bool(cfg.get("enabled", True))
        self.vwap_threshold = float(cfg.get("vwap_threshold", 0.0015))
        self.rsi_threshold = float(cfg.get("rsi_threshold", 0.12))
        self.bb_low = float(cfg.get("bb_low", 0.35))
        self.bb_high = float(cfg.get("bb_high", 0.65))
        self.min_confidence = float(cfg.get("min_confidence", 0.55))

    def decide(self, features: Dict[str, Any]) -> PrototypeDecision:
        if not self.enabled:
            return PrototypeDecision(0, 0.0, "quiet_mean_reversion_v1 disabled", "quiet_mean_reversion_v1")

        rsi = float(features.get("rsi", 0.0))
        bb_pos = float(features.get("bb_pos", 0.5))
        vwap_dist = float(features.get("vwap_dist", 0.0))
        ema_9_dist = float(features.get("ema_9_dist", 0.0))
        ema_50_dist = float(features.get("ema_50_dist", 0.0))

        if vwap_dist <= -self.vwap_threshold and rsi <= -self.rsi_threshold and bb_pos <= self.bb_low:
            confidence = self._confidence(
                abs(vwap_dist) / max(self.vwap_threshold, 1e-9),
                abs(rsi) / max(self.rsi_threshold, 1e-9),
                (self.bb_low - bb_pos) / max(self.bb_low, 1e-9),
                abs(min(ema_9_dist, 0.0)) + abs(min(ema_50_dist, 0.0)),
            )
            return PrototypeDecision(
                1,
                confidence,
                f"quiet_mean_reversion_v1 long | rsi={rsi:.3f} bb_pos={bb_pos:.3f} vwap={vwap_dist:.4f}",
                "quiet_mean_reversion_v1",
            )

        if vwap_dist >= self.vwap_threshold and rsi >= self.rsi_threshold and bb_pos >= self.bb_high:
            confidence = self._confidence(
                abs(vwap_dist) / max(self.vwap_threshold, 1e-9),
                abs(rsi) / max(self.rsi_threshold, 1e-9),
                (bb_pos - self.bb_high) / max(1.0 - self.bb_high, 1e-9),
                abs(max(ema_9_dist, 0.0)) + abs(max(ema_50_dist, 0.0)),
            )
            return PrototypeDecision(
                -1,
                confidence,
                f"quiet_mean_reversion_v1 short | rsi={rsi:.3f} bb_pos={bb_pos:.3f} vwap={vwap_dist:.4f}",
                "quiet_mean_reversion_v1",
            )

        return PrototypeDecision(0, 0.0, "quiet_mean_reversion_v1 no-edge", "quiet_mean_reversion_v1")

    def _confidence(self, *components: float) -> float:
        score = sum(max(0.0, min(1.5, c)) for c in components) / max(len(components), 1)
        return float(min(0.95, max(self.min_confidence, self.min_confidence + 0.20 * score)))


class RoutePrototypeEngine:
    """Dispatches route-aware prototype logic by router decision."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.quiet_mean_reversion = QuietMeanReversionPrototype(self.config)

    def apply(self, route_name: str, features: Dict[str, Any]) -> Optional[PrototypeDecision]:
        if route_name == "mean_reversion":
            return self.quiet_mean_reversion.decide(features)
        return None
