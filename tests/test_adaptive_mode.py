import time
import types
import unittest

from athena.config import ATHENA_CONFIG
from athena.risk.adaptive_mode import AdaptiveModeController, TradingMode


class TestAdaptiveModeController(unittest.TestCase):
    def _config(self):
        cfg = dict(ATHENA_CONFIG)
        cfg["adaptive_mode"] = {
            "enabled": True,
            "update_interval_bars": 1,
            "hysteresis_bars": 10,
            "market_regime": {
                "enabled": True,
                "timeframes": ["1h"],
                "weights": {"1h": 1.0},
                "trend_threshold": 0.001,
                "volatility_threshold": 0.02,
            },
            "self_health": {
                "enabled": True,
                "window_trades": 5,
                "min_win_rate": 0.35,
                "min_profit_factor": 0.8,
                "min_sharpe": -0.2,
            },
            "modes": {
                "defensive": {
                    "max_position_pct": 0.005,
                    "min_confidence": 0.65,
                    "kelly_fraction": 0.10,
                    "max_open_positions": 1,
                    "cooldown_after_loss_sec": 600,
                },
                "conservative": {
                    "max_position_pct": 0.01,
                    "min_confidence": 0.55,
                    "kelly_fraction": 0.15,
                    "max_open_positions": 2,
                    "cooldown_after_loss_sec": 300,
                },
                "aggressive": {
                    "max_position_pct": 0.02,
                    "min_confidence": 0.45,
                    "kelly_fraction": 0.25,
                    "max_open_positions": 3,
                    "cooldown_after_loss_sec": 150,
                },
            },
        }
        cfg["timeframe"] = "15m"
        cfg["runtime_timeframe"] = "15m"
        return cfg

    def _ohlcv(self, drift_per_candle: float, count: int = 80):
        now_ms = int(time.time() * 1000)
        out = []
        price = 100.0
        for i in range(count):
            open_ = price
            close = open_ * (1.0 + drift_per_candle)
            high = max(open_, close) * 1.0005
            low = min(open_, close) * 0.9995
            volume = 1000.0 + i
            out.append([now_ms - (count - i) * 900_000, open_, high, low, close, volume])
            price = close
        return out

    def test_hysteresis_prevents_fast_mode_flapping(self):
        controller = AdaptiveModeController(self._config())

        uptrend = self._ohlcv(0.003, count=80)
        first = controller.update(0, {"ohlcv": uptrend, "recent_trades": []})
        self.assertEqual(first, TradingMode.AGGRESSIVE)
        self.assertEqual(controller.current_mode, TradingMode.AGGRESSIVE)

        flat = self._ohlcv(0.0, count=80)
        blocked = controller.update(5, {"ohlcv": flat, "recent_trades": []})
        self.assertIsNone(blocked)
        self.assertEqual(controller.current_mode, TradingMode.AGGRESSIVE)

        switched = controller.update(12, {"ohlcv": flat, "recent_trades": []})
        self.assertEqual(switched, TradingMode.DEFENSIVE)
        self.assertEqual(controller.current_mode, TradingMode.DEFENSIVE)

    def test_self_health_only_downgrades(self):
        controller = AdaptiveModeController(self._config())
        uptrend = self._ohlcv(0.003, count=80)
        bad_trades = [{"pnl": -10.0} for _ in range(5)]

        mode = controller.update(12, {"ohlcv": uptrend, "recent_trades": bad_trades})
        self.assertEqual(mode, TradingMode.DEFENSIVE)
        self.assertEqual(controller.current_mode, TradingMode.DEFENSIVE)

    def test_incomplete_higher_tf_chunk_is_ignored(self):
        controller = AdaptiveModeController(self._config())
        ohlcv = self._ohlcv(0.003, count=35)

        for row in ohlcv[-3:]:
            row[1] *= 0.70
            row[2] *= 0.72
            row[3] *= 0.68
            row[4] *= 0.69

        mode = controller.update(0, {"ohlcv": ohlcv, "recent_trades": []})
        self.assertEqual(mode, TradingMode.AGGRESSIVE)

    def test_mode_switch_updates_risk_proxy(self):
        controller = AdaptiveModeController(self._config())
        risk_proxy = types.SimpleNamespace(
            cfg={
                "max_position_pct": 0.01,
                "min_confidence": 0.55,
                "max_open_positions": 2,
                "cooldown_after_loss_sec": 300,
                "kelly_fraction": 0.15,
            },
            kelly_fraction=0.15,
        )
        controller.set_risk_manager(risk_proxy)

        uptrend = self._ohlcv(0.003, count=80)
        controller.update(0, {"ohlcv": uptrend, "recent_trades": []})

        self.assertAlmostEqual(risk_proxy.cfg["max_position_pct"], 0.02)
        self.assertAlmostEqual(risk_proxy.cfg["min_confidence"], 0.45)
        self.assertEqual(risk_proxy.cfg["max_open_positions"], 3)
        self.assertEqual(risk_proxy.cfg["cooldown_after_loss_sec"], 150)
        self.assertAlmostEqual(risk_proxy.kelly_fraction, 0.25)


if __name__ == "__main__":
    unittest.main()
