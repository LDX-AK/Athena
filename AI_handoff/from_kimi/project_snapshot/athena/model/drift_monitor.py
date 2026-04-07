"""
athena/model/drift_monitor.py — AthenaDriftMonitor

Следит за деградацией торговых метрик на скользящем окне закрытых сделок.
На этом этапе только детектит drift и логирует причины.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import logging
import math

logger = logging.getLogger("athena.drift")


@dataclass
class DriftStatus:
    drift_detected: bool
    alerts_in_row: int
    checks: Dict[str, float]
    alerts: List[str]
    reasons: List[str]


class AthenaDriftMonitor:
    def __init__(self, config: Dict):
        cfg = config.get("drift", {})
        self.enabled = cfg.get("enabled", True)
        self.window_trades = int(cfg.get("window_trades", 30))
        self.min_win_rate = float(cfg.get("min_win_rate", 0.45))
        self.min_profit_factor = float(cfg.get("min_profit_factor", 1.10))
        self.min_sharpe = float(cfg.get("min_sharpe", 0.70))
        self.consecutive_alerts = int(cfg.get("consecutive_alerts", 3))
        self.winrate_drop = float(cfg.get("winrate_drop", 0.10))
        self.confidence_drop = float(cfg.get("confidence_drop", 0.15))
        self.sharpe_drop = float(cfg.get("sharpe_drop", 0.30))
        self.volatility_multiplier = float(cfg.get("volatility_multiplier", 2.0))
        self.consecutive_losses_limit = int(cfg.get("consecutive_losses", 5))

        self._alerts_in_row = 0
        self._baseline_checks: Optional[Dict[str, float]] = None

    def evaluate(self, trade_history: List[Dict]) -> DriftStatus:
        if not self.enabled or len(trade_history) < self.window_trades:
            return DriftStatus(False, self._alerts_in_row, {}, [], [])

        recent = trade_history[-self.window_trades :]
        pnls = [float(t.get("pnl", 0.0)) for t in recent]
        confidences = [float(t["confidence"]) for t in recent if t.get("confidence") is not None]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / len(pnls) if pnls else 0.0
        total_win = sum(wins)
        total_loss = abs(sum(losses))
        profit_factor = (total_win / total_loss) if total_loss > 0 else float("inf")
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        mean = sum(pnls) / len(pnls)
        variance = sum((x - mean) ** 2 for x in pnls) / len(pnls)
        std = math.sqrt(max(variance, 0.0))
        sharpe = 0.0 if std < 1e-6 else mean / std

        recent_slice = pnls[-min(20, len(pnls)) :]
        recent_mean = sum(recent_slice) / len(recent_slice)
        recent_variance = sum((x - recent_mean) ** 2 for x in recent_slice) / len(recent_slice)
        recent_volatility = math.sqrt(max(recent_variance, 0.0))

        consecutive_losses = 0
        for pnl in reversed(pnls):
            if pnl < 0:
                consecutive_losses += 1
            else:
                break

        checks = {
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "sharpe": sharpe,
            "avg_confidence": avg_confidence,
            "recent_volatility": recent_volatility,
            "consecutive_losses": float(consecutive_losses),
        }

        if self._baseline_checks is None:
            self._baseline_checks = dict(checks)
            logger.info(
                "DRIFT baseline captured: %s",
                {k: round(v, 4) for k, v in self._baseline_checks.items()},
            )
            return DriftStatus(False, self._alerts_in_row, checks, [], ["baseline-captured"])

        baseline = self._baseline_checks

        alerts: List[str] = []
        reasons: List[str] = []
        if win_rate < self.min_win_rate:
            alerts.append("WINRATE_FLOOR")
            reasons.append(f"win_rate={win_rate:.3f}<{self.min_win_rate:.3f}")
        if profit_factor < self.min_profit_factor:
            alerts.append("PROFIT_FACTOR_FLOOR")
            reasons.append(f"profit_factor={profit_factor:.3f}<{self.min_profit_factor:.3f}")
        if sharpe < self.min_sharpe:
            alerts.append("SHARPE_FLOOR")
            reasons.append(f"sharpe={sharpe:.3f}<{self.min_sharpe:.3f}")

        if win_rate < baseline["win_rate"] - self.winrate_drop:
            alerts.append("WINRATE_DRIFT")
            reasons.append(
                f"win_rate_drop={baseline['win_rate'] - win_rate:.3f}>{self.winrate_drop:.3f}"
            )

        if sharpe < baseline["sharpe"] - self.sharpe_drop:
            alerts.append("SHARPE_DRIFT")
            reasons.append(
                f"sharpe_drop={baseline['sharpe'] - sharpe:.3f}>{self.sharpe_drop:.3f}"
            )

        confidence_coverage = len(confidences) / max(1, len(recent))
        baseline_confidence = max(baseline.get("avg_confidence", 0.0), 1e-9)
        if confidence_coverage < 0.8:
            reasons.append(f"insufficient-confidence-data:{confidence_coverage:.2f}")
        elif avg_confidence < baseline_confidence * (1 - self.confidence_drop):
            alerts.append("CONFIDENCE_DRIFT")
            reasons.append(
                f"confidence_drop={(baseline_confidence - avg_confidence):.3f}"
            )

        baseline_volatility = max(baseline.get("recent_volatility", 0.0), 1e-9)
        if recent_volatility > baseline_volatility * self.volatility_multiplier:
            alerts.append("REGIME_VOLATILITY")
            reasons.append(
                f"volatility={recent_volatility:.4f}>{baseline_volatility * self.volatility_multiplier:.4f}"
            )

        if consecutive_losses >= self.consecutive_losses_limit:
            alerts.append("LOSS_STREAK")
            reasons.append(
                f"consecutive_losses={consecutive_losses}>={self.consecutive_losses_limit}"
            )

        if alerts:
            self._alerts_in_row += 1
        else:
            self._alerts_in_row = 0

        drift_detected = self._alerts_in_row >= self.consecutive_alerts

        status = DriftStatus(drift_detected, self._alerts_in_row, checks, alerts, reasons)

        if alerts:
            logger.warning(
                "DRIFT pre-alert [%d/%d]: %s | alerts=%s",
                self._alerts_in_row,
                self.consecutive_alerts,
                ", ".join(reasons),
                alerts,
            )

        if drift_detected:
            logger.error(
                "DRIFT detected: checks=%s | alerts=%s | reasons=%s",
                {k: round(v, 4) for k, v in checks.items()},
                alerts,
                reasons,
            )

        return status
