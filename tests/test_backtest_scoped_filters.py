import copy
import time
import unittest

from athena.backtest.runner import AthenaBacktest
from athena.config import ATHENA_CONFIG
from athena.model.signal import AthenaSignal


class StaticEngineer:
    windows = [5]

    def __init__(
        self,
        vol_regime: float = 0.5,
        session_asia: float = 0.0,
        session_europe: float = 1.0,
        session_us: float = 0.0,
        session_overlap: float = 0.0,
        is_weekend: float = 0.0,
    ):
        self.vol_regime = vol_regime
        self.session_asia = session_asia
        self.session_europe = session_europe
        self.session_us = session_us
        self.session_overlap = session_overlap
        self.is_weekend = is_weekend

    def transform(self, batch):
        last_price = float(batch["ohlcv"][-1][4])
        return {
            "vol_regime": self.vol_regime,
            "session_asia": self.session_asia,
            "session_europe": self.session_europe,
            "session_us": self.session_us,
            "session_overlap": self.session_overlap,
            "is_weekend": self.is_weekend,
            "hour_bucket": 2,
            "_symbol": batch.get("symbol", "BTC/USDT"),
            "_exchange": batch.get("exchange", "binance"),
            "_last_price": last_price,
        }


class StaticSentiment:
    def get_historical(self, symbol, ts):
        return {}


class TestBacktestScopedFilters(unittest.TestCase):
    def _ohlcv(self, rows: int = 80):
        now_ms = int(time.time() * 1000)
        data = []
        price = 100.0
        for i in range(rows):
            open_ = price
            close = open_ * (0.998 if i % 2 == 0 else 1.001)
            high = max(open_, close) * 1.004
            low = min(open_, close) * 0.996
            volume = 1000 + i
            data.append([now_ms - (rows - i) * 900_000, open_, high, low, close, volume])
            price = close
        return data

    def _cfg(self):
        cfg = copy.deepcopy(ATHENA_CONFIG)
        cfg["model_path"] = "none"
        cfg["flags"]["SENTIMENT_ENABLED"] = False
        cfg["flags"]["SENTIMENT_BACKTEST"] = False
        cfg["flags"]["MTF_FILTER_ENABLED"] = False
        cfg["risk"].update(
            {
                "min_confidence": 0.10,
                "stop_loss_pct": 0.001,
                "take_profit_pct": 0.001,
                "max_position_pct": 0.01,
            }
        )
        cfg.setdefault("data", {})["lookback_candles"] = 20
        return cfg

    def test_direction_filter_can_block_long_entries(self):
        cfg = self._cfg()
        cfg.setdefault("experiment", {})["direction_filter"] = "short"
        backtest = AthenaBacktest(StaticEngineer(vol_regime=0.5), StaticSentiment(), cfg)
        backtest.fusion.predict = lambda features, sentiment=None: AthenaSignal(
            direction=1,
            confidence=0.90,
            symbol="BTC/USDT",
            exchange="binance",
            price=float(features["_last_price"]),
            features=features,
        )
        backtest.mtf_gate.allow_signal = lambda ohlcv, direction: (True, "ok")

        result = backtest.run(self._ohlcv(), initial_balance=10_000.0, symbol="BTC/USDT")
        self.assertEqual(result, {})

    def test_regime_filter_can_block_non_matching_regimes(self):
        cfg = self._cfg()
        cfg.setdefault("experiment", {})["regime_filter"] = "hot"
        backtest = AthenaBacktest(StaticEngineer(vol_regime=0.5), StaticSentiment(), cfg)
        backtest.fusion.predict = lambda features, sentiment=None: AthenaSignal(
            direction=-1,
            confidence=0.90,
            symbol="BTC/USDT",
            exchange="binance",
            price=float(features["_last_price"]),
            features=features,
        )
        backtest.mtf_gate.allow_signal = lambda ohlcv, direction: (True, "ok")

        result = backtest.run(self._ohlcv(), initial_balance=10_000.0, symbol="BTC/USDT")
        self.assertEqual(result, {})

    def test_meta_filter_can_block_disallowed_hour_entries(self):
        data = self._ohlcv()
        current_hour = time.gmtime(data[-1][0] / 1000).tm_hour
        blocked_hour = (current_hour + 1) % 24

        cfg = self._cfg()
        cfg.setdefault("experiment", {})["meta_filter"] = {"allowed_hours": [blocked_hour]}
        backtest = AthenaBacktest(StaticEngineer(vol_regime=0.5), StaticSentiment(), cfg)
        backtest.fusion.predict = lambda features, sentiment=None: AthenaSignal(
            direction=-1,
            confidence=0.55,
            symbol="BTC/USDT",
            exchange="binance",
            price=float(features["_last_price"]),
            features=features,
        )
        backtest.mtf_gate.allow_signal = lambda ohlcv, direction: (True, "ok")

        result = backtest.run(data, initial_balance=10_000.0, symbol="BTC/USDT")
        self.assertEqual(result, {})

    def test_meta_filter_can_cap_overconfident_signals(self):
        cfg = self._cfg()
        cfg.setdefault("experiment", {})["meta_filter"] = {"max_confidence": 0.60}
        backtest = AthenaBacktest(StaticEngineer(vol_regime=0.5), StaticSentiment(), cfg)
        backtest.fusion.predict = lambda features, sentiment=None: AthenaSignal(
            direction=-1,
            confidence=0.90,
            symbol="BTC/USDT",
            exchange="binance",
            price=float(features["_last_price"]),
            features=features,
        )
        backtest.mtf_gate.allow_signal = lambda ohlcv, direction: (True, "ok")

        result = backtest.run(self._ohlcv(), initial_balance=10_000.0, symbol="BTC/USDT")
        self.assertEqual(result, {})

    def test_router_no_trade_only_blocks_when_enabled(self):
        base_engineer = StaticEngineer(
            vol_regime=0.10,
            session_asia=1.0,
            session_europe=0.0,
            session_us=0.0,
            session_overlap=0.0,
            is_weekend=0.0,
        )

        cfg_disabled = self._cfg()
        cfg_disabled.setdefault("router", {})["enabled"] = False
        backtest_disabled = AthenaBacktest(base_engineer, StaticSentiment(), cfg_disabled)
        backtest_disabled.fusion.predict = lambda features, sentiment=None: AthenaSignal(
            direction=-1,
            confidence=0.90,
            symbol="BTC/USDT",
            exchange="binance",
            price=float(features["_last_price"]),
            features=features,
        )
        backtest_disabled.mtf_gate.allow_signal = lambda ohlcv, direction: (True, "ok")

        allowed = backtest_disabled.run(self._ohlcv(), initial_balance=10_000.0, symbol="BTC/USDT")
        self.assertNotEqual(allowed, {})

        cfg_enabled = self._cfg()
        cfg_enabled.setdefault("router", {})["enabled"] = True
        backtest_enabled = AthenaBacktest(base_engineer, StaticSentiment(), cfg_enabled)
        backtest_enabled.fusion.predict = lambda features, sentiment=None: AthenaSignal(
            direction=-1,
            confidence=0.90,
            symbol="BTC/USDT",
            exchange="binance",
            price=float(features["_last_price"]),
            features=features,
        )
        backtest_enabled.mtf_gate.allow_signal = lambda ohlcv, direction: (True, "ok")

        blocked = backtest_enabled.run(self._ohlcv(), initial_balance=10_000.0, symbol="BTC/USDT")
        self.assertEqual(blocked, {})


if __name__ == "__main__":
    unittest.main()
