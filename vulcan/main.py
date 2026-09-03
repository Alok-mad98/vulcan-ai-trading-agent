"""VULCAN ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Autonomous VRP Options Desk. Main orchestrator.

Run loop (cron-friendly, idempotent):
  1. Market-hours guard
  2. MODEL 1: vol forecast (HAR + GARCH + Kalman ensemble) + regime + direction
  3. MODEL 2: chain IV -> VRP signal -> spread plan
  4. MODEL 3: LLM agent debate -> verdict (veto/shrink only)
  5. RISK GATES: deterministic approval + Kelly sizing
  6. EXECUTE: mleg order (or DRY_RUN log)
  7. MANAGE: exits at 60% max profit / breach stop / expiry roll
  8. DASHBOARD: write data/dashboard.json

Usage:
  python -m vulcan.main            # one cycle (safe for cron)
  python -m vulcan.main --loop     # continuous every 15 min
  python -m vulcan.main --dry-run  # log trades, submit nothing
"""
from __future__ import annotations

import argparse
import json
import urllib.request
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from vulcan import data as d
from vulcan.vol_forecaster import forecast, realized_vol
from vulcan.pricer import extract_atm_iv, vrp_signal, build_spread_plan
from vulcan import risk as R
from vulcan.agent import run_agent
from vulcan.executor import submit_spread, position_pnl

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_PATH = DATA_DIR / "vulcan_state.json"
DASH_PATH = DATA_DIR / "dashboard.json"

EXIT_PROFIT_PCT = 0.60     # close at 60% of max profit (classic premium management)
BREACH_STOP_PCT = 0.75     # if loss >= 75% of defined max loss, cut
MIN_DTE_ROLL = 2           # roll anything inside 2 DTE

DASH_URL = os.getenv("VULCAN_DASH_URL", "https://vulcan-dashboard.arechampionw.workers.dev")


def push_to_dashboard(st: dict):
    """Push bot state + loop results to the Cloudflare dashboard KV."""
    try:
        token = open(Path(__file__).resolve().parent.parent / ".push_token").read().strip()
        loop_p = DATA_DIR / "loop_runs.json"
        body = {"state": {k: st.get(k) for k in
                          ("cycles", "last_forecast", "last_signal", "last_agent", "history", "status")},
                "loop": json.loads(loop_p.read_text()) if loop_p.exists() else {}}
        req = urllib.request.Request(f"{DASH_URL}/api/push?tok={token}",
                                     data=json.dumps(body, default=str).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "Mozilla/5.0 (VULCAN bot; paper-trading state push)")
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        print(f"dashboard push failed: {e}")


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"trades": [], "cycles": 0}


def save_state(st: dict):
    DATA_DIR.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2, default=str))


def market_open_now() -> bool:
    """Use /v2/clock (the account object has NO is_market_open field!)."""
    try:
        clock = d._get("https://paper-api.alpaca.markets/v2/clock")
        return bool(clock.get("is_open", False))
    except Exception:
        return False


def manage_positions(st: dict, dry: bool) -> list[str]:
    """Exit rules on open option positions. Returns log lines."""
    logs = []
    try:
        positions = [p for p in d.get_positions() if "P" in p["symbol"][-9:] or "C" in p["symbol"][-9:]]
    except Exception as e:
        return [f"positions fetch failed: {e}"]
    for pos in positions:
        info = position_pnl(pos)
        # find matching trade record for defined max
        rec = next((t for t in st["trades"] if t.get("status") == "open" and
                    any(l["symbol"] == info["symbol"] for l in t.get("legs", []))), None)
        max_loss_ct = (rec or {}).get("max_loss_per_ct", 5.0) * 100
        max_profit_ct = (rec or {}).get("max_profit_per_ct", 2.0) * 100
        qty = abs(info["qty"]) or 1
        unreal = info["unrealized"]
        reason = None
        if unreal <= -BREACH_STOP_PCT * max_loss_ct * qty:
            reason = f"breach stop: {unreal:+.0f} <= -{BREACH_STOP_PCT:.0%} of max loss"
        elif max_profit_ct and unreal >= EXIT_PROFIT_PCT * max_profit_ct * qty:
            reason = f"profit take: {unreal:+.0f} >= {EXIT_PROFIT_PCT:.0%} of max profit"
        elif (rec or {}).get("dte", 99) <= MIN_DTE_ROLL:
            reason = f"expiry roll: dte<={MIN_DTE_ROLL}"
        if reason:
            logs.append(f"EXIT {info['symbol']} ({reason})")
            if not dry:
                try:
                    from vulcan.executor import close_position_legs
                    close_position_legs(pos)
                    if rec:
                        rec["status"] = "closed"
                        rec["closed_reason"] = reason
                        rec["closed_at"] = datetime.now(timezone.utc).isoformat()
                    R.register_close(unreal)
                    R.register_open_risk(-(rec or {}).get("risk_total", 0.0))
                except Exception as e:
                    logs.append(f"  close FAILED: {e}")
        else:
            logs.append(f"HOLD {info['symbol']} unreal={unreal:+.0f}")
    return logs


def _hist(st, line: str):
    st.setdefault("history", []).append({"ts": datetime.now(timezone.utc).isoformat(), "line": line})
    st["history"] = st["history"][-50:]


def _structural_win_prob(plan, spot: float, rv_forecast: float, sig_conf: float) -> float:
    """P(max-profit zone) from Model-1's forecast distribution (lognormal approx).

    This is the honest way: the probability must come from the SAME forecast vol
    that generated the trade, applied to the ACTUAL short strikes ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â not from a
    disconnected VRP-confidence prior. Blended 70/30 with the VRP prior, capped.
    """
    sigma_t = max(rv_forecast, 0.03) * math.sqrt(max(plan.dte, 1) / 365.0)

    def phi(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    if plan.name in ("iron_condor", "iron_fly"):
        if plan.name == "iron_fly":
            # legs: [sell P(atm), buy P(low wing), sell C(atm), buy C(high wing)]
            wing_lo = min(l.strike for l in plan.legs if l.kind == "P" and l.side == "buy")
            wing_hi = max(l.strike for l in plan.legs if l.kind == "C" and l.side == "buy")
        else:
            wing_lo = max(l.strike for l in plan.legs if l.kind == "P" and l.side == "sell")
            wing_hi = min(l.strike for l in plan.legs if l.kind == "C" and l.side == "sell")
        z_lo = math.log(wing_lo / spot) / sigma_t
        z_hi = math.log(wing_hi / spot) / sigma_t
        p_struct = phi(z_hi) - phi(z_lo)
    elif plan.name == "bull_put_spread":
        sp = max(l.strike for l in plan.legs if l.side == "sell")
        p_struct = 1.0 - phi(math.log(sp / spot) / sigma_t)          # P(S_T > short put)
    elif plan.name == "bear_call_spread":
        sc = min(l.strike for l in plan.legs if l.side == "sell")
        p_struct = phi(math.log(sc / spot) / sigma_t)                 # P(S_T < short call)
    else:  # debit spreads: P(direction right beyond breakeven)
        be = plan.breakeven
        if "bull" in plan.name:
            p_struct = 1.0 - phi(math.log(be / spot) / sigma_t)
        else:
            p_struct = phi(math.log(be / spot) / sigma_t)

    # PURE structural P â€” must match the constructor's _kelly_edge math exactly
    # (same objective) so builder and gate agree. VRP confidence does not dilute P.
    return float(min(0.95, max(0.05, p_struct)))


def run_cycle(dry: bool = False) -> dict:
    st = load_state()
    st["cycles"] += 1
    cycle_log = {"ts": datetime.now(timezone.utc).isoformat(), "events": []}
    ev = cycle_log["events"]

    if not market_open_now():
        ev.append("market closed ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â managing positions only")
        logs = manage_positions(st, dry)
        ev.extend(logs)
        for e in ev[-6:]:
            _hist(st, e)
        st["status"] = "idle (market closed)"
        save_state(st)
        write_dashboard(st)
        push_to_dashboard(st)
        return cycle_log

    # ---- data ----
    bars = d.get_bars("SPY", days=400)
    df = pd.DataFrame(bars).set_index("t")
    close = df["c"]
    spot = float(close.iloc[-1])
    chain = d.get_option_chain("SPY")

    # ---- MODEL 1 ----
    fc = forecast(close, df.get("v"))

    # ---- MODEL 2 ----
    atm = extract_atm_iv(chain, spot, target_dte=9)
    if atm is None:
        ev.append("no ATM IV available ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â skip")
        save_state(st); write_dashboard(st)
        return cycle_log
    rv20_hist = realized_vol(close, 20).dropna().tolist()
    sig = vrp_signal(atm, fc.ensemble, rv20_hist)
    plan = build_spread_plan(sig, spot, fc.direction_bias, chain)

    if plan is None:
        ev.append(f"no qualifying structure (VRP {sig.vrp*100:+.1f}pts, action={sig.action})")
        save_state(st); write_dashboard(st)
        return cycle_log

    # ---- RISK GATES (sizing first so the agent reviews a real ticket) ----
    vix, vix_chg = try_vix()
    decision = R.evaluate_plan(plan, spot, fc.ensemble, vix, vix_chg, fc.regime["regime"],
                               win_prob=_structural_win_prob(plan, spot, fc.ensemble, sig.confidence),
                               equity=float(d.get_account()["equity"]))
    contracts = decision.contracts
    if not decision.approved or contracts < 1:
        ev.append(f"RISK DENIED: {'; '.join(decision.reasons)}")
        save_state(st); write_dashboard(st); push_to_dashboard(st)
        return cycle_log
    if decision.mc:
        st["last_mc"] = decision.mc
        ev.append(f"MC VaR: 99%=${decision.mc['var99']:.0f}/ct CVaR=${decision.mc['cvar99']:.0f} "
                  f"P(breach)={decision.mc['prob_breach']*100:.1f}% VR={decision.mc['vr_factor']:.1f}x "
                  f"({decision.mc['n_paths']:,} paths)")

    # ---- MODEL 3: agent debate on the actual ticket ----
    verdict = run_agent(fc, sig, plan, decision.reasons, contracts)
    if verdict.decision == "VETO":
        ev.append(f"AGENT VETO: {verdict.pm_reason[:160]}")
        save_state(st); write_dashboard(st); push_to_dashboard(st)
        return cycle_log
    if verdict.decision == "SHRINK":
        new_c = max(int(contracts * verdict.shrink_factor), 0)
        ev.append(f"AGENT SHRINK x{verdict.shrink_factor:.2f}: {contracts} -> {new_c}")
        contracts = new_c
        if contracts < 1:
            save_state(st); write_dashboard(st); push_to_dashboard(st)
            return cycle_log

    st["last_forecast"] = {"ensemble": fc.ensemble, "har": fc.har, "garch": fc.garch,
                           "kalman": fc.kalman, "realized_20": fc.realized_20,
                           "rv_ratio": fc.rv_ratio, "regime": fc.regime.get("regime"),
                           "direction_bias": fc.direction_bias}
    st["last_signal"] = {"atm_iv": sig.atm_iv, "rv_forecast": sig.rv_forecast, "vrp": sig.vrp,
                         "vrp_ratio": sig.vrp_ratio, "iv_rank_proxy": sig.iv_rank_proxy,
                         "term_slope": sig.term_slope, "skew": sig.skew,
                         "action": sig.action, "confidence": sig.confidence}
    st["last_agent"] = {"decision": verdict.decision, "llm_used": verdict.llm_used,
                        "pm_reason": verdict.pm_reason, "bull_case": verdict.bull_case,
                        "bear_case": verdict.bear_case, "risk_note": verdict.risk_note}

    # ---- EXECUTE ----
    par = plan.max_loss * 100 * contracts
    ev.append(f"EXECUTE {plan.name} x{contracts} credit={plan.credit:+.2f} "
              f"risk=${par:,.0f} ({par/100000*100:.2f}% NAV) | VRP {sig.vrp*100:+.1f}pts "
              f"IV{sig.atm_iv*100:.0f}% vs RVfc{sig.rv_forecast*100:.0f}% regime={fc.regime['regime']}")
    if dry:
        ev.append("DRY-RUN: order not submitted")
    else:
        try:
            resp = submit_spread(plan, contracts)
            ev.append(f"ORDER {resp.get('id', '?')} status={resp.get('status')}")
            st["trades"].append({
                "ts": cycle_log["ts"], "name": plan.name, "contracts": contracts,
                "credit": plan.credit, "max_loss_per_ct": plan.max_loss,
                "max_profit_per_ct": plan.max_profit, "dte": plan.dte,
                "risk_total": par, "status": "open",
                "legs": [{"symbol": l.symbol, "side": l.side, "kind": l.kind,
                          "strike": l.strike, "expiration": l.expiration} for l in plan.legs],
                "vrp": sig.vrp, "iv": sig.atm_iv, "rv_fc": sig.rv_forecast,
                "agent": {"decision": verdict.decision, "reason": verdict.pm_reason[:300]},
            })
            R.register_open_risk(par)
        except Exception as e:
            ev.append(f"ORDER FAILED: {e}")

    # ---- equity long/short sleeve (options remain the compliance core) ----
    try:
        from vulcan.equity_sleeve import plan_equity_trade, submit_equity_bracket
        has_spy_stock = any(p["symbol"] == "SPY" for p in (d.get_positions() or []))
        if not has_spy_stock and fc.direction_bias is not None:
            ep = plan_equity_trade(fc, spot, "SPY", float(d.get_account()["equity"]))
            if ep:
                if dry:
                    ev.append(f"EQUITY DRY-RUN: {ep.side} {ep.qty} SPY (${ep.notional:,.0f}) {ep.rationale}")
                else:
                    resp = submit_equity_bracket(ep, spot)
                    ev.append(f"EQUITY {ep.side.upper()} {ep.qty} SPY @~{spot:.2f} "
                              f"(bracket stop -3%/trail +8%) | {ep.rationale} | id={resp.get('id', '?')[:12]}")
            else:
                ev.append(f"EQUITY: no trade (bias {fc.direction_bias:+.2f}, regime {fc.regime['regime']})")
    except Exception as e:
        ev.append(f"EQUITY sleeve error: {e}")

    # ---- manage existing ----
    ev.extend(manage_positions(st, dry))

    for e in ev[-6:]:
        _hist(st, e)
    st["status"] = "ok"
    save_state(st)
    write_dashboard(st)
    push_to_dashboard(st)
    return cycle_log


def try_vix() -> tuple[float | None, float | None]:
    try:
        bars = d.get_bars("VIX", days=10)
        closes = [b["c"] for b in bars]
        if len(closes) >= 2:
            return closes[-1], closes[-1] / closes[-2] - 1
    except Exception:
        pass
    return None, None


def write_dashboard(st: dict):
    try:
        acc = d.get_account()
        positions = [position_pnl(p) for p in d.get_positions()]
    except Exception:
        acc, positions = {}, []
    dash = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "account": {"equity": acc.get("equity"), "cash": acc.get("cash"),
                    "unrealized": acc.get("unrealized_pl")},
        "positions": positions,
        "trades": st.get("trades", [])[-20:],
        "cycles": st.get("cycles", 0),
    }
    DATA_DIR.mkdir(exist_ok=True)
    DASH_PATH.write_text(json.dumps(dash, indent=2, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--interval", type=int, default=900)
    args = ap.parse_args()

    while True:
        try:
            out = run_cycle(dry=args.dry_run)
            for e in out["events"]:
                print(f"[{out['ts'][11:19]}] {e}")
        except Exception as e:
            print(f"CYCLE ERROR: {e}")
        if not args.loop:
            break
        time.sleep(args.interval)
