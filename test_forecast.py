from vulcan import data as d
import pandas as pd
from vulcan.vol_forecaster import forecast

bars = d.get_bars("SPY", days=400)
df = pd.DataFrame(bars).set_index("t")
fc = forecast(df["c"], df.get("v"))
print("=== VULCAN VOL FORECAST (SPY) ===")
print(f"HAR-RV   : {fc.har*100:6.1f}%")
print(f"GARCH    : {fc.garch*100:6.1f}%")
print(f"Kalman   : {fc.kalman*100:6.1f}%")
print(f"ENSEMBLE : {fc.ensemble*100:6.1f}%")
print(f"RV20     : {fc.realized_20*100:6.1f}%  | rv5/rv20 = {fc.rv_ratio:.2f}")
print(f"Regime   : {fc.regime}")
print(f"Direction: bias={fc.direction_bias:+.2f} {fc.direction}")
