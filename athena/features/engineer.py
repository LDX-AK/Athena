"""
athena/features/engineer.py — AthenaEngineer v2

Источники фич:
  1. Наши оригинальные (EMA, RSI, VWAP, OBI, время)
  2. DRW Kaggle Competition — order flow dynamics, market regime interactions
  3. G-Research Competition — multi-horizon returns, cross-asset correlations
  4. RIT Research — sentiment momentum, tweet volume proxy через vol spikes
  5. Perplexity PPO state — vol_regime (ATR percentile), rolling sharpe

Итого: ~60 признаков вместо 25.
Важно: больше фич ≠ лучше. LightGBM сам выберет нужные через feature importance.
Лишние просто проигнорирует.
"""

import numpy as np
import pandas as pd
import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("athena.features")

_META_KEYS = {"_symbol", "_exchange", "_last_price"}


class AthenaEngineer:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.ema_periods = [9, 21, 50]
        self.rsi_period  = 14
        self.bb_period   = 20
        self.atr_period  = 14
        # Multi-horizon окна можно переопределить из config для ablation / walk-forward экспериментов
        windows = self.config.get("data", {}).get("windows", [5, 10, 15, 30, 60, 120])
        self.windows = [int(w) for w in windows]

    def _group_enabled(self, name: str) -> bool:
        groups = self.config.get("feature_groups", {})
        return bool(groups.get(name, True))

    def transform(self, batch: Dict[str, Any]) -> Optional[Dict[str, float]]:
        ohlcv     = batch.get("ohlcv", [])
        orderbook = batch.get("orderbook", {})
        sentiment = batch.get("sentiment", {})   # sentiment слой опциональный

        if len(ohlcv) < max(self.windows) + 10:
            return None

        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        ).astype(float)

        features = {}

        # ── БЛОК 1: Ценовые фичи ──────────────────────────────
        if self._group_enabled("price"):
            features.update(self._price_features(df))

        # ── БЛОК 2: Классические индикаторы ───────────────────
        if self._group_enabled("indicators"):
            features.update(self._indicators(df))

        # ── БЛОК 3: Order Book (наши оригинальные) ────────────
        if self._group_enabled("orderbook"):
            features.update(self._orderbook_features(orderbook))

        # ── БЛОК 4: DRW Kaggle — Order Flow Dynamics ──────────
        # "Order imbalance consistently ranks in top-10 features"
        if self._group_enabled("orderflow"):
            features.update(self._order_flow_features(df, orderbook))

        # ── БЛОК 5: DRW Kaggle — Multi-Horizon Returns ────────
        if self._group_enabled("multihorizon"):
            features.update(self._multi_horizon_features(df))

        # ── БЛОК 6: DRW Kaggle — Market Regime Interactions ───
        if self._group_enabled("regime"):
            features.update(self._regime_interactions(df, orderbook))

        # ── БЛОК 7: G-Research — Rolling Stats + Momentum ─────
        if self._group_enabled("rolling"):
            features.update(self._rolling_stats(df))

        # ── БЛОК 8: Volatility Regime (для PPO state) ─────────
        if self._group_enabled("volatility"):
            features.update(self._volatility_regime(df))

        # ── БЛОК 9: Volume dynamics (DRW) ─────────────────────
        if self._group_enabled("volume"):
            features.update(self._volume_dynamics(df))

        # ── БЛОК 10: Временные фичи ───────────────────────────
        if self._group_enabled("time"):
            features.update(self._time_features(df))

        # ── БЛОК 11: Sentiment (если есть данные) ─────────────
        if sentiment and self._group_enabled("sentiment"):
            features.update(self._sentiment_features(sentiment))

        # Мета-поля для роутера
        features["_symbol"]     = batch.get("symbol", "")
        features["_exchange"]   = batch.get("exchange", "")
        features["_last_price"] = float(df["close"].iloc[-1])

        # Чистим NaN
        return {
            k: (0.0 if isinstance(v, float) and np.isnan(v) else v)
            for k, v in features.items()
        }

    # ══════════════════════════════════════════════════════════
    # БЛОК 1 — Ценовые фичи (оригинал)
    # ══════════════════════════════════════════════════════════
    def _price_features(self, df) -> Dict:
        c    = df["close"]
        last = c.iloc[-1]
        feats = {}
        for lag in [1, 2, 3, 5, 10, 20]:
            feats[f"ret_{lag}"] = c.iloc[-1] / c.iloc[-(lag+1)] - 1
        feats["price_pos_20"] = (
            (last - c.tail(20).min()) /
            (c.tail(20).max() - c.tail(20).min() + 1e-9)
        )
        feats["price_pos_60"] = (
            (last - c.tail(60).min()) /
            (c.tail(60).max() - c.tail(60).min() + 1e-9)
        )
        return feats

    # ══════════════════════════════════════════════════════════
    # БЛОК 2 — Классические индикаторы (оригинал + улучшения)
    # ══════════════════════════════════════════════════════════
    def _indicators(self, df) -> Dict:
        c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
        feats = {}

        # EMA + slope
        for p in self.ema_periods:
            ema = c.ewm(span=p, adjust=False).mean()
            feats[f"ema_{p}_dist"]  = c.iloc[-1] / ema.iloc[-1] - 1
            feats[f"ema_{p}_slope"] = ema.iloc[-1] / ema.iloc[-3] - 1

        # EMA crossover сигналы
        ema9  = c.ewm(span=9,  adjust=False).mean()
        ema21 = c.ewm(span=21, adjust=False).mean()
        feats["ema_cross_9_21"]  = ema9.iloc[-1] / ema21.iloc[-1] - 1
        feats["ema_cross_trend"] = float(ema9.iloc[-1] > ema21.iloc[-1])

        # RSI нормализованный [-1, 1]
        delta = c.diff()
        gain  = delta.clip(lower=0).rolling(self.rsi_period).mean()
        loss  = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
        rsi   = 100 - 100 / (1 + gain / (loss + 1e-9))
        feats["rsi"]          = (rsi.iloc[-1] - 50) / 50
        feats["rsi_slope"]    = (rsi.iloc[-1] - rsi.iloc[-5]) / 50
        feats["rsi_overbought"] = float(rsi.iloc[-1] > 70)
        feats["rsi_oversold"]   = float(rsi.iloc[-1] < 30)

        # Bollinger Bands
        bb_m  = c.rolling(self.bb_period).mean()
        bb_s  = c.rolling(self.bb_period).std()
        bb_u  = bb_m + 2 * bb_s
        bb_l  = bb_m - 2 * bb_s
        bb_r  = (bb_u - bb_l).iloc[-1]
        feats["bb_pos"]        = (c.iloc[-1] - bb_l.iloc[-1]) / (bb_r + 1e-9)
        feats["bb_width"]      = bb_r / bb_m.iloc[-1]
        feats["bb_squeeze"]    = float(bb_r / bb_m.iloc[-1] < 0.02)  # сжатие = взрыв скоро

        # ATR нормализованный
        tr    = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr   = tr.rolling(self.atr_period).mean()
        feats["atr_norm"]  = atr.iloc[-1] / c.iloc[-1]
        feats["atr_ratio"] = atr.iloc[-1] / atr.rolling(50).mean().iloc[-1]  # vs средний ATR

        # VWAP
        tp   = (h + l + c) / 3
        vwap = (tp * v).cumsum() / v.cumsum()
        feats["vwap_dist"]  = c.iloc[-1] / vwap.iloc[-1] - 1
        feats["above_vwap"] = float(c.iloc[-1] > vwap.iloc[-1])

        # MACD
        macd   = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
        signal = macd.ewm(span=9, adjust=False).mean()
        feats["macd_hist"]  = (macd.iloc[-1] - signal.iloc[-1]) / c.iloc[-1]
        feats["macd_cross"] = float(macd.iloc[-1] > signal.iloc[-1])

        # Stochastic %K (быстрый осциллятор)
        low14  = l.rolling(14).min()
        high14 = h.rolling(14).max()
        stoch  = (c - low14) / (high14 - low14 + 1e-9) * 100
        feats["stoch_k"] = (stoch.iloc[-1] - 50) / 50

        return feats

    # ══════════════════════════════════════════════════════════
    # БЛОК 3 — Order Book (оригинал)
    # ══════════════════════════════════════════════════════════
    def _orderbook_features(self, ob: Dict) -> Dict:
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        if not bids or not asks:
            return {k: 0.0 for k in ["ob_imb_5", "ob_imb_20", "spread", "ba_ratio", "ob_pressure"]}

        bv5  = sum(b[1] for b in bids[:5])
        av5  = sum(a[1] for a in asks[:5])
        bv20 = sum(b[1] for b in bids[:20])
        av20 = sum(a[1] for a in asks[:20])

        return {
            "ob_imb_5":   (bv5  - av5)  / (bv5  + av5  + 1e-9),
            "ob_imb_20":  (bv20 - av20) / (bv20 + av20 + 1e-9),
            "spread":     (asks[0][0] - bids[0][0]) / bids[0][0],
            "ba_ratio":   bv5 / (av5 + 1e-9),
            # Давление покупателей на нескольких уровнях
            "ob_pressure": (bv5 / (bv5 + av5 + 1e-9)) - 0.5,
        }

    # ══════════════════════════════════════════════════════════
    # БЛОК 4 — DRW Kaggle: Order Flow Dynamics
    # "order_imbalance consistently ranks in top-10"
    # ══════════════════════════════════════════════════════════
    def _order_flow_features(self, df, ob: Dict) -> Dict:
        c, v = df["close"], df["volume"]
        feats = {}

        # Trade imbalance через price direction proxy
        # (без тиковых данных используем direction свечей)
        price_dir = np.sign(c.diff())
        buy_vol  = (v * (price_dir > 0)).rolling(10).sum()
        sell_vol = (v * (price_dir < 0)).rolling(10).sum()
        total_v  = buy_vol + sell_vol

        feats["trade_imbalance"]  = ((buy_vol - sell_vol) / (total_v + 1e-9)).iloc[-1]
        feats["buy_pressure_10"]  = (buy_vol  / (total_v + 1e-9)).iloc[-1]

        # Execution ratio proxy (объём vs средний объём)
        vol_ma = v.rolling(20).mean()
        feats["execution_ratio"] = v.iloc[-1] / (vol_ma.iloc[-1] + 1e-9)

        # Total liquidity из стакана
        if ob.get("bids") and ob.get("asks"):
            bids, asks = ob["bids"], ob["asks"]
            total_liq  = sum(b[1] for b in bids[:10]) + sum(a[1] for a in asks[:10])
            buy_press  = sum(b[1] for b in bids[:5])
            feats["total_liquidity"] = np.log1p(total_liq)
            feats["liquidity_ratio"] = buy_press / (total_liq / 2 + 1e-9)
        else:
            feats["total_liquidity"] = 0.0
            feats["liquidity_ratio"] = 1.0

        return feats

    # ══════════════════════════════════════════════════════════
    # БЛОК 5 — DRW + G-Research: Multi-Horizon Returns
    # "Multiple time horizons: [5,10,15,30,60,120] minutes"
    # ══════════════════════════════════════════════════════════
    def _multi_horizon_features(self, df) -> Dict:
        c     = df["close"]
        h     = df["high"]
        l     = df["low"]
        feats = {}

        for w in self.windows:
            if len(c) <= w:
                continue
            ret = c.iloc[-1] / c.iloc[-(w+1)] - 1
            feats[f"ret_{w}m"]          = ret
            feats[f"vol_{w}m"]          = c.pct_change().rolling(w).std().iloc[-1]
            feats[f"high_{w}m_dist"]    = c.iloc[-1] / h.tail(w).max() - 1
            feats[f"low_{w}m_dist"]     = c.iloc[-1] / l.tail(w).min() - 1
            feats[f"range_{w}m"]        = (h.tail(w).max() - l.tail(w).min()) / c.iloc[-1]

        # Momentum consistency — сколько из последних N свечей закрылись вверх
        for w in [5, 10, 20]:
            up_candles = (c.diff().tail(w) > 0).sum()
            feats[f"up_ratio_{w}"] = up_candles / w

        return feats

    # ══════════════════════════════════════════════════════════
    # БЛОК 6 — DRW: Market Regime Interactions
    # "Cross-feature interactions enhance performance"
    # ══════════════════════════════════════════════════════════
    def _regime_interactions(self, df, ob: Dict) -> Dict:
        c, v = df["close"], df["volume"]
        feats = {}

        # vol × order_imbalance
        vol_norm = v.iloc[-1] / (v.rolling(20).mean().iloc[-1] + 1e-9)
        ob_imb   = 0.0
        if ob.get("bids") and ob.get("asks"):
            bv = sum(b[1] for b in ob["bids"][:5])
            av = sum(a[1] for a in ob["asks"][:5])
            ob_imb = (bv - av) / (bv + av + 1e-9)

        feats["vol_x_imbalance"]  = vol_norm * ob_imb
        feats["vol_x_momentum"]   = vol_norm * (c.iloc[-1] / c.iloc[-6] - 1)

        # ATR × volume — высокая волатильность при высоком объёме = тренд
        tr  = pd.concat([
            df["high"] - df["low"],
            (df["high"] - c.shift()).abs(),
            (df["low"]  - c.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        feats["atr_x_vol"] = (atr / c.iloc[-1]) * vol_norm

        return feats

    # ══════════════════════════════════════════════════════════
    # БЛОК 7 — G-Research: Rolling Stats
    # ══════════════════════════════════════════════════════════
    def _rolling_stats(self, df) -> Dict:
        c     = df["close"]
        rets  = c.pct_change().dropna()
        feats = {}

        for w in [10, 30, 60]:
            r = rets.tail(w)
            if len(r) < 3:
                continue
            mean_r = r.mean()
            std_r  = r.std()
            feats[f"rolling_mean_{w}"]     = mean_r
            feats[f"rolling_std_{w}"]      = std_r
            # Sharpe rolling (без risk-free rate для простоты)
            feats[f"rolling_sharpe_{w}"]   = mean_r / (std_r + 1e-9)
            # Skewness — асимметрия доходностей
            feats[f"rolling_skew_{w}"]     = float(r.skew())
            # Autocorrelation lag-1 — momentum vs mean-reversion
            if len(r) > 2:
                feats[f"autocorr_{w}"] = float(r.autocorr(lag=1))

        return feats

    # ══════════════════════════════════════════════════════════
    # БЛОК 8 — Volatility Regime (для PPO state vector)
    # ATR percentile показывает "горячий" или "холодный" рынок
    # ══════════════════════════════════════════════════════════
    def _volatility_regime(self, df) -> Dict:
        c = df["close"]
        h = df["high"]
        l = df["low"]

        tr  = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()

        # Percentile текущего ATR относительно последних 60 свечей
        atr_history = atr.tail(60).dropna()
        current_atr = atr.iloc[-1]
        if len(atr_history) > 0:
            percentile = float((atr_history < current_atr).mean())
        else:
            percentile = 0.5

        # Режим рынка: 0=тихий, 0.5=нормальный, 1=взрывной
        return {
            "vol_regime":       percentile,
            "vol_regime_hot":   float(percentile > 0.75),
            "vol_regime_quiet": float(percentile < 0.25),
            # Изменение волатильности (ускорение)
            "vol_acceleration": (atr.iloc[-1] / atr.iloc[-10] - 1) if len(atr) > 10 else 0.0,
        }

    # ══════════════════════════════════════════════════════════
    # БЛОК 9 — Volume Dynamics (DRW)
    # ══════════════════════════════════════════════════════════
    def _volume_dynamics(self, df) -> Dict:
        v     = df["volume"]
        c     = df["close"]
        feats = {}

        for w in [5, 10, 20, 60]:
            if len(v) <= w:
                continue
            vol_ma  = v.rolling(w).mean()
            vol_std = v.rolling(w).std()
            feats[f"vol_ratio_{w}"]    = np.log1p(v.iloc[-1] / (vol_ma.iloc[-1] + 1e-9))
            feats[f"vol_zscore_{w}"]   = (v.iloc[-1] - vol_ma.iloc[-1]) / (vol_std.iloc[-1] + 1e-9)
            feats[f"vol_momentum_{w}"] = v.iloc[-1] - vol_ma.iloc[-1]

        # OBV-like (On Balance Volume)
        obv = (v * np.sign(c.diff())).cumsum()
        feats["obv_slope"] = (obv.iloc[-1] - obv.iloc[-10]) / (abs(obv.iloc[-10]) + 1e-9)

        return feats

    # ══════════════════════════════════════════════════════════
    # БЛОК 10 — Временные фичи + SessionContext v1
    # ══════════════════════════════════════════════════════════
    def _time_features(self, df) -> Dict:
        ts = df["timestamp"].iloc[-1] / 1000
        dt = datetime.datetime.utcfromtimestamp(ts)
        h, m = dt.hour, dt.minute
        dow  = dt.weekday()  # 0=пн, 6=вс

        session_asia = float(0 <= h < 8)
        session_europe = float(7 <= h < 15)
        session_us = float(13 <= h < 22)
        session_overlap = float(13 <= h < 15)
        is_weekend = float(dow >= 5)

        return {
            "hour_sin":      np.sin(2 * np.pi * h / 24),
            "hour_cos":      np.cos(2 * np.pi * h / 24),
            "minute_sin":    np.sin(2 * np.pi * m / 60),
            "dow_sin":       np.sin(2 * np.pi * dow / 7),
            "hour_bucket":   int(h),
            "session_asia":  session_asia,
            "session_europe": session_europe,
            "session_us":    session_us,
            "session_overlap": session_overlap,
            "is_weekend":    is_weekend,
            "session_open_phase": float(h in {0, 7, 13}),
            "session_close_phase": float(h in {8, 15, 22}),
            # backward-compatible legacy fields
            "london_open":   float(8 <= h <= 12),
            "ny_open":       float(13 <= h <= 17),
            "asia_open":     session_asia,
            "overlap_session": session_overlap,
            "weekend":       is_weekend,
        }

    # ══════════════════════════════════════════════════════════
    # БЛОК 11 — Sentiment (из Kaggle CSV или CryptoPanic)
    # Опциональный — если sentiment={} просто пропускается
    # ══════════════════════════════════════════════════════════
    def _sentiment_features(self, sentiment: Dict) -> Dict:
        """
        Ожидаем sentiment = {
            "score":   float,  # [-1, +1] нормализованный
            "volume":  float,  # кол-во новостей/твитов за период
            "trend":   float,  # изменение sentiment за N периодов
        }
        """
        score  = sentiment.get("score",  0.0)
        volume = sentiment.get("volume", 0.0)
        trend  = sentiment.get("trend",  0.0)

        return {
            "sentiment_score":    np.clip(score, -1, 1),
            "sentiment_volume":   np.log1p(max(volume, 0)),
            "sentiment_trend":    np.clip(trend, -1, 1),
            # Sentiment momentum — резкий рост позитива = сигнал
            "sentiment_momentum": float(score > 0.3 and trend > 0.1),
            "sentiment_fear":     float(score < -0.3),
            # Взаимодействие sentiment × volume (сильный сигнал = громкий)
            "sentiment_x_vol":    score * np.log1p(max(volume, 0)),
        }

    def get_ml_features(self, features: Dict) -> Dict:
        """Возвращает только фичи для ML (без мета-полей)."""
        return {k: v for k, v in features.items() if k not in _META_KEYS}
