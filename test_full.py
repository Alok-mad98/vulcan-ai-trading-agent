"""Full pipeline test — bypasses market-hours guard (weekend test)."""
import json
from datetime import datetime, timezone

import pandas as pd

from vulcan import data as d
from vulcan.vol_forecaster import forecast, realized_vol
from vulcan.pricer import extract_atm_iv, vrp_signal, build_spread_plan
from vulcan import risk as R
from vulcan.agent import run_agent

print("fetching data...")
bars = d.get_bars("SPY", days=400)
df = pd.DataFrame(bars).set_index("t")
close = df["c"]
spot = float(close.iloc[-1])
chain = d.get_option_chain("SPY")

print("\n--- MODEL 1: VOL FORECAST ---")
fc = forecast(close, df.get("v"))
print(f"ensemble RV={fc.ensemble*100:.1f}% | regime={fc.regime} | bias={fc.direction_bias:+.2f}")

print("\n--- MODEL 2: VRP SIGNAL ---")
atm = extract_atm_iv(chain, spot, target_dte=9)
rv20_hist = realized_vol(close, 20).dropna().tolist()
sig = vrp_signal(atm, fc.ensemble, rv20_hist)
print(f"IV={sig.atm_iv*100:.1f}% VRP={sig.vrp*100:+.1f}pts action={sig.action} conf={sig.confidence:.2f}")
plan = build_spread_plan(sig, spot, fc.direction_bias, chain)
if plan is None:
    print("no plan — neutral market, nothing to do")
    raise SystemExit(0)
print(f"PLAN {plan.name}: credit={plan.credit:+.2f} max_loss={plan.max_loss:.2f} dte={plan.dte}")

print("\n--- MODEL 3: AGENT DEBATE (LLM) ---")
verdict = run_agent(fc, sig, plan, [], 0)
print(f"decision: {verdict.decision} (llm_used={verdict.llm_used})")
print(f"PM: {verdict.pm_reason[:300]}")
print(f"BULL: {(verdict.bull_case or '')[:200]}")
print(f"BEAR: {(verdict.bear_case or '')[:200]}")

print("\n--- RISK GATES ---")
from vulcan.main import try_vix
vix, vix_chg = try_vix()
print(f"VIX={vix} chg={vix_chg}")
win_prob = min(0.90, 0.5 + sig.confidence * 0.35 + max(0.0, sig.vrp) * 2)
decision = R.evaluate_plan(plan, spot, fc.ensemble, vix, vix_chg, fc.regime["regime"], win_prob,
                           equity=float(d.get_account()["equity"]))
print(f"approved={decision.approved} contracts={decision.contracts}")
for r in decision.reasons:
    print(f"  {r}")

print("\n=== FINAL: " + ("WOULD EXECUTE " + str(decision.contracts) + " CONTRACTS" if decision.approved else "NO TRADE") + " ===")
