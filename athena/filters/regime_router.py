"""Rule-based regime/session router for Athena v3 prototypes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple


class RegimeRouter:
    """Two-level router: regime decides allowed routes, session adjusts preference and confidence."""

    _MATRIX: Dict[Tuple[str, str], Tuple[str, float, str]] = {
        ("quiet", "asia"): ("no_trade", 0.80, "quiet-asia penalty"),
        ("quiet", "europe"): ("mean_reversion", 0.95, "quiet-europe mean reversion"),
        ("quiet", "us"): ("mean_reversion", 0.92, "quiet-us mean reversion"),
        ("quiet", "eu_us_overlap"): ("no_trade", 0.85, "quiet-overlap stand aside"),
        ("quiet", "weekend"): ("no_trade", 0.75, "quiet-weekend stand aside"),
        ("normal", "asia"): ("directional", 0.92, "normal-asia lighter confidence"),
        ("normal", "europe"): ("directional", 1.00, "normal-europe preferred directional"),
        ("normal", "us"): ("directional", 1.00, "normal-us preferred directional"),
        ("normal", "eu_us_overlap"): ("directional", 1.05, "normal-overlap boost"),
        ("normal", "weekend"): ("no_trade", 0.80, "normal-weekend stand aside"),
        ("hot", "asia"): ("no_trade", 0.82, "hot-asia avoid breakout noise"),
        ("hot", "europe"): ("breakout", 1.00, "hot-europe breakout"),
        ("hot", "us"): ("breakout", 1.08, "hot-us breakout boost"),
        ("hot", "eu_us_overlap"): ("breakout", 1.10, "hot-overlap breakout boost"),
        ("hot", "weekend"): ("no_trade", 0.70, "hot-weekend stand aside"),
    }

    _ALLOWED_ROUTES = {
        "quiet": ["no_trade", "mean_reversion"],
        "normal": ["directional"],
        "hot": ["breakout", "no_trade"],
    }

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}
        self.router_cfg = self.config.get("router", {}) or {}
        self.enabled = bool(self.router_cfg.get("enabled", False))

    def detect_regime(self, features: Dict[str, Any]) -> str:
        percentile = float(features.get("vol_regime", 0.5))
        if percentile < 0.25:
            return "quiet"
        if percentile > 0.75:
            return "hot"
        return "normal"

    def detect_session(self, features: Dict[str, Any], timestamp_ms: int | None = None) -> str:
        if float(features.get("is_weekend", features.get("weekend", 0.0))) >= 1.0:
            return "weekend"
        if float(features.get("session_overlap", features.get("overlap_session", 0.0))) >= 1.0:
            return "eu_us_overlap"
        if float(features.get("session_us", features.get("ny_open", 0.0))) >= 1.0:
            return "us"
        if float(features.get("session_europe", features.get("london_open", 0.0))) >= 1.0:
            return "europe"
        if float(features.get("session_asia", features.get("asia_open", 0.0))) >= 1.0:
            return "asia"

        if timestamp_ms is None:
            return "unknown"

        dt = datetime.fromtimestamp(float(timestamp_ms) / 1000.0, tz=timezone.utc)
        hour = dt.hour
        if dt.weekday() >= 5:
            return "weekend"
        if 13 <= hour < 15:
            return "eu_us_overlap"
        if 13 <= hour < 22:
            return "us"
        if 7 <= hour < 15:
            return "europe"
        if 0 <= hour < 8:
            return "asia"
        return "unknown"

    def decide(
        self,
        features: Dict[str, Any],
        timestamp_ms: int | None = None,
        raw_confidence: float = 0.0,
    ) -> Dict[str, Any]:
        regime = self.detect_regime(features)
        session = self.detect_session(features, timestamp_ms=timestamp_ms)
        route, multiplier, note = self._MATRIX.get(
            (regime, session),
            self._fallback_for(regime),
        )

        raw_conf = float(raw_confidence)
        adjusted = max(0.0, min(1.0, raw_conf * multiplier))

        return {
            "route": route,
            "regime": regime,
            "session": session,
            "allowed_routes": list(self._ALLOWED_ROUTES.get(regime, [route])),
            "confidence_multiplier": float(multiplier),
            "raw_confidence": raw_conf,
            "adjusted_confidence": adjusted,
            "reason": f"{regime}:{session}->{route} ({note}, x{multiplier:.2f})",
        }

    def _fallback_for(self, regime: str) -> Tuple[str, float, str]:
        if regime == "quiet":
            return ("mean_reversion", 0.90, "quiet fallback")
        if regime == "hot":
            return ("breakout", 0.95, "hot fallback")
        return ("directional", 0.95, "normal fallback")
