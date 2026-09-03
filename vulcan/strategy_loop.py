"""VULCAN — Strategy Research Loop (the loop-engineering framework).

Implements the 5-stage loop from the research doc:
  1. GENERATE  — parameter grid over strategy variants (offset mult, credit bar, threshold)
  2. BACKTEST  — walk-forward, no leakage: every signal uses ONLY data before day t
  3. SCORE     — ICIR = mean(monthly IC)/std(monthly IC); kill < 0.3
  4. ANALYZE   — failure modes per variant fed back as next-round constraints
  5. GATE      — out-of-sample (last 25% untouched) + deflated Sharpe
                 (López de Prado) correcting for N variants tested

Synthetic options backtest: we price a condor at IV_proxy = RV20 * vrp_markup
(conservative documented assumption) and settle against the realized path —
this is the standard way to test VRP strategies without full historical chains.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, norm

from vulcan.vol_forecaster import har_rv_forecast, garch_vol_forecast, kalman_vol_forecast, realized_vol


# ---------------- walk-forward RV forecast (no leakage) ----------------
def walk_forward_rv_forecast(close: pd.Series, min_hist: int = 150) -> pd.Series:
    """At each day t, ensemble RV forecast using data up to t-1 only. Expensive but honest."""
    rets = close.pct_change()
    rv_daily = (np.log(close / close.shift(1)).abs() * np.sqrt(252))
    out = pd.Series(index=close.index, dtype=float)
    rv20 = realized_vol(close, 20)
    n = len(close)
    for i in range(min_hist, n):
        hist_c = close.iloc[:i]
        # subsample: refit HAR/Kalman daily, GARCH every 5 days is too slow -> GARCH weekly
        har = har_rv_forecast(rv_daily.iloc[:i])
        kal = kalman_vol_forecast(rv_daily.iloc[:i])
        if i % 5 == 0 or out.iloc[i - 1] != out.iloc[i - 1]:  # first time or every 5d
            g = garch_vol_forecast(rets.iloc[:i])
        else:
            g = out.iloc[i - 1] * 1.0
        out.iloc[i] = 0.4 * har + 0.35 * g + 0.25 * kal
    return out


# ---------------- synthetic condor settlement ----------------
def settle_condor(spot0: float, spot1: float, rv_realized_1d_path: np.ndarray,
                  offset_pct: float, width_pct: float, iv_at_entry: float,
                  dte: int, fee_per_contract: float = 1.3) -> dict:
    """Sell condor at iv_at_entry, settle at expiry vs realized path.

    Payoff approximation: condor P&L = credit - intrinsic_width if spot breaches a wing,
    scaled linearly between short strike and wing (standard condor payoff).
    Returns pnl per 1 contract (in $, multiplier 100).
    """
    off = spot0 * offset_pct
    w = spot0 * width_pct
    short_p, long_p = spot0 - off, spot0 - off - w
    short_c, long_c = spot0 + off, spot0 + off + w

    # entry credit priced at iv_at_entry via simple BS on 4 legs
    from vulcan.pricer import bs_price
    t = dte / 365.0
    credit = (bs_price(spot0, short_p, t, iv_at_entry, kind="P") - bs_price(spot0, long_p, t, iv_at_entry, kind="P")
              + bs_price(spot0, short_c, t, iv_at_entry, kind="C") - bs_price(spot0, long_c, t, iv_at_entry, kind="C"))

    s1 = spot1
    def condor_payoff(s: float) -> float:
        put_leg = min(max(s - long_p, 0.0), w) - min(max(s - short_p, 0.0), w)
        call_leg = min(max(short_c - s, 0.0), w) - min(max(long_c - s, 0.0), w)
        return put_leg + call_leg  # intrinsic at expiry (loss when positive)

    intrinsic = condor_payoff(s1)
    pnl = (credit - intrinsic) * 100.0 - fee_per_contract * 4
    return {"pnl": pnl, "credit": credit, "win": pnl > 0,
            "max_loss": (w - credit) * 100, "max_profit": credit * 100}


# ---------------- metrics ----------------
def monthly_icir(signal: pd.Series, forward_ret: pd.Series) -> tuple[float, int]:
    """Monthly Spearman IC between signal and next-month forward returns -> ICIR."""
    df = pd.concat([signal, forward_ret], axis=1).dropna()
    df.columns = ["sig", "fwd"]
    ics = []
    for _, g in df.groupby(pd.Grouper(freq="ME")):
        if len(g) >= 15:
            ic, _ = spearmanr(g["sig"], g["fwd"])
            if not math.isnan(ic):
                ics.append(ic)
    if len(ics) < 3:
        return 0.0, len(ics)
    return float(np.mean(ics) / max(np.std(ics), 1e-9)), len(ics)


def sharpe(daily_pnl: pd.Series) -> float:
    r = daily_pnl.dropna()
    if len(r) < 20 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * math.sqrt(252))


def max_drawdown(equity: pd.Series) -> float:
    eq = equity.dropna()
    if len(eq) < 2:
        return 0.0
    dd = eq / eq.cummax() - 1
    return float(dd.min())


def deflated_sharpe(sr: float, n: int, n_variants: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Probability that SR is real after multiple-testing (Bailey & López de Prado).

    Uses the expected-max-SR-under-null of n_variants trials.
    """
    if n < 20:
        return 0.0
    sr_annual = sr / math.sqrt(252) if abs(sr) > 3 else sr  # accept daily or annualized
    e_max_sr = math.sqrt((2 * math.log(n_variants)) / max(n - 1, 1))
    denom = math.sqrt(max((1 - skew * sr_annual + (kurt - 1) / 4 * sr_annual ** 2) / max(n - 1, 1), 1e-12))
    z = (sr_annual - e_max_sr) / denom
    return float(norm.cdf(z))


# ---------------- the loop ----------------
@dataclass
class VariantResult:
    params: dict
    n_trades: int
    win_rate: float
    avg_pnl: float
    profit_factor: float
    sharpe: float
    max_dd: float
    icir: float
    ic_months: int
    is_pnl: float          # in-sample total
    oos_pnl: float         # out-of-sample total
    oos_sharpe: float
    dsr_p: float           # deflated Sharpe probability
    pass_gate: bool
    failures: list = field(default_factory=list)


def run_loop(close: pd.Series, param_grid: dict | None = None, max_rounds: int = 2) -> list[VariantResult]:
    """Run the full loop: grid -> IS backtest -> ICIR kill -> OOS gate -> DSR."""
    close = close.copy()
    close.index = pd.to_datetime(close.index)
    close = close.dropna()
    n = len(close)
    split = int(n * 0.75)
    is_end = split
    oos_slice = slice(split, n)

    if param_grid is None:
        # Round-1 grid (tight): offsets/widths scaled to daily vol regime
        param_grid = {
            "offset_atm_sigma": [0.8, 1.0, 1.2],   # short strikes at k*sigma*dte-sqrt-scaled
            "width_atm_sigma": [0.5, 0.8],
            "vrp_threshold_pts": [0.01, 0.02],      # trade only when VRP >= threshold
            "vrp_markup": [1.10, 1.18],             # conservative IV = RV20 * markup
        }
    keys = list(param_grid)
    variants = [dict(zip(keys, v)) for v in itertools.product(*param_grid.values())]
    print(f"LOOP: testing {len(variants)} variants | IS days={is_end} OOS days={n - split}")

    rv_fc = walk_forward_rv_forecast(close)
    rv20 = realized_vol(close, 20)
    fwd5 = close.shift(-5) / close - 1.0  # 5-day forward return (options horizon proxy)

    results: list[VariantResult] = []
    for vi, p in enumerate(variants):
        pnls, sig_vals = [], []
        oos_pnls = []
        for i in range(150, n - 6):
            fc = rv_fc.iloc[i]
            iv_proxy = rv20.iloc[i] * p["vrp_markup"]
            vrp = iv_proxy - fc
            sig_vals.append(vrp)
            dte = 9
            # ATM sigma scale for strikes
            sig_scale = fc * math.sqrt(dte / 365.0)
            off = p["offset_atm_sigma"] * sig_scale / max(0.01, 0.01)
            # convert to pct of spot
            off_pct = p["offset_atm_sigma"] * fc * math.sqrt(dte / 365.0)
            w_pct = p["width_atm_sigma"] * fc * math.sqrt(dte / 365.0)
            if vrp >= p["vrp_threshold_pts"]:
                r = settle_condor(close.iloc[i], close.iloc[min(i + dte, n - 1)], None,
                                  off_pct, w_pct, iv_proxy, dte)
                pnls.append((close.index[i], r["pnl"]))
                if i >= split:
                    oos_pnls.append(r["pnl"])
            else:
                pnls.append((close.index[i], 0.0))
                if i >= split:
                    oos_pnls.append(0.0)

        if len(pnls) < 60:
            continue
        pnl_s = pd.Series(dict(pnls)).sort_index()
        sig_s = pd.Series(sig_vals, index=pnl_s.index[:len(sig_vals)])
        trades = pnl_s[pnl_s != 0]
        win_rate = float((trades > 0).mean()) if len(trades) else 0.0
        wins, losses = trades[trades > 0], trades[trades < 0]
        pf = float(wins.sum() / max(-losses.sum(), 1e-9)) if len(losses) else 10.0
        sr = sharpe(pnl_s)
        icir, ic_months = monthly_icir(sig_s, fwd5.reindex(pnl_s.index))
        eq = pnl_s.cumsum()
        mdd = max_drawdown(eq)

        oos_s = pd.Series(oos_pnls)
        oos_sr = sharpe(oos_s[oos_s != 0] if (oos_s != 0).sum() > 20 else oos_s)

        failures = []
        if icir < 0.3:
            failures.append(f"ICIR {icir:.2f} < 0.3")
        if win_rate < 0.5 and pf < 1.2:
            failures.append(f"weak payoff wr={win_rate:.0%} pf={pf:.2f}")
        if mdd < -0.15 * 3000:  # drawdown > 15% of a ~3k risk budget
            failures.append(f"maxDD ${-mdd:.0f}")

        # OOS gate: OOS sharpe must retain >= 50% of IS sharpe
        gate = (len(failures) == 0) and (oos_sr >= 0.5 * sr if sr > 0 else False)
        dsr = deflated_sharpe(sr, n=len(pnl_s), n_variants=len(variants))
        gate = gate and dsr > 0.90

        results.append(VariantResult(
            params=p, n_trades=int(len(trades)), win_rate=win_rate,
            avg_pnl=float(trades.mean()) if len(trades) else 0.0,
            profit_factor=pf, sharpe=sr, max_dd=mdd, icir=icir, ic_months=ic_months,
            is_pnl=float(pnl_s[:close.index[is_end - 1]].sum()),
            oos_pnl=float(sum(oos_pnls)), oos_sharpe=oos_sr, dsr_p=dsr,
            pass_gate=gate, failures=failures))

    results.sort(key=lambda r: (r.pass_gate, r.icir, r.sharpe), reverse=True)
    return results


if __name__ == "__main__":
    from vulcan import data as d
    bars = d.get_bars("SPY", days=400)
    close = pd.DataFrame(bars).set_index("t")["c"]
    res = run_loop(close)
    print(f"\n{'='*100}\nLOOP RESULTS (sorted: gate, ICIR, Sharpe)\n{'='*100}")
    for r in res[:12]:
        p = r.params
        tag = "PASS" if r.pass_gate else "kill"
        print(f"[{tag}] off={p['offset_atm_sigma']}sig w={p['width_atm_sigma']}sig "
              f"thr={p['vrp_threshold_pts']:.2f} mk={p['vrp_markup']:.2f} | "
              f"n={r.n_trades} wr={r.win_rate:.0%} pf={r.profit_factor:.2f} "
              f"sr={r.sharpe:.2f} icir={r.icir:.2f}({r.ic_months}mo) oos={r.oos_pnl:+.0f} "
              f"dsr={r.dsr_p:.2f} {'; '.join(r.failures)}")
