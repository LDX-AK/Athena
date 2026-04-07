"""
athena/model/retrain_policy.py — AthenaRetrainPolicy

Решает, когда нужно запускать retrain:
- планово (schedule_days),
- внепланово при drift,
- с cooldown между запусками.

На текущем этапе возвращает решение и reason, без автоматического обучения.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List


@dataclass
class RetrainDecision:
    trigger: bool
    reason: str


class AthenaRetrainPolicy:
    def __init__(self, config: Dict):
        cfg = config.get("retrain", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.schedule_days = int(cfg.get("schedule_days", 10))
        self.cooldown_hours = int(cfg.get("cooldown_hours", 24))
        self.trigger_on_drift = bool(cfg.get("trigger_on_drift", True))
        self.dry_run = bool(cfg.get("dry_run", True))
        self.max_retrains_per_week = int(cfg.get("max_retrains_per_week", 3))
        self.critical_alerts_required = int(cfg.get("critical_alerts_required", 2))
        self.emergency_bypass_enabled = bool(cfg.get("emergency_bypass_enabled", True))
        self.emergency_min_severity = int(cfg.get("emergency_min_severity", 7))
        self.emergency_cooldown_hours = int(cfg.get("emergency_cooldown_hours", 6))

        self.started_at = datetime.now(timezone.utc)
        self.last_retrain_at = None
        self.retrain_history: List[datetime] = []
        self.last_emergency_retrain_at = None
        self.critical_alerts = {
            "SHARPE_DRIFT",
            "REGIME_VOLATILITY",
            "LOSS_STREAK",
            "SHARPE_FLOOR",
        }
        self.alert_severity = {
            "SHARPE_FLOOR": 1,
            "WINRATE_FLOOR": 1,
            "WINRATE_DRIFT": 2,
            "CONFIDENCE_DRIFT": 2,
            "SHARPE_DRIFT": 3,
            "REGIME_VOLATILITY": 3,
            "LOSS_STREAK": 4,
            "PROFIT_FACTOR_FLOOR": 2,
        }

    def evaluate(self, drift_detected: bool = False, alerts: List[str] | None = None) -> RetrainDecision:
        if not self.enabled:
            return RetrainDecision(False, "retrain-disabled")

        now = datetime.now(timezone.utc)
        alerts = alerts or []
        severity_score = sum(self.alert_severity.get(a, 1) for a in alerts)

        week_ago = now - timedelta(days=7)
        self.retrain_history = [ts for ts in self.retrain_history if ts >= week_ago]
        if len(self.retrain_history) >= self.max_retrains_per_week:
            return RetrainDecision(False, "weekly-budget-exhausted")

        is_emergency = (
            self.emergency_bypass_enabled
            and "LOSS_STREAK" in alerts
            and "REGIME_VOLATILITY" in alerts
            and severity_score >= self.emergency_min_severity
        )

        if is_emergency:
            if self.last_emergency_retrain_at is not None:
                emergency_left = self.last_emergency_retrain_at + timedelta(hours=self.emergency_cooldown_hours) - now
                if emergency_left.total_seconds() > 0:
                    return RetrainDecision(False, f"emergency-rate-limited:{int(emergency_left.total_seconds())}s")
            return RetrainDecision(True, f"EMERGENCY-REGIME-BREAK:severity={severity_score}")

        if self.last_retrain_at is not None:
            cooldown_left = self.last_retrain_at + timedelta(hours=self.cooldown_hours) - now
            if cooldown_left.total_seconds() > 0:
                return RetrainDecision(False, f"cooldown-active:{int(cooldown_left.total_seconds())}s")

        if self.trigger_on_drift and drift_detected:
            critical_count = len(set(alerts) & self.critical_alerts)
            if critical_count >= self.critical_alerts_required:
                return RetrainDecision(
                    True,
                    f"drift-trigger:{critical_count}-critical:severity={severity_score}",
                )
            return RetrainDecision(
                False,
                f"drift-insufficient-critical:{critical_count}:severity={severity_score}",
            )

        elapsed_days = (now - self.started_at).total_seconds() / 86400
        if elapsed_days >= self.schedule_days:
            return RetrainDecision(True, "scheduled-trigger")

        return RetrainDecision(False, "no-trigger")

    def mark_retrain_started(self):
        now = datetime.now(timezone.utc)
        self.last_retrain_at = now
        self.retrain_history.append(now)

    def mark_emergency_retrain_started(self):
        now = datetime.now(timezone.utc)
        self.last_emergency_retrain_at = now
        self.last_retrain_at = now
        self.retrain_history.append(now)
