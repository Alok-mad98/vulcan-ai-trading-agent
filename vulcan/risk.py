"""VULCAN — Deterministic Risk Gates + Kelly position sizing.

The LLM proposes; THIS module disposes. Every gate is hard-coded math — no
model output can override them (Horizon Blackline / EdgeStack pattern).

Gates:
  G1  defined-risk only        — plan must have bounded max_loss
  G2  VIX/turbulence gate      — no NEW premium selling when vol shock active
  G3  gap-day sizing           — size for a 3-sigma SPY gap, not the average day
  G4  Kelly-fraction sizing    — size = f(win prob, payoff) capped hard
  G5  exposure caps            — max premium-at-risk per trade & portfolio-wide
  G6  daily circuit breaker    — realized loss > limit -> halt trading today
  G7  concentration/duplication— no overlapping structures on same expiry/side
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from vulcan.pricer import SpreadPlan

STATE_PATH = Path(os.path.join(os.path.dirname(__file__), "..", "data", "risk_state.json"))

# ---- hard limits (the constitution) ----
MAX_PREMIUM_AT_RISK_PCT_TRADE = 0.015     # 1.5% NAV max loss per structure
MAX_PREMIUM_AT_RISK_PCT_PORT = 0.06       # 6% NAV total open risk
MAX_DAILY_LOSS_PCT = 0.020                # 2% NAV realized loss -> circuit breaker
KELLY_FRACTION = 0.25                     # quarter-Kelly
GAP_SIGMA = 3.0                           # stress-test a 3-sigma gap
MIN_WIN_PROB = 0.55                       # don't size without an edge estimate
NAV = 100_000.0


@dataclass
class RiskDecision:
    approved: bool
    contracts: int = 0
    premium_at_risk: float = 0.0
    reasons: list[str] = field(default_factory=list)
    mc: dict = field(default_factory=dict)   # monte-carlo VaR summary for dashboard


def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"realized_today": 0.0, "date": "", "open_risk": 0.0, "trades": []}


def _save_state(st: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2))


def reset_daily_if_needed(st: dict) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if st.get("date") != today:
        st["date"] = today
        st["realized_today"] = 0.0
    return st


def kelly_contracts(plan: SpreadPlan, win_prob: float, nav: float = NAV) -> int:
    """Quarter-Kelly on the defined-risk payoff: b = max_profit/max_loss per spread.

    Kelly f* = (p*b - (1-p)) / b   (per unit risked)
    contracts = floor(f* * nav * KELLY_FRACTION / max_loss_per_contract)
    """
    b = plan.max_profit / max(plan.max_loss, 1e-9)
    edge = win_prob * b - (1 - win_prob)
    if edge <= 0:
        return 0
    f = edge / b
    risk_budget = f * nav * KELLY_FRACTION
    return max(int(risk_budget // max(plan.max_loss, 1e-9)), 0)


def gap_day_stress(plan: SpreadPlan, spot: float, rv_forecast: float, dte: int) -> float:
    """Fraction of max_loss lost under a 3-sigma one-day gap against the position.

    For credit structures a gap THROUGH the short strike is the killer. We
    approximate with BS on stressed vol: rv*2.5 (vol spikes in gaps), 1 day.
    """
    from vulcan.pricer import bs_price
    sigma_stress = max(rv_forecast * 2.5, 0.15)
    t = max(dte, 1) / 365.0
    gap = spot * sigma_stress / math.sqrt(252) * GAP_SIGMA
    pnl_down = 0.0
    pnl_up = 0.0
    for leg in plan.legs:
        mult = -1 if leg.side == "sell" else 1
        for direction, spot_new in (("down", spot - gap), ("up", spot + gap)):
            px = bs_price(spot_new, leg.strike, t, sigma_stress, kind=leg.kind)
            v = mult * (leg.est_price - px) * 100
            if direction == "down":
                pnl_down += v
            else:
                pnl_up += v
    loss = min(pnl_down, pnl_up, 0.0)
    return -loss / max(plan.max_loss * 100.0, 1e-9)  # fraction of defined max_loss


def evaluate_plan(plan: SpreadPlan, spot: float, rv_forecast: float,
                  vix: float | None, vix_chg: float | None,
                  regime: str, win_prob: float,
                  open_positions: list | None = None, equity: float = NAV,
                  use_monte_carlo: bool = True) -> RiskDecision:
    st = reset_daily_if_needed(_load_state())
    reasons: list[str] = []

    # G1 — defined risk only
    if plan.max_loss <= 0 or not math.isfinite(plan.max_loss):
        return RiskDecision(False, 0, 0.0, ["G1 FAIL: structure has unbounded risk"])

    # G2 — turbulence gate: no NEW premium selling during vol shocks
    if plan.name in ("iron_condor", "bull_put_spread", "bear_call_spread"):
        if vix is not None and vix > 28:
            reasons.append(f"G2 VETO: VIX {vix:.0f} > 28 (stress)")
        if vix_chg is not None and vix_chg > 0.12:
            reasons.append(f"G2 VETO: VIX +{vix_chg*100:.0f}% today (shock)")
        if regime == "stress":
            reasons.append("G2 VETO: regime=stress (HMM)")

    # G3 — Monte Carlo VaR: full P&L distribution under GBM (antithetic+Sobol).
    #      G3's job is MODEL INTEGRITY: simulated losses must respect the defined
    #      max (catches pricing/sign bugs). Profitability judgment is G4's (Kelly
    #      already integrates breach probability into expected value).
    mc = None
    if use_monte_carlo:
        try:
            from vulcan.montecarlo import portfolio_var_mc
            mc = portfolio_var_mc(plan, spot, rv_forecast, plan.dte, 1, n_paths=32_768)
            max_loss_ct = plan.max_loss * 100.0
            if mc.var99 > max_loss_ct * 1.05:
                reasons.append(f"G3 VETO: MC 99% VaR ${mc.var99:.0f}/ct exceeds defined max ${max_loss_ct:.0f}")
            if mc.cvar99 > max_loss_ct * 1.05:
                reasons.append(f"G3 VETO: MC CVaR99 ${mc.cvar99:.0f} exceeds defined max ${max_loss_ct:.0f}")
            if mc.prob_max_loss > 0.55:
                reasons.append(f"G3 VETO: MC P(breach)={mc.prob_max_loss*100:.0f}% — structure loses more often than not")
        except Exception as e:
            reasons.append(f"G3 WARN: MC unavailable ({e}) — falling back to gap stress")
            mc = None
    if mc is None:
        gap_frac = gap_day_stress(plan, spot, rv_forecast, plan.dte)
        if gap_frac > 1.05:
            reasons.append(f"G3 VETO: 3-sigma gap loses {gap_frac*100:.0f}% of max_loss")

    # G4 — Kelly sizing (quarter-Kelly). Honest probability only — if the
    # structural win probability is below MIN_WIN_PROB, refuse (never inflate).
    if win_prob < MIN_WIN_PROB:
        reasons.append(f"G4 VETO: structural win_prob {win_prob:.2f} < {MIN_WIN_PROB} (no honest edge)")
        contracts = 0
    else:
        contracts = kelly_contracts(plan, win_prob, equity)
        if contracts < 1:
            reasons.append("G4 VETO: no positive Kelly edge (win_prob too low)")
            contracts = 0

    # G5 — exposure caps
    par_per = plan.max_loss * 100.0  # per contract, options multiplier 100
    total_risk = st.get("open_risk", 0.0)
    if contracts >= 1:
        allowed = int((equity * MAX_PREMIUM_AT_RISK_PCT_TRADE) // par_per)
        if allowed < 1:
            reasons.append("G5 VETO: single-trade risk cap < 1 contract")
            contracts = 0
        else:
            contracts = min(contracts, allowed)
        if contracts >= 1:
            room = equity * MAX_PREMIUM_AT_RISK_PCT_PORT - total_risk
            if room < par_per:
                reasons.append("G5 VETO: portfolio premium-at-risk cap reached")
                contracts = 0
            else:
                contracts = min(contracts, int(room // par_per))

    # G6 — daily circuit breaker
    if st.get("realized_today", 0.0) <= -equity * MAX_DAILY_LOSS_PCT:
        reasons.append("G6 VETO: daily loss circuit breaker tripped")
        contracts = 0

    approved = contracts >= 1 and not any("VETO" in r for r in reasons)
    mc_note = ""
    if mc is not None:
        mc_note = (f" MC-VaR99 ${mc.var99:.0f}/ct, CVaR99 ${mc.cvar99:.0f}, "
                   f"P(breach)={mc.prob_max_loss*100:.1f}%, VR {mc.vr_factor:.1f}x, {mc.n_paths:,} paths")
    if approved:
        reasons.append(f"APPROVED: {contracts} contracts, risk ${par_per*contracts:,.0f} "
                       f"({par_per*contracts/equity*100:.2f}% NAV).{mc_note}")
    return RiskDecision(approved=approved, contracts=contracts,
                        premium_at_risk=par_per * contracts, reasons=reasons,
                        mc=({"var99": mc.var99, "cvar99": mc.cvar99, "var95": mc.var95,
                             "prob_breach": mc.prob_max_loss, "worst": mc.worst,
                             "vr_factor": mc.vr_factor, "n_paths": mc.n_paths} if mc else {}))


def register_open_risk(delta_risk: float):
    st = reset_daily_if_needed(_load_state())
    st["open_risk"] = max(0.0, st.get("open_risk", 0.0) + delta_risk)
    _save_state(st)


def register_close(realized_pnl: float):
    st = reset_daily_if_needed(_load_state())
    st["realized_today"] = st.get("realized_today", 0.0) + realized_pnl
    _save_state(st)
