"""
athena/risk/manager.py — AthenaRisk v2

Улучшения vs v1:
  - Dynamic Kelly Criterion (адаптивный размер позиции)
  - Rolling Sharpe для PPO state vector
  - current_vol_regime и current_sentiment для AthenaShield
  - get_ppo_state() → np.ndarray для RL агента
"""

import time
import datetime
import numpy as np
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from athena.model.signal import AthenaSignal

logger = logging.getLogger("athena.risk")


@dataclass
class AthenaPosition:
    symbol:      str
    exchange:    str
    direction:   int
    entry_price: float
    size_usd:    float
    sl:          float
    tp:          float
    entry_time:  float = field(default_factory=time.time)


@dataclass
class AthenaDecision:
    approved:          bool
    reason:            str
    adjusted_size_usd: float = 0.0


class AthenaRisk:
    def __init__(self, config: Dict):
        self.cfg             = config
        self.open_positions: List[AthenaPosition] = []
        self.daily_pnl       = 0.0
        self.total_balance   = 10_000.0
        self.day_start_bal   = 10_000.0
        self.last_loss_time  = 0.0
        self.trade_history:  List[Dict] = []
        self._last_day       = -1

        # PPO state fields — обновляются из AthenaEngineer
        self.current_vol_regime  = 0.5   # ATR percentile [0, 1]
        self.current_sentiment   = 0.0   # sentiment score [-1, 1]

        # Rolling P&L для sharpe расчёта (последние 24ч сделок)
        self._pnl_rolling: deque = deque(maxlen=200)

        # Dynamic Kelly
        self.kelly_enabled   = config.get("kelly_enabled", True)
        self.kelly_fraction  = config.get("kelly_fraction", 0.25)

    def check(self, signal: AthenaSignal) -> AthenaDecision:
        if signal.direction == 0:
            return AthenaDecision(False, "HOLD")

        self._reset_daily_if_needed()

        # 1. Уверенность модели
        if signal.confidence < self.cfg["min_confidence"]:
            return AthenaDecision(False,
                f"Confidence {signal.confidence:.3f} < {self.cfg['min_confidence']}")

        # 2. Кулдаун после убытка
        cd = self.cfg["cooldown_after_loss_sec"] - (time.time() - self.last_loss_time)
        if cd > 0:
            return AthenaDecision(False, f"Cooldown {cd:.0f}s")

        # 3. Дневной дродаун
        dd = self.daily_pnl / (self.day_start_bal + 1e-9)
        if dd <= -self.cfg["max_daily_drawdown_pct"]:
            return AthenaDecision(False, f"Daily DD {dd*100:.1f}% превысил лимит")

        # 4. Максимум позиций
        if len(self.open_positions) >= self.cfg["max_open_positions"]:
            return AthenaDecision(False, f"Макс. позиций: {len(self.open_positions)}")

        # 5. Нет дублей
        for p in self.open_positions:
            if p.symbol == signal.symbol and p.direction == signal.direction:
                return AthenaDecision(False, f"Дубль {signal.symbol}")

        # 6. Размер позиции
        size = self._calculate_size(signal)

        return AthenaDecision(True, "OK", size)

    def _calculate_size(self, signal: AthenaSignal) -> float:
        """
        Dynamic Kelly Criterion.

        Классический Kelly: f = (p × b - q) / b
          p = win rate, q = 1-p, b = avg_win / avg_loss

        Мы используем дробный Kelly (25%) для консерватизма
        и умножаем на confidence модели.
        """
        base_size = self.total_balance * self.cfg["max_position_pct"]

        if not self.kelly_enabled or len(self.trade_history) < 20:
            # Недостаточно истории → используем базовый размер × confidence
            return max(10.0, base_size * signal.confidence)

        wins   = [t["pnl"] for t in self.trade_history[-50:] if t.get("pnl", 0) > 0]
        losses = [t["pnl"] for t in self.trade_history[-50:] if t.get("pnl", 0) < 0]

        if not wins or not losses:
            return max(10.0, base_size * signal.confidence)

        p     = len(wins) / (len(wins) + len(losses))    # win rate
        b     = abs(np.mean(wins)) / (abs(np.mean(losses)) + 1e-9)  # win/loss ratio
        kelly = (p * b - (1 - p)) / (b + 1e-9)
        kelly = max(0.0, min(kelly, 1.0))

        # Дробный Kelly × confidence модели
        size  = self.total_balance * kelly * self.kelly_fraction * signal.confidence

        # Ограничиваем максимальным размером из конфига
        max_size = self.total_balance * self.cfg["max_position_pct"]
        return max(10.0, min(size, max_size))

    def update(self, result: Dict):
        pnl = result.get("pnl", 0.0)
        self.daily_pnl     += pnl
        self.total_balance += pnl
        self._pnl_rolling.append(pnl)

        if pnl < 0:
            self.last_loss_time = time.time()
            logger.warning(f"❌ Убыток ${pnl:.2f} | Баланс ${self.total_balance:.2f}")
        else:
            logger.info(f"💰 Прибыль ${pnl:.2f} | Баланс ${self.total_balance:.2f}")

        self.trade_history.append({
            **result,
            "ts":      time.time(),
            "balance": self.total_balance,
        })

    def calculate_sl_tp(self, price: float, direction: int):
        sl_pct = self.cfg["stop_loss_pct"]
        tp_pct = self.cfg["take_profit_pct"]
        if direction == 1:
            return price * (1 - sl_pct), price * (1 + tp_pct)
        return price * (1 + sl_pct), price * (1 - tp_pct)

    def get_ppo_state(self) -> np.ndarray:
        """
        Формируем state vector для AthenaShield (PPO).
        Вызывается перед каждым решением о размере позиции.
        """
        balance_norm   = self.total_balance / (self.day_start_bal + 1e-9) - 1
        unrealized_pnl = 0.0  # TODO: подключить через AthenaRouter
        rolling_sharpe = self._rolling_sharpe_24h()
        vol_regime     = self.current_vol_regime
        sentiment      = self.current_sentiment

        return np.array([
            np.clip(balance_norm,   -1, 1),
            np.clip(unrealized_pnl, -1, 1),
            np.clip(rolling_sharpe / 3, -1, 1),
            vol_regime,
            sentiment,
        ], dtype=np.float32)

    def _rolling_sharpe_24h(self) -> float:
        """Rolling Sharpe за последние N сделок (proxy за 24ч)."""
        if len(self._pnl_rolling) < 5:
            return 0.0
        pnls = np.array(list(self._pnl_rolling))
        mean = pnls.mean()
        std  = pnls.std()
        return float(mean / (std + 1e-9) * np.sqrt(252))

    def stats(self) -> Dict:
        wins   = [t["pnl"] for t in self.trade_history if t.get("pnl", 0) > 0]
        losses = [t["pnl"] for t in self.trade_history if t.get("pnl", 0) < 0]
        total  = len(self.trade_history)
        return {
            "total_trades":       total,
            "win_rate":           len(wins) / total if total else 0,
            "total_pnl":          sum(t.get("pnl", 0) for t in self.trade_history),
            "daily_pnl":          self.daily_pnl,
            "open_positions":     len(self.open_positions),
            "balance":            self.total_balance,
            "avg_win":            float(np.mean(wins))   if wins   else 0,
            "avg_loss":           float(np.mean(losses)) if losses else 0,
            "rolling_sharpe_24h": self._rolling_sharpe_24h(),
            "vol_regime":         self.current_vol_regime,
            "sentiment":          self.current_sentiment,
        }

    def _reset_daily_if_needed(self):
        today = datetime.date.today().toordinal()
        if today != self._last_day:
            self.daily_pnl     = 0.0
            self.day_start_bal = self.total_balance
            self._last_day     = today
            logger.info(f"📅 Новый день | Баланс ${self.total_balance:.2f}")
