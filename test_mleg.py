"""Reproduce the mleg 422 with the exact executor format, capture the error body."""
from vulcan import data as d

# a minimal 2-leg bear call spread (the format executor.submit_spread builds)
legs = [
    {"symbol": "SPY260910C00770000", "ratio_qty": 1, "side": "sell"},
    {"symbol": "SPY260910C00772000", "ratio_qty": 1, "side": "buy"},
]
order = {
    "order_class": "mleg",
    "qty": "1",
    "order_type": "limit",
    "time_in_force": "day",
    "limit_price": -0.30,
    "legs": legs,
}
print("submitting:", order)
try:
    resp = d.submit_order(order)
    print("OK:", resp.get("id"), resp.get("status"))
except Exception as e:
    print("ERROR:", e)

# variant: extended_hours not allowed for options; try without limit sign change
order2 = dict(order)
order2["limit_price"] = 0.30  # positive = max debit
try:
    resp = d.submit_order(order2)
    print("OK(positive):", resp.get("id"), resp.get("status"))
except Exception as e:
    print("ERROR(positive):", e)
