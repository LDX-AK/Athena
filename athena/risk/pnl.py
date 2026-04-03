"""PnL helpers for risk and monitoring telemetry."""


def calc_unrealized_pnl(router, current_prices: dict) -> float:
    """Estimate unrealized PnL for open paper positions."""
    total = 0.0
    commission_rate = float(getattr(router, "commission_rate", 0.0) or 0.0)

    for pos in getattr(router, "paper_positions", {}).values():
        entry = float(pos.get("entry", 0.0) or 0.0)
        if entry <= 0.0:
            continue

        symbol = pos.get("symbol", "")
        mark_price = float(current_prices.get(symbol, entry))
        direction = int(pos.get("direction", 0) or 0)
        size_usd = float(pos.get("size_usd", 0.0) or 0.0)

        gross_pnl = ((mark_price - entry) / entry) * size_usd * direction
        est_close_commission = size_usd * commission_rate
        open_commission = float(pos.get("commission", 0.0) or 0.0)
        total += gross_pnl - est_close_commission - open_commission

    return total
