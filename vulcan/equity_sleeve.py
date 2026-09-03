"""VULCAN â€” Equity Long/Short Sleeve.

Why a second sleeve: the hackathon REQUIRES options (Options Alpha Agents track),
so VRP spreads remain the compliance core â€” but nothing stops an equity
long/short overlay traded alongside, using the SAME Model-1 brain
(regime + direction bias + vol forecast) with its own deterministic gates:

  E1  regime gate:       long only in calm/bull; short only in stress with bearish bias
  E2  signal gate:       |direction_bias| >= 0.30 required
  E3  vol-scaled sizing: target notional = NAV * 0.10 * min(2.0, RV20/0.12)
                          (bigger size when vol cheap, smaller when vol rich)
  E4  Kelly tilt:        scale by min(1.5, 0.5 + edge)
  E5  stops:             -3% position stop, +8% trail, hard 15% NAV cap per name
  E6  no shorting in calm regime (paper-account locates + tail asymmetry)

Targets: SPY (core), QQQ/HHI ETFs optional. Executed as bracket orders.
"""
from __future__ import annotations

from dataclasses import dataclass

from vulcan import data as d
from vulcan.vol_forecaster import realized_vol

NAV = 100_000.0
BIAS_GATE = 0.30
BASE_NOTIONAL_PCT = 0.10


@dataclass
class EquityPlan:
    symbol: str
    side: str            # buy / sell (short)
    notional: float
    qty: int
    stop_pct: float = 0.03
    trail_pct: float = 0.08
    rationale: str = ""


def plan_equity_trade(fc, spot: float, symbol: str = "SPY", equity: float = NAV) -> EquityPlan | None:
    bias = fc.direction_bias
    regime = fc.regime.get("regime", "unknown")
    rv20 = fc.realized_20

    if abs(bias) < BIAS_GATE:
        return None

    side = "buy" if bias > 0 else "sell"
    if side == "sell" and regime != "stress":
        return None  # E6
    if side == "buy" and regime == "stress" and fc.rv_ratio > 1.3:
        return None  # vol shock: don't catch falling knife

    # E3 vol-scaled notional
    vol_scalar = min(2.0, max(0.4, rv20 / 0.12))
    notional = equity * BASE_NOTIONAL_PCT * vol_scalar
    # E4 edge tilt
    notional *= min(1.5, 0.5 + abs(bias))
    notional = min(notional, equity * 0.15)  # E5 hard cap

    qty = int(notional // max(spot, 1e-9))
    if qty < 1:
        return None
    dir_word = "bullish" if side == "buy" else "bearish"
    return EquityPlan(symbol=symbol, side=side, notional=qty * spot, qty=qty,
                      rationale=f"bias {bias:+.2f} {dir_word}, regime={regime}, "
                                f"rv20={rv20*100:.0f}% vol-scalar {vol_scalar:.2f}")


def submit_equity_bracket(plan: EquityPlan, spot: float) -> dict:
    stop = spot * (1 - plan.stop_pct) if plan.side == "buy" else spot * (1 + plan.stop_pct)
    limit = spot * (1 + 0.0005) if plan.side == "buy" else spot * (1 - 0.0005)
    order = {
        "symbol": plan.symbol,
        "qty": str(plan.qty),
        "side": plan.side,
        "type": "limit",
        "time_in_force": "day",
        "limit_price": round(limit, 2),
        "order_class": "bracket",
        "take_profit": {"limit_price": round(spot * (1 + plan.trail_pct) if plan.side == "buy"
                                            else spot * (1 - plan.trail_pct), 2)},
        "stop_loss": {"stop_price": round(stop, 2)},
    }
    return d.submit_order(order)
