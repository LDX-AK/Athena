"""
athena/model/rl_shield.py — AthenaShield (PPO Risk Agent)

Включается через: config flags RL_ENABLED = True
По умолчанию: False — работает классический AthenaRisk

Что делает:
  НЕ генерирует торговые сигналы (это задача LightGBM + Sentiment)
  Управляет РАЗМЕРОМ позиции динамически.

  Статический риск-менеджер: всегда 2% депозита
  RL Shield: учится на реальном P&L, адаптируется к режиму рынка:
    - "горячий" рынок (высокая волатильность) → меньше размер
    - флэт с хорошим sharpe → больше размер
    - после серии убытков → автоматически уменьшает

State Vector (5D — как в Perplexity, но с фиксами):
  [0] balance_norm     — текущий баланс / начальный [-inf, +inf]
  [1] unrealized_pnl   — нереализованный PnL текущей позиции [-1, +1]
  [2] rolling_sharpe   — sharpe за 24ч [-3, +3]
  [3] vol_regime       — ATR percentile [0, 1]
  [4] sentiment_score  — из Kaggle/CryptoPanic [-1, +1]

Action: position_size_pct [-1, +1]
  Положительное → LONG размер
  Отрицательное → SHORT размер (или уменьшить лонг)
  0 → пропустить сделку

Reward:
  reward = sharpe_24h × 10 - maxdd_pct × 5 + pnl_today × 0.1
"""

import numpy as np
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger("athena.rl_shield")

# Проверяем наличие stable-baselines3 — он опциональный
try:
    import gymnasium as gym
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False


@dataclass
class ShieldDecision:
    """Решение AthenaShield об размере позиции."""
    size_multiplier: float  # [0, 1] — умножается на базовый размер из AthenaRisk
    reason:          str


class AthenaRiskEnv:
    """
    Gymnasium Environment для обучения PPO.
    Принимает live P&L данные от AthenaRisk.
    """

    def __init__(self, risk_manager, max_episode_steps: int = 1000):
        if not SB3_AVAILABLE:
            raise ImportError("pip install stable-baselines3 gymnasium")

        import gymnasium as gym

        self.risk      = risk_manager
        self.max_steps = max_episode_steps
        self.step_count = 0

        # Action: размер позиции [0, 1] (только лонг для скальпинга)
        self.action_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(1,), dtype=np.float32
        )

        # State: 5 нормализованных значений
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=(5,), dtype=np.float32
        )

    def reset(self, seed=None, options=None):
        self.step_count = 0
        return self._get_state(), {}

    def step(self, action: np.ndarray) -> Tuple:
        self.step_count += 1
        size_pct = float(action[0])

        # Получаем текущие метрики из AthenaRisk
        stats = self.risk.stats()

        # Reward function (от Perplexity с улучшениями)
        sharpe = stats.get("rolling_sharpe_24h", 0.0)
        maxdd  = abs(self.risk.daily_pnl / (self.risk.day_start_bal + 1e-9))
        pnl_t  = stats.get("daily_pnl", 0.0) / (self.risk.total_balance + 1e-9)

        # Штраф за большой размер при высоком дродауне
        dd_penalty    = maxdd * 5.0
        # Бонус за правильный размер при хорошем sharpe
        sharpe_bonus  = max(0, sharpe) * 10.0 * size_pct
        # PnL компонент
        pnl_component = pnl_t * 0.1

        reward = sharpe_bonus - dd_penalty + pnl_component

        # Терминальное условие
        done = (
            self.step_count >= self.max_steps or
            maxdd > 0.08  # принудительно завершаем если DD > 8%
        )

        state = self._get_state()
        return state, float(reward), done, False, {}

    def _get_state(self) -> np.ndarray:
        """Собираем state vector для PPO."""
        stats = self.risk.stats()
        balance_norm    = self.risk.total_balance / (self.risk.day_start_bal + 1e-9) - 1
        unrealized_pnl  = 0.0  # TODO: подключить через AthenaRouter
        rolling_sharpe  = np.clip(stats.get("rolling_sharpe_24h", 0.0), -3, 3) / 3
        vol_regime      = self.risk.current_vol_regime    # [0, 1] — обновляет AthenaEngineer
        sentiment_score = self.risk.current_sentiment     # [-1, 1] — из AthenaSentiment

        return np.array([
            np.clip(balance_norm,   -1, 1),
            np.clip(unrealized_pnl, -1, 1),
            rolling_sharpe,
            vol_regime,
            sentiment_score,
        ], dtype=np.float32)


class AthenaShield:
    """
    Обёртка над PPO моделью для использования в торговом цикле.
    Если RL_ENABLED=False — возвращает size_multiplier=1.0 (без изменений).
    """

    def __init__(self, config: Dict, risk_manager=None):
        self.config    = config
        self.flags     = config.get("flags", {})
        self.enabled   = self.flags.get("RL_ENABLED", False)
        self.model_path = config.get("rl_model_path", "athena/model/athena_shield_ppo")
        self.risk      = risk_manager

        self._ppo_model  = None
        self._trade_count = 0
        self._retrain_every = self.flags.get("RL_RETRAIN_EVERY", 100)

        if self.enabled:
            self._load_or_init()
        else:
            logger.info("🛡️  AthenaShield: RL выключен (RL_ENABLED=False), используем статический риск")

    def _load_or_init(self):
        """Загружаем обученную PPO модель или инициализируем новую."""
        if not SB3_AVAILABLE:
            logger.error("stable-baselines3 не установлен, RL отключён")
            self.enabled = False
            return

        try:
            self._ppo_model = PPO.load(self.model_path)
            logger.info(f"🛡️  AthenaShield PPO загружен: {self.model_path}")
        except (FileNotFoundError, ValueError):
            logger.info("🛡️  AthenaShield: PPO модели нет, нужно обучение (--mode train_rl)")
            self._ppo_model = None

    def get_size_multiplier(self, state: Optional[np.ndarray] = None) -> ShieldDecision:
        """
        Возвращает множитель размера позиции [0, 1].
        Базовый размер из AthenaRisk × multiplier = финальный размер.

        multiplier=1.0 → максимальный размер (по риск-менеджеру)
        multiplier=0.5 → половина от разрешённого
        multiplier=0.0 → не торговать
        """
        if not self.enabled or self._ppo_model is None:
            return ShieldDecision(1.0, "RL отключён — полный размер")

        if state is None:
            return ShieldDecision(1.0, "Нет state — полный размер")

        action, _ = self._ppo_model.predict(state, deterministic=True)
        multiplier = float(np.clip(action[0], 0.0, 1.0))

        self._trade_count += 1

        # Периодическое дообучение
        if self._trade_count % self._retrain_every == 0:
            logger.info(f"🔄 AthenaShield: запускаем дообучение PPO (сделок: {self._trade_count})")
            self._retrain()

        reason = f"PPO multiplier={multiplier:.2f}"
        return ShieldDecision(multiplier, reason)

    def train(self, total_timesteps: int = 100_000):
        """Первоначальное обучение PPO."""
        if not SB3_AVAILABLE:
            logger.error("pip install stable-baselines3 gymnasium")
            return

        if self.risk is None:
            logger.error("AthenaShield.train() требует risk_manager")
            return

        logger.info(f"🏋️  Обучение AthenaShield PPO ({total_timesteps:,} шагов)...")

        env = DummyVecEnv([lambda: AthenaRiskEnv(self.risk)])
        self._ppo_model = PPO(
            "MlpPolicy", env,
            verbose=1,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
        )
        self._ppo_model.learn(total_timesteps=total_timesteps)
        self._ppo_model.save(self.model_path)
        logger.info(f"✅ AthenaShield PPO сохранён: {self.model_path}")

    def _retrain(self, additional_steps: int = 10_000):
        """Дообучение на новых данных (каждые N сделок)."""
        if self._ppo_model is None or self.risk is None:
            return
        try:
            env = DummyVecEnv([lambda: AthenaRiskEnv(self.risk)])
            self._ppo_model.set_env(env)
            self._ppo_model.learn(total_timesteps=additional_steps, reset_num_timesteps=False)
            self._ppo_model.save(self.model_path)
            logger.info(f"✅ AthenaShield дообучен ({additional_steps} шагов)")
        except Exception as e:
            logger.error(f"Ошибка дообучения PPO: {e}")
