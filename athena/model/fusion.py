"""
athena/model/fusion.py — SignalFusion

Hybrid Signal: LightGBM % + Sentiment % с настраиваемыми весами.

Архитектура:
  AthenaModel (LightGBM)  →  signal_lgbm  ─┐
                                             ├→ SignalFusion → AthenaSignal (итоговый)
  SentimentSignal          →  signal_sent  ─┘

Веса задаются в config:
  LGBM_WEIGHT:      0.70
  SENTIMENT_WEIGHT: 0.30

Sentiment можно полностью отключить: SENTIMENT_ENABLED=False
Тогда итоговый сигнал = чистый LightGBM.
"""

import numpy as np
import logging
from dataclasses import dataclass
from typing import Dict, Optional
from athena.model.signal import AthenaModel, AthenaSignal

logger = logging.getLogger("athena.fusion")


@dataclass
class RawSignal:
    """Сырой сигнал от одного источника."""
    direction:  int    # 1=BUY, -1=SELL, 0=HOLD
    confidence: float  # [0, 1]
    source:     str    # "lgbm" | "sentiment"


class SentimentSignal:
    """
    Конвертирует sentiment score в торговый сигнал.

    Логика:
      score > +threshold  → BUY  (позитив = покупатели активны)
      score < -threshold  → SELL (негатив = продавцы активны)
      иначе               → HOLD
    """

    def __init__(self, buy_threshold: float = 0.25, sell_threshold: float = -0.25):
        self.buy_threshold  = buy_threshold
        self.sell_threshold = sell_threshold

    def predict(self, sentiment: Dict) -> RawSignal:
        score  = sentiment.get("score",  0.0)
        volume = sentiment.get("volume", 0.0)
        trend  = sentiment.get("trend",  0.0)

        # Комбинированный скор: основной + бонус за тренд
        combined = score * 0.7 + trend * 0.3

        # Уверенность растёт с объёмом новостей (log-нормализованный)
        vol_factor   = min(1.0, volume / 3.0)  # насыщение при volume=3 (log)
        base_conf    = abs(combined)
        confidence   = min(0.95, base_conf * (0.5 + 0.5 * vol_factor))

        if combined > self.buy_threshold:
            return RawSignal(1, confidence, "sentiment")
        elif combined < self.sell_threshold:
            return RawSignal(-1, confidence, "sentiment")
        else:
            return RawSignal(0, confidence, "sentiment")


class SignalFusion:
    """
    Объединяет сигналы от LightGBM и Sentiment с настраиваемыми весами.

    Алгоритм fusion:
      1. Получаем direction и confidence от каждого источника
      2. Конвертируем в weighted score: score = direction × confidence × weight
      3. Суммируем: total_score = lgbm_score + sentiment_score
      4. Итоговый direction = sign(total_score)
      5. Итоговая confidence = abs(total_score) / max_possible

    Пример:
      LightGBM:  BUY  conf=0.80  weight=0.70  → score = +0.56
      Sentiment: SELL conf=0.60  weight=0.30  → score = -0.18
      Total:     +0.38 → BUY с confidence=0.38/0.70=0.54
    """

    def __init__(self, config: Dict):
        flags = config.get("flags", {})
        sentiment_cfg = config.get("sentiment", {})
        self.lgbm_weight      = flags.get("LGBM_WEIGHT",      0.70)
        self.sentiment_weight = flags.get("SENTIMENT_WEIGHT", 0.30)
        self.runtime_timeframe = str(config.get("runtime_timeframe") or config.get("timeframe", "1m"))
        self.sentiment_min_timeframe = str(sentiment_cfg.get("min_timeframe", "30m"))
        self.sentiment_mode = str(sentiment_cfg.get("mode", "weighted"))
        self.sentiment_enabled = bool(flags.get("SENTIMENT_ENABLED", True))
        self.sentiment_weighted_enabled = (
            self.sentiment_enabled
            and self.timeframe_allows_weighted_sentiment(
                self.runtime_timeframe,
                self.sentiment_min_timeframe,
            )
        )
        self.min_confidence   = config.get("risk", {}).get("min_confidence", 0.65)

        self.lgbm_model      = AthenaModel(config["model_path"])
        self.sentiment_model = SentimentSignal()

        sentiment_state = "ON" if self.sentiment_weighted_enabled else (
            "FILTER_ONLY" if self.sentiment_enabled else "OFF"
        )
        logger.info(
            f"🔀 SignalFusion инициализирован: "
            f"LightGBM={self.lgbm_weight:.0%} | "
            f"Sentiment={self.sentiment_weight:.0%} "
            f"({sentiment_state}, tf={self.runtime_timeframe}, min_tf={self.sentiment_min_timeframe})"
        )

    @staticmethod
    def _tf_to_minutes(tf: str) -> int:
        tf = str(tf).strip().lower()
        try:
            if tf.endswith("m"):
                return max(1, int(tf[:-1]))
            if tf.endswith("h"):
                return max(1, int(tf[:-1]) * 60)
            if tf.endswith("d"):
                return max(1, int(tf[:-1]) * 1440)
        except ValueError:
            pass
        return 1

    @classmethod
    def timeframe_allows_weighted_sentiment(cls, runtime_tf: str, min_tf: str = "30m") -> bool:
        return cls._tf_to_minutes(runtime_tf) >= cls._tf_to_minutes(min_tf)

    def predict(self, features: Dict, sentiment: Optional[Dict] = None) -> AthenaSignal:
        """
        Главный метод — получаем итоговый сигнал.

        features:  технические фичи от AthenaEngineer
        sentiment: {'score': float, 'volume': float, 'trend': float} или None
        """
        # ── LightGBM сигнал ──────────────────────────────────
        lgbm_raw = self.lgbm_model.predict(features)
        lgbm_score = lgbm_raw.direction * lgbm_raw.confidence * self.lgbm_weight

        # ── Sentiment сигнал ──────────────────────────────────
        sent_score = 0.0
        if self.sentiment_weighted_enabled and sentiment:
            sent_raw   = self.sentiment_model.predict(sentiment)
            sent_score = sent_raw.direction * sent_raw.confidence * self.sentiment_weight
        elif not self.sentiment_weighted_enabled:
            # Sentiment выключен или переведён в macro/filter-only режим → работаем на чистом LightGBM
            lgbm_score = lgbm_raw.direction * lgbm_raw.confidence

        # ── Fusion ────────────────────────────────────────────
        total_score = lgbm_score + sent_score

        # Максимально возможный score (для нормализации confidence)
        if self.sentiment_weighted_enabled and sentiment:
            max_score = self.lgbm_weight + self.sentiment_weight  # = 1.0
        else:
            max_score = 1.0

        final_confidence = abs(total_score) / max_score
        final_direction  = int(np.sign(total_score))

        # Если signals противоречат друг другу сильно → снижаем уверенность
        if (lgbm_raw.direction != 0 and
                sentiment and sent_score != 0 and
                np.sign(lgbm_score) != np.sign(sent_score)):
            final_confidence *= 0.75  # штраф за противоречие
            logger.debug(
                f"⚡ Сигналы противоречат: LGBM={lgbm_raw.direction} "
                f"Sent={int(np.sign(sent_score))} → conf снижена до {final_confidence:.3f}"
            )

        symbol   = features.get("_symbol", "")
        exchange = features.get("_exchange", "")
        price    = features.get("_last_price", 0.0)

        # Логируем fusion
        if final_direction != 0:
            logger.info(
                f"🔀 Fusion [{symbol}]: "
                f"LGBM={lgbm_raw.direction}({lgbm_raw.confidence:.2f}) "
                f"Sent={int(np.sign(sent_score)) if sent_score else 'OFF'} "
                f"→ {final_direction} conf={final_confidence:.3f}"
            )

        return AthenaSignal(
            direction=final_direction,
            confidence=float(final_confidence),
            symbol=symbol,
            exchange=exchange,
            price=float(price),
            features=features,
        )

    def update_weights(self, lgbm_weight: float, sentiment_weight: float):
        """
        Динамическое изменение весов на лету.
        Можно вызвать из dashboard или при деградации одного из источников.
        """
        assert abs(lgbm_weight + sentiment_weight - 1.0) < 0.01, \
            "Веса должны давать сумму 1.0"
        self.lgbm_weight      = lgbm_weight
        self.sentiment_weight = sentiment_weight
        logger.info(f"🔀 Веса обновлены: LGBM={lgbm_weight:.0%} Sent={sentiment_weight:.0%}")

    def disable_sentiment(self):
        """Быстрое отключение sentiment (например при недоступности API)."""
        self.sentiment_enabled = False
        self.sentiment_weighted_enabled = False
        logger.warning("⚠️  Sentiment отключён, работаем на чистом LightGBM")

    def enable_sentiment(self):
        self.sentiment_enabled = True
        self.sentiment_weighted_enabled = self.timeframe_allows_weighted_sentiment(
            self.runtime_timeframe,
            self.sentiment_min_timeframe,
        )
        logger.info("✅ Sentiment включён")
