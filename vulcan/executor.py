"""VULCAN — Alpaca executor. Multi-leg (mleg) options orders + position monitor."""
from __future__ import annotations

from vulcan import data as d
from vulcan.pricer import SpreadPlan


def submit_spread(plan: SpreadPlan, contracts: int, limit_slippage: float = 0.05) -> dict:
    """Submit a defined-risk spread as one mleg order.

    Net price convention: positive limit = max debit paid; negative = min credit received.
    We cross the mid by `limit_slippage` to improve fill odds.
    """
    legs = []
    for leg in plan.legs:
        legs.append({
            "symbol": leg.symbol,
            "ratio_qty": 1,
            "side": "buy" if leg.side == "buy" else "sell",
        })
    net_mid = -plan.credit  # credit positive plan => net mid negative (we receive)
    # buying power effect sign: we want worst-case for us:
    #   credit spread: receive credit - slippage => limit_price = -(credit - slippage)
    #   debit spread : pay debit + slippage      => limit_price = +(debit + slippage)
    if plan.credit >= 0:
        limit_price = -(plan.credit - limit_slippage)
    else:
        limit_price = -plan.credit + limit_slippage  # debit = -credit

    order = {
        "order_class": "mleg",
        "qty": str(contracts),
        "type": "limit",          # REST field is "type" (NOT order_type)
        "time_in_force": "day",
        "limit_price": round(limit_price, 2),
        "legs": legs,
    }
    return d.submit_order(order)


def close_position_legs(position: dict) -> dict | None:
    """Close an existing option position (single leg fallback)."""
    sym = position["symbol"]
    qty = abs(int(float(position["qty"])))
    side = "buy" if float(position["qty"]) < 0 else "sell"
    return d.submit_order({
        "symbol": sym, "qty": str(qty), "side": side,
        "type": "market", "time_in_force": "day",
    })


def position_pnl(position: dict) -> dict:
    """Summarize an option position: unrealized P&L, premium at risk."""
    qty = float(position.get("qty", 0))
    avg = float(position.get("avg_entry_price", 0) or 0)
    cur = float(position.get("current_price", 0) or 0)
    mval = float(position.get("market_value", 0) or 0)
    return {"symbol": position.get("symbol"), "qty": qty,
            "avg_entry": avg, "current": cur,
            "unrealized": float(position.get("unrealized_pl", 0) or 0),
            "market_value": mval}
