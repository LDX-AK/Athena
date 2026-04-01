"""
athena/monitor/dashboard.py — консольный дашборд Athena
"""

import time
import logging
from typing import Dict
from athena.risk.manager import AthenaRisk

logger = logging.getLogger("athena.monitor")


class AthenaDashboard:
    def __init__(self, risk: AthenaRisk, print_every: int = 10):
        self.risk        = risk
        self.print_every = print_every   # выводим статистику каждые N сделок
        self._count      = 0
        self._start_time = time.time()

    def update(self, result: Dict):
        self._count += 1
        if self._count % self.print_every == 0:
            self._print_stats()

    def _print_stats(self):
        s       = self.risk.stats()
        uptime  = (time.time() - self._start_time) / 3600

        print("\n" + "━" * 52)
        print("  ⚡ ATHENA AI-BOT  |  Live Dashboard")
        print("━" * 52)
        print(f"  Uptime:          {uptime:.1f}h")
        print(f"  Баланс:          ${s['balance']:>10.2f}")
        print(f"  Дневной PnL:     ${s['daily_pnl']:>+10.2f}")
        print(f"  Всего PnL:       ${s['total_pnl']:>+10.2f}")
        print(f"  Сделок:          {s['total_trades']}")
        print(f"  Win Rate:        {s['win_rate']*100:.1f}%")
        print(f"  Avg Win:         ${s['avg_win']:.2f}")
        print(f"  Avg Loss:        ${s['avg_loss']:.2f}")
        print(f"  Открытых поз.:   {s['open_positions']}")
        print("━" * 52 + "\n")
