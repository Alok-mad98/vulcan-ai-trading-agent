import re
import vulcan.data as d

chain = d.get_option_chain("SPY")
print("chain contracts:", len(chain))
with_iv = [x for x in chain if x.get("impliedVolatility")]
print("with IV:", len(with_iv))
for x in with_iv[:5]:
    g = x.get("greeks") or {}
    print(f"  {x['symbol']} IV={x['impliedVolatility']:.4f} delta={g.get('delta')}")

# group by expiration
exps = {}
for x in chain:
    m = re.match(r"[A-Z]+(\d{6})([CP])(\d+)", x["symbol"].replace(" ", ""))
    if m:
        exps.setdefault(m.group(1), 0)
        exps[m.group(1)] += 1
print("expirations (YYMMDD: n):", dict(sorted(exps.items())[:10]))

bars = d.get_bars("SPY", days=90)
print(f"\nSPY bars: {len(bars)} (latest close: {bars[-1]['c'] if bars else '?'})")
