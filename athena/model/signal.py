"""
athena/model/signal.py — AI мозг Athena (AthenaModel)
"""

import pickle
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional
import logging

logger = logging.getLogger("athena.model")

# Мета-поля которые не передаём в модель
_META_KEYS = {"_symbol", "_exchange", "_last_price"}


@dataclass
class AthenaSignal:
    direction:  int     # 1=BUY | -1=SELL | 0=HOLD
    confidence: float   # [0.0, 1.0]
    symbol:     str
    exchange:   str
    price:      float
    features:   Dict


class AthenaModel:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self._schema_alignment_logged = False
        self.model      = self._load()

    def _load(self):
        try:
            with open(self.model_path, "rb") as f:
                m = pickle.load(f)
            logger.info(f"🧠 AthenaModel загружена: {self.model_path}")
            return m
        except FileNotFoundError:
            logger.warning("⚠️  Модель не найдена → baseline режим (OBI + RSI)")
            return None

    def _trained_feature_names(self):
        if self.model is None:
            return None

        for attr_name in ("feature_name_", "feature_names_in_"):
            value = getattr(self.model, attr_name, None)
            if value is None:
                continue
            if callable(value):
                try:
                    value = value()
                except TypeError:
                    pass
            names = [str(name) for name in value]
            if names:
                return names

        booster = getattr(self.model, "booster_", None)
        if booster is not None and hasattr(booster, "feature_name"):
            try:
                names = [str(name) for name in booster.feature_name()]
                if names:
                    return names
            except Exception:
                pass

        return None

    def _prepare_inference_frame(self, X_dict: Dict) -> pd.DataFrame:
        X = pd.DataFrame([X_dict], dtype=float)
        trained_feature_names = self._trained_feature_names()
        if not trained_feature_names:
            return X

        missing = [name for name in trained_feature_names if name not in X.columns]
        extra = [name for name in X.columns if name not in trained_feature_names]

        for name in missing:
            X[name] = 0.0
        if extra:
            X = X.drop(columns=extra)

        X = X.reindex(columns=trained_feature_names, fill_value=0.0)

        if missing or extra:
            log_fn = logger.warning if not self._schema_alignment_logged else logger.debug
            log_fn(
                "⚠️ Inference schema aligned for %s | missing=%d extra=%d",
                self.model_path,
                len(missing),
                len(extra),
            )
            self._schema_alignment_logged = True

        return X

    def predict(self, features: Optional[Dict]) -> AthenaSignal:
        null = AthenaSignal(0, 0.0, "", "", 0.0, {})
        if not features:
            return null

        symbol   = features.get("_symbol", "")
        exchange = features.get("_exchange", "")
        price    = features.get("_last_price", 0.0)

        # Убираем мета-поля перед инференсом
        X_dict = {k: v for k, v in features.items() if k not in _META_KEYS}

        if self.model is None:
            return self._baseline(X_dict, symbol, exchange, price)

        X     = self._prepare_inference_frame(X_dict)
        proba = self.model.predict_proba(X)[0]   # [SELL, HOLD, BUY]
        cls   = int(np.argmax(proba))
        conf  = float(proba[cls])
        dir_  = {0: -1, 1: 0, 2: 1}[cls]

        return AthenaSignal(dir_, conf, symbol, exchange, price, features)

    def _baseline(self, f, symbol, exchange, price) -> AthenaSignal:
        """Baseline без ML: OBI + RSI → быстрая проверка инфраструктуры."""
        ob_imb = f.get("ob_imb_5", 0)
        rsi    = f.get("rsi", 0)              # уже [-1, 1]
        score  = 0.6 * ob_imb + 0.4 * rsi
        # Порог снижен до 0.05 (placeholder пока нет athena_brain.pkl)
        if   score >  0.05: return AthenaSignal( 1, min(0.95, abs(score) + 0.45), symbol, exchange, price, f)
        elif score < -0.05: return AthenaSignal(-1, min(0.95, abs(score) + 0.45), symbol, exchange, price, f)
        else:               return AthenaSignal( 0, 0.5,                           symbol, exchange, price, f)


class AthenaTrainer:
    """Обучение и переобучение AthenaModel."""

    def __init__(self, engineer, config):
        self.engineer = engineer
        self.config   = config

    def create_labels(self, df, tp_pct=0.006, sl_pct=0.003, lookahead=10):
        """Triple Barrier Labeling (Lopez de Prado)."""
        close  = df["close"].values
        labels = []
        for i in range(len(close) - lookahead):
            entry = close[i]
            tp, sl = entry * (1 + tp_pct), entry * (1 - sl_pct)
            label  = 0
            for j in range(1, lookahead + 1):
                fp = close[i + j]
                if fp >= tp: label =  1; break
                if fp <= sl: label = -1; break
            labels.append(label)
        labels.extend([0] * lookahead)
        return pd.Series(labels, index=df.index)

    def train(self, historical_data: list, save_path: str):
        try:
            import lightgbm as lgb
            from sklearn.model_selection import TimeSeriesSplit
        except ImportError:
            logger.error("pip install lightgbm scikit-learn"); return

        logger.info("🏋️  Athena обучается...")
        df     = pd.DataFrame(historical_data,
                              columns=["timestamp","open","high","low","close","volume"]).astype(float)
        labels = self.create_labels(df,
                                    tp_pct=self.config["risk"]["take_profit_pct"],
                                    sl_pct=self.config["risk"]["stop_loss_pct"])

        lookback = 100
        all_feats = []
        for i in range(lookback, len(df)):
            batch = {"ohlcv": df.iloc[i-lookback:i].values.tolist(), "orderbook": {}}
            f = self.engineer.transform(batch)
            if f:
                # убираем мета-поля
                all_feats.append({k: v for k, v in f.items() if k not in _META_KEYS})

        X = pd.DataFrame(all_feats)
        y = labels.iloc[lookback:lookback + len(all_feats)].map({-1: 0, 0: 1, 1: 2})

        tscv   = TimeSeriesSplit(n_splits=5)
        scores = []
        for fold, (tr, val) in enumerate(tscv.split(X)):
            m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
                                   num_leaves=31, min_child_samples=50, subsample=0.8,
                                   colsample_bytree=0.8, class_weight="balanced",
                                   random_state=42, verbose=-1)
            m.fit(X.iloc[tr], y.iloc[tr])
            scores.append(m.score(X.iloc[val], y.iloc[val]))
            logger.info(f"  Fold {fold+1}: acc={scores[-1]:.4f}")

        import numpy as np
        logger.info(f"📊 Средняя точность: {np.mean(scores):.4f} ± {np.std(scores):.4f}")

        final = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
                                   num_leaves=31, min_child_samples=50, subsample=0.8,
                                   colsample_bytree=0.8, class_weight="balanced",
                                   random_state=42, verbose=-1)
        final.fit(X, y)

        with open(save_path, "wb") as f:
            pickle.dump(final, f)
        logger.info(f"✅ AthenaModel сохранена: {save_path}")

        imp = pd.Series(final.feature_importances_, index=X.columns).sort_values(ascending=False)
        logger.info(f"🔝 Топ-10 признаков:\n{imp.head(10)}")
        return final
