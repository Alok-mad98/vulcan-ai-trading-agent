"""VULCAN Model 2 test: ATM IV extraction + VRP signal + spread plan construction."""
import pandas as pd
from vulcan import data as d
from vulcan.vol_forecaster import forecast, realized_vol
from vulcan.pricer import extract_atm_iv, vrp_signal, build_spread_plan

bars = d.get_bars("SPY", days=400)
df = pd.DataFrame(bars).set_index("t")
close = df["c"]
fc = forecast(close, df.get("v"))
spot = float(close.iloc[-1])
print(f"SPY spot: {spot:.2f} | forecast RV: {fc.ensemble*100:.1f}% | regime: {fc.regime['regime']}")

chain = d.get_option_chain("SPY")
atm = extract_atm_iv(chain, spot, target_dte=9)
if atm is None:
    raise SystemExit("no ATM IV extracted")
print(f"ATM IV: {atm.atm_iv*100:.1f}% (call {atm.iv_call*100:.1f}% / put {atm.iv_put*100:.1f}%) | dte={atm.dte}")
print(f"term slope: {atm.forward_iv_1w}, put skew: {atm.put_skew}")

rv20_hist = realized_vol(close, 20).dropna().tolist()
sig = vrp_signal(atm, fc.ensemble, rv20_hist)
print(f"\n=== VRP SIGNAL ===")
print(f"IV {sig.atm_iv*100:.1f}% vs RVfc {sig.rv_forecast*100:.1f}% -> VRP {sig.vrp*100:+.1f} pts (ratio {sig.vrp_ratio:.2f})")
print(f"IV rank proxy: {sig.iv_rank_proxy:.2f} | action: {sig.action} | confidence: {sig.confidence:.2f}")

plan = build_spread_plan(sig, spot, fc.direction_bias, chain)
if plan:
    print(f"\n=== PLAN: {plan.name} ({plan.dte}dte) ===")
    for l in plan.legs:
        print(f"  {l.side.upper():4s} {l.kind}{l.strike:.0f} @ ~{l.est_price:.2f}  ({l.symbol})")
    print(f"credit={plan.credit:+.2f} width={plan.width:.1f} max_loss={plan.max_loss:.2f} max_profit={plan.max_profit:.2f} BE={plan.breakeven:.0f}")
    print(f"rationale: {plan.rationale}")
else:
    print("\nno plan constructed (neutral)")
