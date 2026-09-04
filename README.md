<div align="center">

<img src="docs/logo.png" alt="VULCAN" width="120"/>

# VULCAN — Autonomous VRP Options Desk

**An autonomous AI trading agent that harvests the variance risk premium from SPY options.**

*The edge was never the chart. The edge was the forecast.*

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Cloudflare](https://img.shields.io/badge/Cloudflare-Workers%20%2B%20KV-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)
![Alpaca](https://img.shields.io/badge/Alpaca-Paper%20Trading-FF6B1A?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)

[**Live Dashboard**](https://vulcan-dashboard.arechampionw.workers.dev) · [One-Page Write-Up](WRITEUP.md)

Built in **4 days** for the [lablab.ai × Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) — Options Alpha Agents track.

**Day 1 result: $100,000.00 → $100,335.37 (+0.34%), fully booked, fully flat.**

</div>

---

## Table of Contents

1. [The Story (plain English)](#the-story-plain-english)
2. [The Edge in One Sentence](#the-edge-one-sentence)
3. [How the Maths Works — Step by Step](#how-the-maths-works--step-by-step)
4. [The 7 Deterministic Risk Gates](#the-7-deterministic-risk-gates)
5. [The Six Bugs Our Own System Caught](#the-six-bugs-our-own-system-caught)
6. [Results — Day 1 Live Paper](#results--day-1-live-paper)
7. [The Dashboard](#the-dashboard)
8. [Repository Layout](#repository-layout)
9. [Quick Start](#quick-start)
10. [The 4-Day Build Log](#the-4-day-build-log)
11. [Honest Assumptions](#honest-assumptions)
12. [Tech Stack](#tech-stack)
13. [License & Disclaimer](#license--disclaimer)

---

## The Story (plain English)

Every option contract carries a price for volatility insurance built into it.
Sometimes the market charges **more** for that insurance than the math says it is
worth. That gap is called the **variance risk premium (VRP)** — one of the most
documented, most persistent edges in quantitative finance.

Think of it like a shop that only opens when customers overpay.

VULCAN is that shop. It runs on its own:

1. **Forecasts** what volatility should be (three classic models vote)
2. **Reads** what the market is charging right now (live SPY option chain)
3. **Measures** the gap between the two
4. **Debates itself** — one AI argues to take the trade, another argues to kill it, a third can only veto or shrink it
5. **Simulates 32,768 futures** for the trade before risking a cent
6. **Only then** does it place a defined-risk order — with hard-coded limits that no AI can override

If the gap is not wide enough, the shop stays closed. Doing nothing is a feature.

---

## The Edge (one sentence)

> *"The edge is always the IV vs RV forecast — everything else is execution."*

Implied volatility is the market's price of risk. Realized volatility is what
actually happens. When IV > forecast RV, insurance is overpriced — sell it.
When IV < forecast RV, insurance is cheap — buy it. VULCAN quantifies that gap
every cycle and structures defined-risk trades around it.

---

## How the Maths Works — Step by Step

Every formula below is implemented in `vulcan/`. Under each one is what it means in plain English.

### Step 1 — What is volatility?

Volatility is how wildly a stock price swings. Every option has a volatility
price baked in — **implied volatility (IV)** is what the market *charges*.
**Realized volatility (RV)** is what the stock *actually does*.

The whole system trades the difference between those two numbers.

### Step 2 — The forecast (Model 1: `vol_forecaster.py`)

Three classic academic models vote on tomorrow's volatility:

| Model | Formula | Plain English |
|-------|---------|---------------|
| **HAR-RV** | `RV[t+1] = c + b_d·RV_day + b_w·RV_week + b_m·RV_month` | Yesterday, last week and last month each get a vote on tomorrow's swings |
| **GARCH(1,1)** | `σ²[t] = ω + α·ε²[t-1] + β·σ²[t-1]` | Calm days follow calm days, wild days follow wild days — and shocks decay |
| **Kalman filter** | `x = x_prior + K·(z − H·x_prior)` | Blend yesterday's belief with today's observation, weighted by trust |

The three forecasts are averaged into **one number per asset**. That number is the edge.

On top sit:
- A **2-state Gaussian HMM** that classifies the market as `calm` or `stress` (no premium selling in stress — ever)
- **qlib-Alpha158 momentum features** that add a directional bias so the structure leans the right way

### Step 3 — The gap = the trade (Model 2: `pricer.py`)

```
VRP = implied volatility (what the market charges)
     − forecast volatility (what it is actually worth)
```

- **VRP > 0** → market overcharges for insurance → **SELL premium**
- **VRP < 0** → insurance is cheap → **BUY it**
- VULCAN only fires when the gap clears a hard threshold (converged: `0.015`)

Live day-one example: **IV 10.7% vs forecast 8.6% → VRP +2.2 points → sell premium.**

### Step 4 — Pricing every strike (Black-Scholes)

```
C = S·N(d1) − K·e^(−rT)·N(d2)
d1 = (ln(S/K) + (r + σ²/2)·T) / (σ·√T)
d2 = d1 − σ·√T
```

*Plain English:* the fair price of an option today, from the strike, time left,
and volatility. Used both to sanity-check live quotes and to price backtest entries.

### Step 5 — The geometry trick (where the VRP thesis lives)

This is the heart of the strategy. Short strikes are placed at
**IMPLIED-sigma distances** (where the credit is rich), but the win probability
is computed with the **FORECAST sigma** (lower when VRP > 0):

```
wing   = spot × σ_implied × k            # where the market pays rich credit
σ_t    = σ_forecast × √(dte/365)         # what we believe will actually happen
p_win  = N(ln((S+wing)/S) / σ_t) × 2 − 1 # probability under OUR forecast
```

Because forecast vol < implied vol when VRP > 0, the structure has a **positive
Kelly edge by construction**. We are paid at implied prices and win at forecast
probabilities. That is the VRP harvest in one paragraph.

### Step 6 — The structures (defined risk ONLY)

| Structure | Construction | When it fires |
|-----------|--------------|---------------|
| **Iron fly** | Sell ATM strangle, buy wings at ±1σ_implied | Neutral bias + rich VRP — the classic harvest |
| **Iron condor** | Sell OTM strangle, buy wider wings | Neutral bias, want more safety |
| **Credit spreads** | Directional premium, bounded loss | Momentum bias present |

Every structure has maximum loss known in advance. No naked exposure. Ever.

The day-one iron fly payoff:

```
P&L
      +7.94 ────╮                  ╭──── +7.94   (max profit = credit)
                ╰────────────────╯
              751      764      777      (strikes)
max loss = 4.87 per contract, defined by construction
```

### Step 7 — The self-improving backtest loop (`loop_runner.py`)

The model never trusts itself. The research loop runs until convergence:

1. **Generate** — parameter grid over strike offsets, widths, VRP thresholds
2. **Backtest walk-forward** — every signal uses ONLY past data. Zero leakage
3. **Score** — monthly **ICIR** (kill < 0.3), Sharpe, profit factor, signal half-life (kill < 5d)
4. **Analyze** — failure modes feed the next round's grid
5. **Gate** — last 25% of data held out; survivors need **OOS Sharpe ≥ 60% of IS**, positive edge, and a **deflated-Sharpe** multiple-testing correction
6. **Repeat** — until parameters stop moving. Stability is the stop condition

**504 backtests over 4 rounds.** Converged region: ~0.65σ implied offset,
0.4σ width, VRP threshold 0.015, IV markup 1.18 — stable across rounds, OOS P&L positive.

No cherry-picking. The model has to prove itself to itself.

### Step 8 — The Monte Carlo engine (`montecarlo.py`, risk gate G3)

Before any order, the trade's full P&L distribution is simulated with **32,768 paths**:

```
S_T = S₀ · exp((r − q − σ²/2)·T + σ·√T·Z)      # exact GBM, zero discretization bias
```

Variance-reduction stack (all four, verified ~3× reduction):

| Technique | What it buys |
|-----------|--------------|
| **Antithetic variates** | Every path redrawn mirrored — variance halves |
| **Control variates** | Anchored to the exact Black-Scholes value, optimal β = cov/var |
| **Sobol quasi-random sequences** | Low-discrepancy sampling covers the space evenly |
| **Moment matching** | Sample mean/variance forced exact |

Convergence law verified empirically: **SE halves as paths ×4 (O(1/√N))**.
The engine cross-checks MC price vs exact BS (inside the 95% CI), computes
portfolio **99% VaR and CVaR per trade**, and includes a CVA module.

The trade dies if simulated tail losses exceed the defined max. This gate
caught and fixed a real sign bug during development — it keeps the model honest.

### Step 9 — Kelly sizing (`risk.py`, gate G4)

Position size follows **quarter-Kelly** from the structural win probability
implied by Model 1's forecast distribution:

```
b          = credit / (max_loss − credit)          # payoff odds
f*         = (p_win·(b+1) − 1) / b                 # full-Kelly fraction
contracts  = equity · 0.25 · f* / (max_loss · 100) # quarter-Kelly, per-contract cost
```

*Plain English:* bet the size where long-run growth is maximized — then cut it
to a quarter, because real markets punish overconfidence. Probabilities below
the **0.55 floor are refused, never inflated**. Sizing is then clamped by the
exposure gates.

### Step 10 — The LLM debate (Model 3: `agent.py`)

A multi-agent pipeline (TradingAgents pattern) on Cloudflare Workers AI:

- **GLM-5.2 analysts** brief two adversarial agents
- **Bull agent** argues why the trade should be taken
- **Bear agent (Kimi-K2.7)** argues why it should be killed — adversarial by design
- **GLM-5.3-Flash PM** reads both briefs and issues the verdict

**The LLM can only VETO or SHRINK a trade — never grow risk.** If the LLM is
unreachable, the system fails closed to the deterministic decision. Every
debate transcript is logged and visible live on the dashboard. No black box.

### Step 11 — The 15-minute autonomous cycle (`main.py`)

Every 15 minutes, one idempotent cycle runs:

```
forecast → VRP signal → structure → Monte Carlo → Kelly → LLM debate
→ execute (Alpaca mleg) → manage exits → journal → dashboard push
```

Idempotent means: if a cycle fails, the next one recovers cleanly. No double orders.

### Step 12 — Execution on Alpaca (`executor.py`, `equity_sleeve.py`)

All trading on a fresh $100,000 Alpaca paper account via the Trading API:

- Live SPY option chains and IV snapshots from `data.alpaca.markets` (~10k contracts with IV + greeks)
- Multi-leg iron flys as single **mleg limit orders** (net-price convention, bounded slippage)
- Bracket orders (stop + trail) for the long/short equity sleeve
- `/v2/clock` market-hours gating — the agent only acts when the market acts

---

## The 7 Deterministic Risk Gates

Pure math. Cannot be overridden by any model output, human or AI:

| Gate | Rule | Plain English |
|------|------|---------------|
| **G1** | Defined risk only | Max loss known in advance, bounded by construction |
| **G2** | Turbulence gate | No entries when VIX spikes or the HMM reads stress |
| **G3** | Monte Carlo VaR | 32,768 paths per trade — tail losses must stay inside the defined max |
| **G4** | Quarter-Kelly sizing | Honest win probability only. Below 0.55 → refuse, never inflate |
| **G5** | Exposure caps | 1.5% NAV per trade, 6% across the whole book |
| **G6** | Daily circuit breaker | 2% NAV daily loss → trading halts |
| **G7** | Discipline exits | Take profit at 60% of max gain, cut at 75% of max loss, roll inside 2 DTE |

A 3σ gap-day stress test backstops G3. The AI proposes. Math disposes.

---

## The Six Bugs Our Own System Caught

We list these because honesty is the product. During development, VULCAN's own
risk system caught its creator — six times:

| # | Bug | How it was caught | Fix |
|---|-----|-------------------|-----|
| 1 | Market guard checked a field that doesn't exist in Alpaca's API | Bot thought market was ALWAYS closed while the market was open | Switched to the `/v2/clock` endpoint |
| 2 | Kelly floor **inflated** low probabilities (0.34 → 0.55 → approved 1,383 contracts!) | Diagnostic run showed absurd sizing | If P < 0.55 → refuse. Never inflate |
| 3 | Strategy builder and risk gate disagreed on win probability | Same plan, opposite verdicts | Both now share ONE structural objective |
| 4 | Monte Carlo signs inverted — simulated losses exceeded the defined max (impossible) | **G3 gate vetoed the trade and exposed the bug** | Corrected P&L signs, hand-verified |
| 5 | A breach cap contradicted fly geometry by construction | Fly structures always failed one gate | G3 = model integrity; G4 = profitability |
| 6 | mleg orders used the wrong REST field name (`order_type` vs `type`) → HTTP 422 | Captured the exact Alpaca error body | Fixed, verified with a real accepted order |

The Monte Carlo gate catching bug #4 is the point of the whole design:
the system verifies itself before it risks a cent.

---

## Results — Day 1 Live Paper

| Metric | Value |
|--------|-------|
| Start equity | $100,000.00 |
| End equity (day 1, booked flat) | **$100,335.37** |
| Structure | Iron fly: sell 764P + 764C, buy 751P + 777C wings |
| Entry context | IV 10.7% vs forecast 8.6% (VRP +2.2) |
| Credit / max loss per contract | $7.94 / $4.87 |
| Max premium at risk | 1.37% NAV (gate G5) |
| Autonomous cycles logged | 47 (every 15 min) |

Exit ledger:

| Leg | Action | P&L |
|-----|--------|-----|
| Short 765P | Closed — SPY dropped, put side won | **+$430** |
| Long 779C | Closed — wing captured value | **+$142** |
| Long 752P | Closed — hedge cost | −$204 |
| Short 765C | Cut early per risk discipline | −$62 |
| **Net day 1** | **Fully booked, fully flat** | **+$335.37** |

The math worked exactly as designed: the fly was short premium at IV 10.7%
vs forecast 8.6% — SPY's realized vol came in below implied, the short put
decayed +430, and every exit was executed through the verified mleg path.

---

## The Dashboard (React + TypeScript + Vite)

8 pages, neobrutalism design, live on Cloudflare Workers + KV:

| Page | What you see |
|------|--------------|
| Overview | Equity/P&L KPIs, vol-forecast bars, VRP panel, MC VaR, cycle log |
| Positions | Live Alpaca positions + orders (mleg class visible) |
| Trades | Full journal: legs, credit, VRP at entry, agent verdict |
| Agent Brain | The actual bull/bear/PM debate transcripts, word for word |
| Backtest Loop | Rounds, best variant, ICIR/OOS/DSR + **Run Loop button** with live progress |
| Monte Carlo | Fan chart (32k paths), P&L histogram with VaR/CVaR markers, convergence plot, tornado — **interactive sliders + Run Simulation** |
| Risk Gates | The 7-gate constitution + authority chain |
| Data & Models | Data sources, honest backtest assumptions, upgrade path |

**Live:** https://vulcan-dashboard.arechampionw.workers.dev

An AI agent that trades with nobody watching needs to be watched by everybody.

---

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

---

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

---

## The 4-Day Build Log

| Day | Shipped |
|-----|---------|
| **Day 1** | Vol forecaster (HAR + GARCH + Kalman + HMM), VRP signal, structure builder, 7 risk gates, Alpaca execution path — **first live iron fly filled, day closed +0.34%** |
| **Day 2** | Monte Carlo engine (GBM exact + 4 variance-reduction techniques + VaR/CVaR), Kelly sizing unified with builder, 6 real bugs found and fixed by the gates |
| **Day 3** | Loop engineering: 504 walk-forward backtests over 4 rounds → converged parameters; dashboard live on Cloudflare with 8 pages |
| **Day 4** | Self-improving loop wired to the dashboard Run button with live progress, interactive Monte Carlo lab, submission materials |

---

## Honest Assumptions

- The backtest settles **synthetic condors**: entry priced by Black-Scholes at
  IV = RV20 × markup, settled European-style, with documented frictions
  ($0.65/leg + 25% credit slippage). This is the standard pedagogical VRP method —
  assumptions stated, not hidden.
- Live data = Alpaca IEX (15-min delayed, ~2% tape volume — closes accurate) +
  Alpaca indicative option chains (IV + greeks on ~10k SPY contracts).
- **#1 upgrade path**: Polygon.io free tier (2y real EOD option prices) to convert
  model validation into market validation. CBOE free VIX CSVs feed the turbulence gate.
- Paper trading results are hypothetical and do not guarantee future returns.

---

## Tech Stack

Python 3.11 (alpaca-py, pandas, numpy, scipy, statsmodels, arch, hmmlearn, scikit-learn)
· React 18 + TypeScript + Vite + Recharts · Cloudflare Workers + KV ·
Cloudflare Workers AI (GLM-5.3-Flash / GLM-5.2 / Kimi-K2.7)

---

## License

MIT — see [LICENSE](LICENSE).

---

## Disclaimer

Educational hackathon project. Paper trading only. Nothing here is financial
advice. Options involve substantial risk of loss.
