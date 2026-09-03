"""VULCAN Model 2 ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Options pricer + Variance Risk Premium (VRP) signal.

Pricing: self-contained Black-Scholes + Greeks (fast, no GPL deps at runtime).
VRP signal: ATM implied vol (from Alpaca chain) vs Model-1 ensemble RV forecast.
Strategy constructor: defined-risk structures only (credit spreads / condors / debits).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

SQRT252 = math.sqrt(252.0)


# ---------------- Black-Scholes ----------------
def _N(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(S: float, K: float, t_years: float, sigma: float, r: float = 0.045, q: float = 0.0, kind: str = "C") -> float:
    if t_years <= 0 or sigma <= 0:
        return max(0.0, (S - K) if kind == "C" else (K - S))
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * t_years) / (sigma * math.sqrt(t_years))
    d2 = d1 - sigma * math.sqrt(t_years)
    if kind == "C":
        return S * math.exp(-q * t_years) * _N(d1) - K * math.exp(-r * t_years) * _N(d2)
    return K * math.exp(-r * t_years) * _N(-d2) - S * math.exp(-q * t_years) * _N(-d1)


def bs_greeks(S: float, K: float, t_years: float, sigma: float, r: float = 0.045, q: float = 0.0, kind: str = "C") -> dict:
    if t_years <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    st = sigma * math.sqrt(t_years)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * t_years) / st
    d2 = d1 - st
    gamma = math.exp(-q * t_years) * _phi(d1) / (S * st)
    vega = S * math.exp(-q * t_years) * _phi(d1) * math.sqrt(t_years) / 100.0  # per 1 vol pt
    if kind == "C":
        delta = math.exp(-q * t_years) * _N(d1)
        theta = (-(S * math.exp(-q * t_years) * _phi(d1) * sigma) / (2 * math.sqrt(t_years))
                 - r * K * math.exp(-r * t_years) * _N(d2) + q * S * math.exp(-q * t_years) * _N(d1)) / 365.0
    else:
        delta = -math.exp(-q * t_years) * _N(-d1)
        theta = (-(S * math.exp(-q * t_years) * _phi(d1) * sigma) / (2 * math.sqrt(t_years))
                 + r * K * math.exp(-r * t_years) * _N(-d2) - q * S * math.exp(-q * t_years) * _N(-d1)) / 365.0
    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


# ---------------- contract symbol parsing ----------------
_SYM_RE = re.compile(r"([A-Z]+)(\d{6})([CP])(\d{8})$")


def parse_option_symbol(sym: str) -> dict | None:
    """SPY260904P00730000 -> dict(under, yymmdd, kind, strike, dte)."""
    s = sym.replace(" ", "").split(";")[0]
    m = _SYM_RE.match(s)
    if not m:
        return None
    und, ymd, kind, strike = m.group(1), m.group(2), m.group(3), m.group(4)
    exp = f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:]}"
    return {"underlying": und, "expiration": exp, "kind": kind, "strike": int(strike) / 1000.0}


# ---------------- IV extraction ----------------
@dataclass
class AtmIv:
    iv_call: float
    iv_put: float
    atm_iv: float          # average of call/put ATM
    forward_iv_1w: float | None   # IV of ~1-week expiry (for term structure)
    put_skew: float | None        # 25-delta-ish put IV minus ATM IV
    spot: float
    dte: int


def extract_atm_iv(chain: list, spot: float, target_dte: int = 7, ref_dte: int = 1) -> AtmIv | None:
    """Find nearest-dated expiry ~ target_dte; return ATM IV + term structure + skew."""
    by_exp: dict[str, list] = {}
    for s in chain:
        meta = parse_option_symbol(s["symbol"])
        if not meta or not s.get("impliedVolatility"):
            continue
        by_exp.setdefault(meta["expiration"], []).append({**meta, **s})

    if not by_exp:
        return None

    def _dte(exp: str, ref=None) -> int:
        from datetime import date
        y, m, dd = map(int, exp.split("-"))
        d0 = ref or date.today()
        return (date(y, m, dd) - d0).days

    import datetime as _dt
    today = _dt.date.today()
    ranked = sorted(by_exp.items(), key=lambda kv: abs(_dte(kv[0], today) - target_dte))
    exp, legs = ranked[0]
    dte = max(_dte(exp, today), 1)

    calls = sorted([l for l in legs if l["kind"] == "C"], key=lambda l: abs(l["strike"] - spot))
    puts = sorted([l for l in legs if l["kind"] == "P"], key=lambda l: abs(l["strike"] - spot))
    if not calls or not puts:
        return None
    iv_call = float(calls[0]["impliedVolatility"])
    iv_put = float(puts[0]["impliedVolatility"])
    atm_iv = 0.5 * (iv_call + iv_put)

    # term structure: next expiry beyond the main one (>=5 dte further)
    later = [e for e, _ in ranked if _dte(e, today) > dte + 4]
    fwd_iv = None
    if later:
        legs2 = by_exp[later[0]]
        c2 = sorted([l for l in legs2 if l["kind"] == "C"], key=lambda l: abs(l["strike"] - spot))
        if c2:
            fwd_iv = float(c2[0]["impliedVolatility"])

    # put skew: OTM put ~5% below spot vs ATM
    otm_puts = [l for l in legs if l["kind"] == "P" and l["strike"] <= spot * 0.95]
    put_skew = None
    if otm_puts:
        nearest = min(otm_puts, key=lambda l: abs(l["strike"] - spot * 0.95))
        put_skew = float(nearest["impliedVolatility"]) - atm_iv

    return AtmIv(iv_call=iv_call, iv_put=iv_put, atm_iv=atm_iv,
                 forward_iv_1w=fwd_iv, put_skew=put_skew, spot=spot, dte=dte)


# ---------------- VRP signal ----------------
@dataclass
class VrpSignal:
    atm_iv: float          # annualized implied vol (market price of risk)
    rv_forecast: float     # Model-1 ensemble forecast
    vrp: float             # IV - RV forecast (annualized vol pts)
    vrp_ratio: float       # IV / RV
    iv_rank_proxy: float   # ATM IV percentile vs last-90d RV20 range (0..1)
    term_slope: float | None
    skew: float | None
    action: str            # SELL_PREMIUM / BUY_VOL / NEUTRAL
    confidence: float      # 0..1


def vrp_signal(atm: AtmIv, fc_ensemble: float, rv20_hist: list[float]) -> VrpSignal:
    vrp = atm.atm_iv - fc_ensemble
    ratio = atm.atm_iv / max(fc_ensemble, 1e-4)
    hist = [v for v in rv20_hist if v > 0]
    irp = 0.5
    if len(hist) >= 30:
        lo, hi = np.percentile(hist, 5), np.percentile(hist, 95)
        irp = float(np.clip((atm.atm_iv - lo) / max(hi - lo, 1e-9), 0, 1))

    # term structure: contango (fwd > spot iv) favors selling; backwardation favors buying
    slope = (atm.forward_iv_1w - atm.atm_iv) if atm.forward_iv_1w is not None else None

    if vrp > 0.020 and ratio > 1.12 and irp > 0.25:
        action, conf = "SELL_PREMIUM", min(1.0, (vrp / 0.08) * (1.1 if slope is None else (1.2 if slope > 0 else 0.9)))
    elif vrp < -0.015 and ratio < 0.92:
        action, conf = "BUY_VOL", min(1.0, (-vrp / 0.06))
    else:
        action, conf = "NEUTRAL", 0.3

    return VrpSignal(atm_iv=atm.atm_iv, rv_forecast=fc_ensemble, vrp=vrp, vrp_ratio=ratio,
                     iv_rank_proxy=irp, term_slope=slope, skew=atm.put_skew,
                     action=action, confidence=float(np.clip(conf, 0, 1)))


# ---------------- strategy constructor (defined-risk only) ----------------
@dataclass
class Leg:
    symbol: str
    side: str            # buy / sell
    kind: str            # C / P
    strike: float
    expiration: str
    qty: int = 1
    est_price: float = 0.0


@dataclass
class SpreadPlan:
    name: str            # bull_put_spread / bear_call_spread / iron_condor / bull_call_spread / bear_put_spread
    legs: list[Leg]
    width: float
    credit: float        # per spread (positive = net credit)
    max_loss: float      # per spread = width - credit (credit spreads) or debit (debit spreads)
    max_profit: float
    breakeven: float
    dte: int
    rationale: str


def build_spread_plan(signal: VrpSignal, spot: float, direction_bias: float, chain: list,
                      width_pct: float = 0.030, otm_offset_pct: float = 0.010) -> SpreadPlan | None:
    """Construct a defined-risk structure matching the VRP action + direction bias.

    SELL_PREMIUM:
      bias > +0.15  -> bull put spread  (OTM put credit spread below spot)
      bias < -0.15  -> bear call spread (OTM call credit spread above spot)
      else          -> iron condor
    BUY_VOL:
      bias > +0.15  -> bull call spread (debit); bias < -0.15 -> bear put spread; else None
    All legs come from the nearest expiry with >=2 DTE and liquid quotes.
    """
    from datetime import date
    import datetime as _dt

    # group chain by expiration, pick one ~7-21 dte with good quote coverage
    by_exp: dict[str, list] = {}
    for s in chain:
        meta = parse_option_symbol(s["symbol"])
        if not meta or not s.get("impliedVolatility"):
            continue
        by_exp.setdefault(meta["expiration"], []).append({**meta, **s})
    if not by_exp:
        return None
    today = _dt.date.today()

    def _dte(exp: str) -> int:
        y, m, dd = map(int, exp.split("-"))
        return (date(y, m, dd) - today).days

    candidates = sorted(
        [(e, legs) for e, legs in by_exp.items() if 2 <= _dte(e) <= 35],
        key=lambda kv: abs(_dte(kv[0]) - 9),
    )
    if not candidates:
        return None
    exp, legs = candidates[0]
    dte = _dte(exp)

    # VRP geometry — all distances in IMPLIED-sigma units (where credit is rich),
    # while P(win) everywhere uses the FORECAST sigma (lower when VRP > 0).
    sig_t_impl = spot * signal.atm_iv * math.sqrt(dte / 365.0)   # ~1 sigma_impl in points
    offset = sig_t_impl          # base: shorts start at 1.0 sigma_impl OTM (grid scales 0.7-2.2)
    width = sig_t_impl * 0.5     # base wing width: 0.5 sigma_impl (grid scales 0.3-1.0)

    def _leg(kind: str, strike: float) -> Leg | None:
        tol = min(width * 0.35, 3.0)
        pool = [l for l in legs if l["kind"] == kind and abs(l["strike"] - strike) <= tol]
        if not pool:
            return None
        best = min(pool, key=lambda l: abs(l["strike"] - strike))
        q = best.get("latestQuote") or {}
        px = (q.get("bp") + q.get("ap")) / 2 if q.get("bp") and q.get("ap") else None
        return Leg(symbol=best["symbol"], side="", kind=kind, strike=float(best["strike"]),
                   expiration=exp, est_price=float(px) if px else bs_price(
                       spot, float(best["strike"]), dte / 365.0, float(best["impliedVolatility"])))

    def _mk(short_kind: str, short_k: float, long_k: float, name: str, credit_side: bool, rationale: str) -> SpreadPlan | None:
        short = _leg(short_kind, short_k)
        long = _leg(short_kind, long_k)
        if not short or not long:
            return None
        short.side, long.side = "sell", "buy"
        diff = abs(short_k - long_k)
        if credit_side:
            credit = short.est_price - long.est_price
            if credit <= 0.05:
                return None
            max_loss, max_profit = diff - credit, credit
            be = short_k + (diff - credit) if short_kind == "C" else short_k - (diff - credit)
        else:
            debit = long.est_price - short.est_price
            if debit <= 0.05:
                return None
            credit = -debit
            max_loss, max_profit = debit, diff - debit
            be = long_k + debit if short_kind == "C" else long_k - debit
        return SpreadPlan(name=name, legs=[short, long], width=diff, credit=credit,
                          max_loss=max_loss, max_profit=max_profit, breakeven=be, dte=dte,
                          rationale=rationale)

    def _kelly_edge(credit: float, w: float, short_kind: str, short_k: float) -> float:
        """Kelly edge of a candidate structure using Model-1's forecast distribution.

        Constructor and risk gate now optimize the SAME objective ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â no more
        credit/width-vs-Kelly disagreement. Requires positive edge to trade.
        """
        sigma_t = max(signal.rv_forecast, 0.03) * math.sqrt(dte / 365.0)

        def phi(x: float) -> float:
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

        z = math.log(short_k / spot) / sigma_t
        if short_kind == "P":
            p_win = 1.0 - phi(z)          # P(S_T > short put)
        else:
            p_win = phi(z)                # P(S_T < short call)
        b = credit / max(w - credit, 1e-9)
        return p_win * b - (1.0 - p_win)

    def _iron_fly() -> SpreadPlan | None:
        """Classic VRP harvest: sell ATM strangle, buy wings at k*sigma_implied.

        Credit is rich (ATM theta), P(win) uses the FORECAST sigma (lower than
        implied when VRP > 0) -> positive Kelly edge by construction. Wings at
        1.0-1.3 sigma_impl keep the loss defined and the MC VaR gate happy.
        """
        def phi3(x: float) -> float:
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

        atm_put = _leg("P", spot)
        atm_call = _leg("C", spot)
        if not (atm_put and atm_call):
            return None
        best = None
        for k in (1.0, 1.15, 1.3):
            wing = sig_t_impl * k
            lp = _leg("P", spot - wing)
            lc = _leg("C", spot + wing)
            if not (lp and lc):
                continue
            atm_put.side, atm_call.side = "sell", "sell"
            lp.side, lc.side = "buy", "buy"
            credit = (atm_put.est_price + atm_call.est_price) - (lp.est_price + lc.est_price)
            w = wing  # one-side width to a wing
            if credit <= 0.5 or credit / w < 0.20:
                continue
            # P(win): S_T within +/- wing under FORECAST vol
            sigma_fc_t = max(signal.rv_forecast, 0.03) * math.sqrt(dte / 365.0)
            z = math.log((spot + wing) / spot) / sigma_fc_t
            p_win = 2.0 * phi3(z) - 1.0
            b = credit / max(w - credit, 1e-9)
            kedge = p_win * b - (1.0 - p_win)
            if kedge <= 0.05:
                continue
            cand = SpreadPlan(
                name="iron_fly", legs=[atm_put, lp, atm_call, lc], width=w, credit=credit,
                max_loss=w - credit, max_profit=credit,
                breakeven=spot - (wing - (w - credit)), dte=dte,
                rationale=f"VRP fly: ATM strangle {atm_put.est_price+atm_call.est_price:.2f}, "
                          f"wings {k:.1f}sig_impl, P(win){p_win:.0%}, kedge={kedge:.2f}")
            if best is None or kedge > best[0]:
                best = (kedge, cand)
        return best[1] if best else None

    def _condor() -> SpreadPlan | None:
        """Grid-search (offset, width); keep best Kelly edge with credit/width >= regime bar."""
        bar = 0.10 if signal.iv_rank_proxy < 0.4 else (0.20 if signal.iv_rank_proxy < 0.7 else 0.28)
        best = None
        for off_mult in (0.7, 1.0, 1.25, 1.5, 1.8, 2.2):
            for w_mult in (0.3, 0.5, 0.75, 1.0):
                put_off = offset * off_mult
                w = max(width * w_mult, 1.0)
                ps, pl = _leg("P", spot - put_off), _leg("P", spot - put_off - w)
                cs, cl = _leg("C", spot + put_off), _leg("C", spot + put_off + w)
                if not (ps and pl and cs and cl):
                    continue
                ps.side, pl.side = "sell", "buy"
                cs.side, cl.side = "sell", "buy"
                credit = (ps.est_price - pl.est_price) + (cs.est_price - cl.est_price)
                if credit <= 0.10 or credit / w < bar:
                    continue
                # Kelly edge for condor: P(within short strikes)
                sigma_t = max(signal.rv_forecast, 0.03) * math.sqrt(dte / 365.0)

                def phi2(x: float) -> float:
                    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

                z_lo = math.log((spot - put_off) / spot) / sigma_t
                z_hi = math.log((spot + put_off) / spot) / sigma_t
                p_win = phi2(z_hi) - phi2(z_lo)
                b = credit / max(w - credit, 1e-9)
                kedge = p_win * b - (1.0 - p_win)
                if kedge <= 0.01:
                    continue
                cand = SpreadPlan(
                    name="iron_condor", legs=[ps, pl, cs, cl], width=w, credit=credit,
                    max_loss=w - credit, max_profit=credit,
                    breakeven=spot - (put_off - (w - credit)), dte=dte,
                    rationale=f"VRP {signal.vrp*100:.1f}pts, off={put_off/spot*100:.1f}% w={w:.0f}, kedge={kedge:.2f}")
                if best is None or kedge > best[0]:
                    best = (kedge, cand)
        return best[1] if best else None

    def _search_credit(short_kind: str, name: str, rationale: str) -> SpreadPlan | None:
        """Grid-search offsets/widths; maximize KELLY EDGE subject to credit/width bar."""
        bar = 0.12 if signal.iv_rank_proxy < 0.4 else (0.24 if signal.iv_rank_proxy < 0.7 else 0.32)
        best = None
        for off_mult in (0.7, 1.0, 1.25, 1.5, 1.8, 2.2):
            for w_mult in (0.3, 0.5, 0.75, 1.0):
                w = max(width * w_mult, 1.0)
                sk = (spot - offset * off_mult) if short_kind == "P" else (spot + offset * off_mult)
                lk = sk - w if short_kind == "P" else sk + w
                p = _mk(short_kind, sk, lk, name, True, rationale)
                if p and p.credit / p.width >= bar:
                    kedge = _kelly_edge(p.credit, p.width, short_kind, sk)
                    if kedge <= 0.01:
                        continue
                    if best is None or kedge > best[0]:
                        best = (kedge, p)
        if best:
            best[1].rationale += f", kedge={best[0]:.2f}"
        return best[1] if best else None

    # ---- action dispatch ----
    if signal.action == "SELL_PREMIUM":
        if direction_bias > 0.15:
            return _search_credit("P", "bull_put_spread", f"VRP sell + bullish bias {direction_bias:+.2f}")
        if direction_bias < -0.15:
            return _search_credit("C", "bear_call_spread", f"VRP sell + bearish bias {direction_bias:+.2f}")
        fly = _iron_fly()
        if fly:
            return fly
        return _condor()

    if signal.action == "BUY_VOL":
        if direction_bias > 0.15:
            return _mk("C", spot + offset, spot + offset + width, "bull_call_spread", False,
                       f"IV<{signal.rv_forecast*100:.0f}%RV + bullish {direction_bias:+.2f}")
        if direction_bias < -0.15:
            return _mk("P", spot - offset, spot - offset - width, "bear_put_spread", False,
                       f"IV<{signal.rv_forecast*100:.0f}%RV + bearish {direction_bias:+.2f}")
        return None
    return None
