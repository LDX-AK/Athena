"""Adaptive trading mode controller for safer regime-aware risk profiles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("athena.adaptive")


class TradingMode(str, Enum):
    DEFENSIVE = "defensive"
    CONSERVATIVE = "conservative"
    AGGRESSIVE = "aggressive"


@dataclass
class ModeDecision:
    mode: TradingMode
    reason: str
    confidence: float


class AdaptiveModeController:
    """Thin adaptive layer that only selects a risk profile; it does not replace risk management."""

    def __init__(self, config: Dict):
        self.config = config
        self.adaptive_cfg = config.get("adaptive_mode", {})
        self.enabled = bool(self.adaptive_cfg.get("enabled", False))
        self.runtime_timeframe = str(config.get("runtime_timeframe") or config.get("timeframe", "15m"))

        default_mode = str(self.adaptive_cfg.get("default_mode", TradingMode.CONSERVATIVE.value))
        self.current_mode = TradingMode(default_mode)
        self.last_reason = "initial"
        self.last_confidence = 0.5
        self.switch_count = 0

        self.update_interval_bars = int(self.adaptive_cfg.get("update_interval_bars", 24))
        self.hysteresis_bars = int(self.adaptive_cfg.get("hysteresis_bars", 12))
        self.market_cfg = self.adaptive_cfg.get("market_regime") or self.adaptive_cfg.get("mtf_matrix", {})
        self.health_cfg = self.adaptive_cfg.get("self_health", {})
        self.mode_params = self.adaptive_cfg.get("modes", {})

        self.last_update_bar = -self.update_interval_bars
        self.mode_start_bar = -self.hysteresis_bars
        self._risk_manager = None

    def set_risk_manager(self, risk_manager) -> None:
        self._risk_manager = risk_manager

    def update(self, bar_index: int, context: Dict) -> Optional[TradingMode]:
        if not self.enabled:
            return None

        if bar_index - self.last_update_bar < self.update_interval_bars:
            return None

        market = self._market_regime_decision(context)
        health = self._self_health_decision(context)
        final_mode = self._merge_decisions(market, health)
        self.last_update_bar = bar_index

        if final_mode == self.current_mode:
            self.last_reason = f"market: {market.reason} | health: {health.reason}"
            self.last_confidence = min(market.confidence, health.confidence)
            return None

        bars_in_mode = bar_index - self.mode_start_bar
        if bars_in_mode < self.hysteresis_bars:
            logger.debug(
                "Adaptive mode change blocked by hysteresis: %s -> %s (%s/%s bars)",
                self.current_mode.value,
                final_mode.value,
                bars_in_mode,
                self.hysteresis_bars,
            )
            return None

        self._apply_mode(final_mode, bar_index, market, health)
        return final_mode

    def _market_regime_decision(self, context: Dict) -> ModeDecision:
        if not self.market_cfg.get("enabled", True):
            return ModeDecision(self.current_mode, "market-regime-disabled", 0.5)

        base_ohlcv = context.get("ohlcv") or []
        if len(base_ohlcv) < 8:
            return ModeDecision(TradingMode.CONSERVATIVE, "insufficient-ohlcv", 0.3)

        timeframes = list(self.market_cfg.get("timeframes") or [self.config.get("mtf_timeframe", "1h")])
        weights = dict(self.market_cfg.get("weights", {}))

        total_weight = 0.0
        trend_score = 0.0
        volatility_score = 0.0

        for tf in timeframes:
            candles = self._aggregate_to_timeframe(base_ohlcv, str(tf))
            if len(candles) < 8:
                continue

            closes = [float(c[4]) for c in candles[-12:]]
            ema_fast = self._ema(closes, span=5)
            ema_slow = self._ema(closes, span=12)
            if not ema_fast or not ema_slow:
                continue

            slow = float(ema_slow[-1])
            if abs(slow) < 1e-9:
                continue

            weight = float(weights.get(tf, 1.0))
            trend = (float(ema_fast[-1]) - slow) / slow
            atr = self._calc_atr(candles[-15:], period=14)
            volatility = atr / max(abs(closes[-1]), 1e-9)

            trend_score += trend * weight
            volatility_score += volatility * weight
            total_weight += weight

        if total_weight <= 0:
            return ModeDecision(TradingMode.CONSERVATIVE, "insufficient-mtf-data", 0.3)

        trend_score /= total_weight
        volatility_score /= total_weight

        trend_threshold = float(self.market_cfg.get("trend_threshold", self.config.get("mtf_min_trend", 0.0015)))
        volatility_threshold = float(self.market_cfg.get("volatility_threshold", 0.01))
        strong_trend_multiplier = float(self.market_cfg.get("strong_trend_multiplier", 2.0))
        high_vol_multiplier = float(self.market_cfg.get("high_vol_multiplier", 2.0))

        if volatility_score >= volatility_threshold * high_vol_multiplier:
            confidence = min(0.95, volatility_score / max(volatility_threshold * high_vol_multiplier, 1e-9))
            return ModeDecision(TradingMode.DEFENSIVE, f"high-vol:{volatility_score:.4f}", confidence)

        if abs(trend_score) >= trend_threshold * strong_trend_multiplier:
            confidence = min(0.90, abs(trend_score) / max(trend_threshold * strong_trend_multiplier, 1e-9))
            direction = "bull" if trend_score > 0 else "bear"
            return ModeDecision(TradingMode.AGGRESSIVE, f"strong-{direction}:{trend_score:.4f}", confidence)

        if abs(trend_score) >= trend_threshold:
            return ModeDecision(TradingMode.CONSERVATIVE, f"moderate-trend:{trend_score:.4f}", 0.70)

        return ModeDecision(TradingMode.DEFENSIVE, f"flat:{trend_score:.4f}", 0.60)

    def _self_health_decision(self, context: Dict) -> ModeDecision:
        if not self.health_cfg.get("enabled", True):
            return ModeDecision(self.current_mode, "self-health-disabled", 0.5)

        trades = list(context.get("recent_trades") or [])
        window = int(self.health_cfg.get("window_trades", 20))
        if len(trades) < window:
            return ModeDecision(self.current_mode, f"insufficient-trades:{len(trades)}/{window}", 0.5)

        recent = trades[-window:]
        pnls = np.array([float(t.get("pnl", 0.0)) for t in recent], dtype=float)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        win_rate = float(np.mean(pnls > 0)) if len(pnls) else 0.0
        std = float(pnls.std()) if len(pnls) > 1 else 0.0
        sharpe = 0.0 if std < 1e-9 else float(pnls.mean() / std)
        profit_factor = float(wins.sum() / abs(losses.sum())) if len(losses) else float("inf")

        if win_rate < float(self.health_cfg.get("min_win_rate", 0.35)):
            return ModeDecision(TradingMode.DEFENSIVE, f"low-winrate:{win_rate:.2f}", 0.8)
        if sharpe < float(self.health_cfg.get("min_sharpe", -0.5)):
            return ModeDecision(TradingMode.DEFENSIVE, f"low-sharpe:{sharpe:.2f}", 0.75)
        if profit_factor < float(self.health_cfg.get("min_profit_factor", 0.8)):
            return ModeDecision(TradingMode.DEFENSIVE, f"low-pf:{profit_factor:.2f}", 0.7)

        return ModeDecision(self.current_mode, "healthy", 0.70)

    def _merge_decisions(self, market: ModeDecision, health: ModeDecision) -> TradingMode:
        if health.mode == TradingMode.DEFENSIVE and health.reason.startswith(("low-winrate", "low-sharpe", "low-pf")):
            return TradingMode.DEFENSIVE
        return market.mode

    @staticmethod
    def _mode_rank(mode: TradingMode) -> int:
        order = {
            TradingMode.DEFENSIVE: 0,
            TradingMode.CONSERVATIVE: 1,
            TradingMode.AGGRESSIVE: 2,
        }
        return order[mode]

    def _apply_mode(
        self,
        new_mode: TradingMode,
        bar_index: int,
        market: ModeDecision,
        health: ModeDecision,
    ) -> None:
        self.current_mode = new_mode
        self.mode_start_bar = bar_index
        self.last_reason = f"market: {market.reason} | health: {health.reason}"
        self.last_confidence = min(market.confidence, health.confidence)
        self.switch_count += 1

        mode_params = dict(self.mode_params.get(new_mode.value, {}))
        if self._risk_manager is not None:
            if hasattr(self._risk_manager, "apply_profile"):
                self._risk_manager.apply_profile(mode_params)
            else:
                for key, value in mode_params.items():
                    if hasattr(self._risk_manager, key):
                        setattr(self._risk_manager, key, value)
                    cfg = getattr(self._risk_manager, "cfg", None)
                    if isinstance(cfg, dict):
                        cfg[key] = value

        logger.info(
            "Adaptive mode switched to %s | %s | params=%s",
            new_mode.value,
            self.last_reason,
            mode_params,
        )

    def summary(self) -> Dict:
        return {
            "enabled": self.enabled,
            "current_mode": self.current_mode.value,
            "switch_count": self.switch_count,
            "last_reason": self.last_reason,
            "last_confidence": self.last_confidence,
        }

    def _aggregate_to_timeframe(self, ohlcv: List[List[float]], target_tf: str) -> List[List[float]]:
        ratio = self._tf_ratio(self.runtime_timeframe, target_tf)
        if ratio <= 1:
            return [list(row) for row in ohlcv]

        full_len = (len(ohlcv) // ratio) * ratio
        if full_len <= 0:
            return []

        out = []
        for i in range(0, full_len, ratio):
            chunk = ohlcv[i : i + ratio]
            out.append([
                chunk[0][0],
                chunk[0][1],
                max(float(c[2]) for c in chunk),
                min(float(c[3]) for c in chunk),
                float(chunk[-1][4]),
                sum(float(c[5]) for c in chunk),
            ])
        return out

    @staticmethod
    def _tf_ratio(base_tf: str, higher_tf: str) -> int:
        base_minutes = AdaptiveModeController._tf_to_minutes(base_tf)
        higher_minutes = AdaptiveModeController._tf_to_minutes(higher_tf)
        if higher_minutes <= base_minutes:
            return 1
        return max(1, int(round(higher_minutes / max(base_minutes, 1))))

    @staticmethod
    def _tf_to_minutes(tf: str) -> int:
        tf = str(tf).strip().lower()
        if tf.endswith("m"):
            return max(1, int(tf[:-1]))
        if tf.endswith("h"):
            return max(1, int(tf[:-1]) * 60)
        if tf.endswith("d"):
            return max(1, int(tf[:-1]) * 1440)
        raise ValueError(f"Unsupported timeframe: {tf}")

    @staticmethod
    def _ema(values: List[float], span: int) -> List[float]:
        if not values:
            return []
        alpha = 2.0 / (span + 1)
        out = [float(values[0])]
        for value in values[1:]:
            out.append(alpha * float(value) + (1.0 - alpha) * out[-1])
        return out

    @staticmethod
    def _calc_atr(ohlcv: List[List[float]], period: int = 14) -> float:
        if len(ohlcv) < 2:
            return 0.0
        tr_values = []
        prev_close = float(ohlcv[0][4])
        for candle in ohlcv[1:]:
            high = float(candle[2])
            low = float(candle[3])
            tr_values.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
            prev_close = float(candle[4])
        if not tr_values:
            return 0.0
        return float(np.mean(tr_values[-period:]))
