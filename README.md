# VULCAN — Autonomous VRP Options Desk

> An autonomous AI trading agent that harvests the **variance risk premium (VRP)**:
> it forecasts realized volatility with real math, compares it to what the options
> market is charging (implied volatility), and sells premium only when the gap
> clears deterministic risk gates.

Built for the [lablab.ai × Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) —
Options Alpha Agents track. Trades on Alpaca **paper trading** ($100,000 fresh account).

**Live dashboard:** https://vulcan-dashboard.arechampionw.workers.dev

---

## The Edge (one sentence)

> *"The edge is always the IV vs RV forecast — everything else is execution."*

Implied volatility is the market's price of risk. Realized volatility is what
actually happens. When IV > forecast RV, insurance is overpriced — sell it.
When IV < forecast RV, insurance is cheap — buy it. VULCAN quantifies that gap
every cycle and structures defined-risk trades around it.

## Architecture — The 3-Model Brain

```
┌─────────────────────────────────────────────────────────────────┐
│  MODEL 1 — VOL FORECASTER (the quant brain)                     │
│  HAR-RV + GARCH(1,1) + Kalman filter ensemble → σ̂ forecast      │
│  + HMM 2-state regime detection + qlib-Alpha158 direction       │
├─────────────────────────────────────────────────────────────────┤
│  MODEL 2 — PRICER + STRATEGY LOOP (the math brain)              │
│  Black-Scholes greeks · VRP signal = ATM IV − σ̂ forecast        │
│  Iron fly / condors / credit spreads — defined risk ONLY        │
│  Kelly-aware strike grid search (builder & gate share one       │
│  objective) · Loop engineering: generate → walk-forward         │
│  backtest → ICIR score → failure analysis → refine →            │
│  out-of-sample gate + deflated Sharpe                           │
├─────────────────────────────────────────────────────────────────┤
│  MODEL 3 — LLM DECISION AGENT (the reasoning brain)             │
│  TradingAgents pattern on Cloudflare Workers AI:                │
│  PM = GLM-5.3-Flash · analysts = GLM-5.2 · bear = Kimi-K2.7     │
│  Bull/bear adversarial debate → PM verdict: VETO or SHRINK only │
├─────────────────────────────────────────────────────────────────┤
│  DETERMINISTIC RISK GATES — pure math, cannot be overridden     │
│  G1 defined-risk · G2 VIX/turbulence · G3 Monte-Carlo VaR       │
│  G4 quarter-Kelly · G5 exposure caps · G6 daily breaker ·       │
│  G7 concentration + exit rules                                  │
├─────────────────────────────────────────────────────────────────┤
│  EXECUTOR — Alpaca mleg limit orders · bracket orders for the   │
│  equity long/short sleeve · SQLite-style JSON state journal     │
└─────────────────────────────────────────────────────────────────┘
```

## The Monte Carlo Engine

Every trade is stress-tested before submission with a full simulation engine
(`vulcan/montecarlo.py`):

- **GBM exact solution** — `S_T = S₀·exp((r−q−σ²/2)T + σ√T·Z)` (zero discretization bias)
- **Variance reduction stack**: antithetic variates, control variates (optimal
  β = cov/var against the analytic BS value), Sobol quasi-random sequences,
  moment matching → ~3× variance reduction, verified
- **Convergence law verified empirically**: SE halves as paths ×4 (O(1/√N))
- **Applications wired in**: option-pricing cross-check (MC vs BS exact, inside 95% CI),
  portfolio 99% VaR/CVaR per trade (risk gate G3), CVA module for OTC-style books

## The Loop Engineering (self-improving backtest)

`python -m vulcan.loop_runner` runs the full research loop until convergence:

1. **Generate** — parameter grid over strike offsets/widths/VRP thresholds
2. **Backtest** — walk-forward with zero leakage (every signal uses only past data),
   real frictions (fees per leg + credit slippage)
3. **Score** — monthly ICIR (kill < 0.3), Sharpe, profit factor, signal half-life (kill < 5d)
4. **Analyze** — failure modes feed the next round's grid
5. **Gate** — last 25% of data held out; survivors need OOS Sharpe ≥ 60% of IS,
   positive edge, and a deflated-Sharpe multiple-testing correction

Final converged region: ~0.65σ implied offset, 0.4σ width, VRP threshold 0.015,
IV markup 1.18 — stable across rounds, OOS P&L positive.

## The Dashboard (React + TypeScript + Vite)

8 pages, neobrutalism design, live on Cloudflare Workers + KV:

| Page | What you see |
|------|--------------|
| Overview | Equity/P&L KPIs, vol-forecast bars, VRP panel, MC VaR, cycle log |
| Positions | Live Alpaca positions + orders (mleg class visible) |
| Trades | Full journal: legs, credit, VRP at entry, agent verdict |
| Agent Brain | The actual bull/bear/PM debate transcripts |
| Backtest Loop | Rounds, best variant, ICIR/OOS/DSR + **Run Loop button** with live progress |
| Monte Carlo | Fan chart (32k paths), P&L histogram with VaR/CVaR markers, convergence plot, tornado — **with interactive sliders + Run Simulation** |
| Risk Gates | The 7-gate constitution + authority chain |
| Data & Models | Data sources, honest backtest assumptions, upgrade path |

## Repository Layout

```
vulcan/
├── vulcan/                 # Python package (the agent)
│   ├── data.py             # Alpaca REST client (single source of data truth)
│   ├── vol_forecaster.py   # MODEL 1: HAR + GARCH + Kalman + HMM + features
│   ├── pricer.py           # MODEL 2: BS greeks, IV extraction, VRP signal,
│   │                       #   Kelly-aware structure constructor
│   ├── montecarlo.py       # GBM + variance reduction + VaR/CVaR + CVA
│   ├── risk.py             # 7 deterministic gates + Kelly sizing
│   ├── agent.py            # MODEL 3: LLM debate pipeline (Cloudflare Workers AI)
│   ├── executor.py         # mleg / bracket / close order submission
│   ├── equity_sleeve.py    # long/short equity overlay (options stay the core)
│   ├── loop_runner.py      # the loop-engineering engine (ICIR + OOS + DSR)
│   ├── strategy_loop.py    # v1 loop (walk-forward, deflated Sharpe)
│   ├── remote.py           # dashboard job poller (KV job queue bridge)
│   └── main.py             # orchestrator: one idempotent cycle
├── dashboard/              # React + TypeScript + Vite app
│   └── src/pages/          # 8 pages incl. MonteCarlo.tsx (recharts)
├── worker/worker.js        # Cloudflare Worker: /api/all, /api/mc, job queue,
│                           #   KV state push + serves the built dashboard
├── wrangler.toml           # Worker config (assets + KV binding)
├── WRITEUP.md              # the required one-page write-up
└── .env.example            # template — real keys live ONLY in local .env
```

## Quick Start

```bash
# 1. Python 3.11 venv + deps
py -3.11 -m venv venv
venv\Scripts\pip install alpaca-py pandas numpy scipy statsmodels scikit-learn arch hmmlearn python-dotenv tabulate requests

# 2. Secrets (never committed)
copy .env.example .env        # fill in your Alpaca paper keys

# 3. One trading cycle (safe, idempotent)
venv\Scripts\python -m vulcan.main --dry-run     # dry run first
venv\Scripts\python -m vulcan.main               # live paper cycle

# 4. The backtest loop (self-improving, until convergence)
venv\Scripts\python -m vulcan.loop_runner

# 5. Monte Carlo engine demo
venv\Scripts\python -m vulcan.montecarlo

# 6. Dashboard (React+TS+Vite -> Cloudflare Worker)
cd dashboard && npm install && npm run build && cd ..
npx wrangler deploy
```

## Results (Day 1, live paper)

| Metric | Value |
|--------|-------|
| Start equity | $100,000.00 |
| End equity (day 1, booked flat) | **$100,335.37** |
| Structure | Iron fly: sell ATM strangle @ IV 10.7% vs forecast 8.6% |
| Max premium at risk | 1.37% NAV (gate G5) |
| Exits | Rule-based + manual book: +430 short-put, +142 wing, −204 hedge, −62 cut leg |
| Cycles logged | 47 (every 15 min, fully autonomous) |

## Honest Assumptions (read this)

- The backtest settles **synthetic condors**: entry priced by Black-Scholes at
  IV = RV20 × markup, settled European-style, with documented frictions
  ($0.65/leg + 25% credit slippage). This is the standard pedagogical VRP method —
  assumptions stated, not hidden.
- Live data = Alpaca IEX (15-min delayed, ~2% tape volume — closes accurate) +
  Alpaca indicative option chains (IV + greeks on ~10k SPY contracts).
- **#1 upgrade path**: Polygon.io free tier (2y real EOD option prices) to convert
  model validation into market validation. CBOE free VIX CSVs feed the turbulence gate.
- Paper trading results are hypothetical and do not guarantee future returns.

## Tech Stack

Python 3.11 (alpaca-py, pandas, numpy, scipy, statsmodels, arch, hmmlearn, scikit-learn)
· React 18 + TypeScript + Vite + Recharts · Cloudflare Workers + KV ·
Cloudflare Workers AI (GLM-5.3-Flash / GLM-5.2 / Kimi-K2.7)

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Educational hackathon project. Paper trading only. Nothing here is financial
advice. Options involve substantial risk of loss.
