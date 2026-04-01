"""
athena/execution/router.py — AthenaRouter
"""

import asyncio
import time
import logging
from typing import Dict, Optional
import ccxt.pro as ccxtpro
from athena.model.signal import AthenaSignal

logger = logging.getLogger("athena.execution")


class AthenaRouter:
    def __init__(self, exchanges: Dict, mode: str = "paper"):
        self.mode = mode
        self.exchanges = {}
        for name, creds in exchanges.items():
            cls = getattr(ccxtpro, name)
            self.exchanges[name] = cls(creds)

        self.paper_positions: Dict[str, Dict] = {}
        self.paper_balance   = 10_000.0
        self.commission_rate = 0.0004   # 0.04% taker

        logger.info(f"🔧 AthenaRouter | режим: {mode.upper()}")

    async def execute(self, signal: AthenaSignal, size_usd: float,
                      sl: float, tp: float) -> Dict:
        if self.mode == "paper":
            return await self._paper_open(signal, size_usd, sl, tp)
        return await self._live_open(signal, size_usd, sl, tp)

    # ── PAPER ──────────────────────────────────────────────────

    async def _paper_open(self, signal: AthenaSignal, size_usd: float,
                           sl: float, tp: float) -> Dict:
        slip  = 0.0001
        price = signal.price * (1 + slip if signal.direction == 1 else 1 - slip)
        comm  = size_usd * self.commission_rate
        self.paper_balance -= comm

        key = f"{signal.exchange}:{signal.symbol}"
        self.paper_positions[key] = {
            "symbol":    signal.symbol,
            "exchange":  signal.exchange,
            "direction": signal.direction,
            "entry":     price,
            "size_usd":  size_usd,
            "sl": sl, "tp": tp,
            "open_time": time.time(),
            "commission": comm,
        }

        label = "LONG" if signal.direction == 1 else "SHORT"
        logger.info(f"📝 [PAPER] {label} {signal.symbol} @ {price:.4f} "
                    f"SL={sl:.4f} TP={tp:.4f} ${size_usd:.2f}")
        return {"status": "paper_opened", "symbol": signal.symbol,
                "direction": signal.direction, "entry_price": price,
                "size_usd": size_usd, "pnl": 0.0}

    async def close_paper_position(self, symbol: str, exchange: str,
                                    current_price: float) -> Optional[Dict]:
        key = f"{exchange}:{symbol}"
        pos = self.paper_positions.pop(key, None)
        if not pos:
            return None

        comm = pos["size_usd"] * self.commission_rate
        pnl  = ((current_price - pos["entry"]) / pos["entry"]
                 * pos["size_usd"] * pos["direction"])
        pnl -= comm + pos["commission"]
        self.paper_balance += pnl

        label = "LONG" if pos["direction"] == 1 else "SHORT"
        logger.info(f"📝 [PAPER] Закрыт {label} {symbol} "
                    f"PnL=${pnl:.2f} | Баланс=${self.paper_balance:.2f}")
        return {"status": "paper_closed", "symbol": symbol,
                "entry_price": pos["entry"], "exit_price": current_price,
                "pnl": pnl, "balance": self.paper_balance}

    # ── LIVE ───────────────────────────────────────────────────

    async def _live_open(self, signal: AthenaSignal, size_usd: float,
                          sl: float, tp: float) -> Dict:
        exchange = self.exchanges.get(signal.exchange)
        if not exchange:
            raise ValueError(f"Биржа {signal.exchange} не инициализирована")

        amount = exchange.amount_to_precision(
            signal.symbol, size_usd / signal.price
        )
        side = "buy" if signal.direction == 1 else "sell"

        # Пробуем limit → fallback market
        try:
            lp    = signal.price * (0.9999 if signal.direction == 1 else 1.0001)
            lp    = exchange.price_to_precision(signal.symbol, lp)
            order = await exchange.create_order(signal.symbol, "limit", side, amount, lp,
                                                params={"timeInForce": "GTC"})
            oid   = order["id"]
            filled = await self._wait_fill(exchange, signal.symbol, oid, timeout=5.0)
            if not filled:
                await exchange.cancel_order(oid, signal.symbol)
                order = await exchange.create_market_order(signal.symbol, side, amount)
        except Exception as e:
            logger.error(f"Ошибка ордера: {e}")
            raise

        await self._set_sl_tp(exchange, signal, amount, sl, tp)

        entry = float(order.get("average", signal.price))
        logger.info(f"✅ [LIVE] {side.upper()} {signal.symbol} @ {entry:.4f}")
        return {"status": "opened", "symbol": signal.symbol,
                "direction": signal.direction, "entry_price": entry,
                "size_usd": size_usd, "pnl": 0.0}

    async def _wait_fill(self, exchange, symbol, order_id, timeout=5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            o = await exchange.fetch_order(order_id, symbol)
            if o["status"] == "closed":
                return True
            await asyncio.sleep(0.5)
        return False

    async def _set_sl_tp(self, exchange, signal: AthenaSignal, amount, sl, tp):
        opp = "sell" if signal.direction == 1 else "buy"
        try:
            await exchange.create_order(signal.symbol, "oco", opp, amount,
                                        exchange.price_to_precision(signal.symbol, tp),
                                        params={"stopPrice": exchange.price_to_precision(signal.symbol, sl)})
        except Exception:
            try:
                await exchange.create_limit_order(signal.symbol, opp, amount, tp)
                await exchange.create_order(signal.symbol, "stop_market", opp, amount,
                                            params={"stopPrice": sl})
            except Exception as e:
                logger.error(f"⚠️  SL/TP не выставлен: {e}")
