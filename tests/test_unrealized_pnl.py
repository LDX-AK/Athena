import unittest

from athena.risk.pnl import calc_unrealized_pnl


class DummyRouter:
    def __init__(self, positions, commission_rate=0.0004):
        self.paper_positions = positions
        self.commission_rate = commission_rate


class TestUnrealizedPnl(unittest.TestCase):
    def test_long_profit(self):
        router = DummyRouter(
            {
                "b:BTC/USDT": {
                    "symbol": "BTC/USDT",
                    "entry": 100.0,
                    "direction": 1,
                    "size_usd": 1000.0,
                    "commission": 0.4,
                }
            }
        )
        pnl = calc_unrealized_pnl(router, {"BTC/USDT": 110.0})
        self.assertAlmostEqual(pnl, 99.2, places=6)

    def test_long_loss(self):
        router = DummyRouter(
            {
                "b:BTC/USDT": {
                    "symbol": "BTC/USDT",
                    "entry": 100.0,
                    "direction": 1,
                    "size_usd": 1000.0,
                    "commission": 0.4,
                }
            }
        )
        pnl = calc_unrealized_pnl(router, {"BTC/USDT": 95.0})
        self.assertAlmostEqual(pnl, -50.8, places=6)

    def test_short_profit(self):
        router = DummyRouter(
            {
                "b:ETH/USDT": {
                    "symbol": "ETH/USDT",
                    "entry": 200.0,
                    "direction": -1,
                    "size_usd": 1000.0,
                    "commission": 0.4,
                }
            }
        )
        pnl = calc_unrealized_pnl(router, {"ETH/USDT": 180.0})
        self.assertAlmostEqual(pnl, 99.2, places=6)

    def test_fallback_to_entry_when_price_missing(self):
        router = DummyRouter(
            {
                "b:SOL/USDT": {
                    "symbol": "SOL/USDT",
                    "entry": 50.0,
                    "direction": 1,
                    "size_usd": 500.0,
                    "commission": 0.2,
                }
            }
        )
        pnl = calc_unrealized_pnl(router, {})
        self.assertAlmostEqual(pnl, -0.4, places=6)

    def test_multiple_positions_are_summed(self):
        router = DummyRouter(
            {
                "b:BTC/USDT": {
                    "symbol": "BTC/USDT",
                    "entry": 100.0,
                    "direction": 1,
                    "size_usd": 1000.0,
                    "commission": 0.4,
                },
                "b:ETH/USDT": {
                    "symbol": "ETH/USDT",
                    "entry": 200.0,
                    "direction": -1,
                    "size_usd": 500.0,
                    "commission": 0.2,
                },
            }
        )
        pnl = calc_unrealized_pnl(
            router,
            {
                "BTC/USDT": 105.0,
                "ETH/USDT": 190.0,
            },
        )
        self.assertAlmostEqual(pnl, 73.8, places=6)

    def test_invalid_entry_is_ignored(self):
        router = DummyRouter(
            {
                "x:BAD": {
                    "symbol": "BAD",
                    "entry": 0.0,
                    "direction": 1,
                    "size_usd": 1000.0,
                    "commission": 0.4,
                }
            }
        )
        pnl = calc_unrealized_pnl(router, {"BAD": 200.0})
        self.assertEqual(pnl, 0.0)


if __name__ == "__main__":
    unittest.main()
