"""VULCAN Model 1 — Volatility Forecaster.

Ensemble of three established vol models (see stefan-jansen ML4T ch.9, FMNM 5.3):
  1. HAR-RV          — heterogeneous autoregressive realized vol (practitioner standard)
  2. GARCH(1,1)      — conditional vol via `arch`
  3. Kalman filter   — local-level state estimate of log-RV (sequential)

Plus a 2-state Gaussian HMM regime label (bull/chop vs stress) used as a
position-sizing gate, and qlib-Alpha158-style momentum features for direction bias.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


# ---------------- realized volatility ----------------
def realized_vol(close: pd.Series, window: int = 1, annualize: bool = True) -> pd.Series:
    """Parkinson-style close-to-close realized vol over `window` days, annualized."""
    logret = np.log(close / close.shift(1))
    rv = logret.rolling(window).std() * np.sqrt(252) if annualize else logret.rolling(window).std()
    return rv


# ---------------- 1. HAR-RV ----------------
def har_rv_forecast(rv_daily: pd.Series) -> float:
    """Fit HAR: RV_t+1 = b0 + b1*RV_d + b2*RV_w + b3*RV_m. Returns next-step forecast (annualized)."""
    rv = rv_daily.dropna()
    if len(rv) < 60:
        return float(rv.iloc[-1]) if len(rv) else 0.20
    df = pd.DataFrame({
        "rv_d": rv,
        "rv_w": rv.rolling(5).mean(),
        "rv_m": rv.rolling(22).mean(),
    }).dropna()
    df["y"] = df["rv_d"].shift(-1)
    df = df.dropna()
    X = np.column_stack([np.ones(len(df)), df["rv_d"], df["rv_w"], df["rv_m"]])
    y = df["y"].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    x_next = np.array([1.0, rv.iloc[-1], rv.rolling(5).mean().iloc[-1], rv.rolling(22).mean().iloc[-1]])
    return float(np.clip(x_next @ beta, 0.02, 3.0))


# ---------------- 2. GARCH(1,1) ----------------
def garch_vol_forecast(returns: pd.Series) -> float:
    """GARCH(1,1) one-step-ahead conditional vol forecast (annualized)."""
    try:
        from arch import arch_model
        r = (returns.dropna() * 100).astype(float)
        if len(r) < 100:
            return float(returns.std() * np.sqrt(252))
        am = arch_model(r, vol="GARCH", p=1, q=1, mean="Constant", rescale=False)
        res = am.fit(disp="off", show_warning=False)
        fc = res.forecast(horizon=1, reindex=False)
        var_next = float(fc.variance.values[-1][0]) / 1e4  # back from pct^2
        return float(np.clip(np.sqrt(var_next * 252), 0.02, 3.0))
    except Exception:
        return float(returns.std() * np.sqrt(252))


# ---------------- 3. Kalman local-level on log-RV ----------------
def kalman_vol_forecast(rv_daily: pd.Series, q: float = 1e-5, r: float = 2e-3) -> float:
    """Local-level Kalman filter over log realized vol; return exp(state) (annualized)."""
    rv = rv_daily.dropna()
    if len(rv) < 30:
        return float(rv.iloc[-1]) if len(rv) else 0.20
    y = np.log(np.maximum(rv.values, 1e-4))
    x = y[0]
    p = 1.0
    for obs in y[1:]:
        p_pred = p + q          # state prediction
        k = p_pred / (p_pred + r)  # Kalman gain
        x = x + k * (obs - x)   # update
        p = (1 - k) * p_pred
    return float(np.clip(np.exp(x), 0.02, 3.0))


# ---------------- regime (HMM 2-state, with vol-ratio fallback) ----------------
def regime_label(close: pd.Series) -> dict:
    """2-state regime: 'calm' vs 'stress'. HMM on (returns, vol ratio); fallback to quantiles."""
    ret = close.pct_change().dropna()
    if len(ret) < 120:
        return {"regime": "unknown", "prob_stress": 0.5}
    vol5 = realized_vol(close, 5)
    vol20 = realized_vol(close, 20)
    ratio = (vol5 / vol20).reindex(ret.index).fillna(1.0)
    feats = np.column_stack([ret.values * 100, ratio.values])

    regime, p_stress = "unknown", 0.5
    try:
        from hmmlearn.hmm import GaussianHMM
        X = feats[:-1]
        if len(X) >= 100:
            m = GaussianHMM(n_components=2, covariance_type="full", n_iter=200, random_state=42)
            m.fit(X)
            _, states = m.decode(X)
            # identify stress state = higher mean |ret|*ratio composite
            s0 = np.mean(np.abs(X[states == 0, 0]) * X[states == 0, 1])
            s1 = np.mean(np.abs(X[states == 1, 0]) * X[states == 1, 1])
            stress_state = 1 if s1 > s0 else 0
            probs = m.predict_proba(X[-1:])
            p_stress = float(probs[0][stress_state])
            regime = "stress" if states[-1] == stress_state else "calm"
    except Exception:
        r = ratio.iloc[-1]
        p_stress = float(np.clip((r - 0.8) / 0.6, 0, 1))
        regime = "stress" if r > 1.1 else "calm"

    return {"regime": regime, "prob_stress": p_stress}


# ---------------- direction features (qlib Alpha158 subset) ----------------
def direction_features(close: pd.Series, volume: pd.Series | None = None) -> dict:
    """ROC5, RSV10, CNTP5, KMID-lite, CORR10 — the robust Alpha158 short-horizon factors."""
    c = close
    roc5 = (c / c.shift(5) - 1).iloc[-1]
    hh10, ll10 = c.rolling(10).max().iloc[-1], c.rolling(10).min().iloc[-1]
    rsv10 = (c.iloc[-1] - ll10) / max(hh10 - ll10, 1e-9)
    up5 = (c.diff() > 0).tail(5).mean()
    body = ((c - c.shift(1)) / c.shift(1)).abs().tail(5).mean()
    corr10 = None
    if volume is not None:
        lv, lr = np.log(volume + 1), c.pct_change()
        if lv.tail(11).notna().all() and lr.tail(11).notna().all():
            corr10 = float(np.corrcoef(lr.tail(10), lv.tail(10))[0, 1])
    return {
        "roc5": float(roc5) if pd.notna(roc5) else 0.0,
        "rsv10": float(rsv10) if pd.notna(rsv10) else 0.5,
        "cntp5": float(up5) if pd.notna(up5) else 0.5,
        "kmid5": float(body) if pd.notna(body) else 0.0,
        "corr10": corr10,
    }


# ---------------- ensemble ----------------
@dataclass
class VolForecast:
    har: float
    garch: float
    kalman: float
    ensemble: float          # weighted blend
    realized_20: float
    rv_ratio: float          # vol5/vol20 expansion signal
    regime: dict = field(default_factory=dict)
    direction: dict = field(default_factory=dict)
    direction_bias: float = 0.0   # -1..+1


def forecast(close: pd.Series, volume: pd.Series | None = None) -> VolForecast:
    rets = close.pct_change()
    # daily realized-vol proxy: |logret| * sqrt(252)  (standard HAR input on daily bars)
    rv_daily = (np.log(close / close.shift(1)).abs() * np.sqrt(252)).replace([np.inf, -np.inf], np.nan)
    rv5 = realized_vol(close, 5)
    rv20 = realized_vol(close, 20)

    har = har_rv_forecast(rv_daily)
    garch = garch_vol_forecast(rets)
    kal = kalman_vol_forecast(rv_daily)

    # weights: HAR is the known-best short-horizon RV forecaster; GARCH reacts to shocks;
    # Kalman smooths. Equal-ish but HAR-tilted.
    ensemble = 0.4 * har + 0.35 * garch + 0.25 * kal

    ratio = (rv5.iloc[-1] / max(rv20.iloc[-1], 1e-9)) if pd.notna(rv5.iloc[-1]) and pd.notna(rv20.iloc[-1]) else 1.0
    reg = regime_label(close)
    dfeat = direction_features(close, volume)

    # direction bias: blend momentum (ROC5), range position (RSV10), up-day count (CNTP5)
    bias = np.tanh(3.0 * dfeat["roc5"]) * 0.45 + (dfeat["rsv10"] - 0.5) * 0.35 + (dfeat["cntp5"] - 0.5) * 0.35
    if dfeat.get("corr10") is not None:
        bias += np.tanh(dfeat["corr10"]) * 0.10
    bias = float(np.clip(bias, -1, 1))

    return VolForecast(
        har=har, garch=garch, kalman=kal, ensemble=ensemble,
        realized_20=float(rv20.iloc[-1]) if pd.notna(rv20.iloc[-1]) else 0.20,
        rv_ratio=float(ratio),
        regime=reg, direction=dfeat, direction_bias=bias,
    )


if __name__ == "__main__":
    from vulcan import data as d
    import pandas as pd

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
