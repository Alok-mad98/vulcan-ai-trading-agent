# -*- coding: utf-8 -*-
"""Generate the final professional README.md for the vulcan repo. Clean ASCII only."""
from pathlib import Path

DOC = """# VULCAN - Autonomous VRP Options Desk

> An autonomous AI trading agent that harvests the **variance risk premium (VRP)**:
> it forecasts realized volatility with real math, compares it to what the options
> market is charging (implied volatility), and sells premium only when the gap
> clears deterministic risk gates.

Built for the [lablab.ai x Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) -
Options Alpha Agents track. Trades on Alpaca **paper trading** ($100,000 fresh account).

**Live dashboard:** https://vulcan-dashboard.arechampionw.workers.dev

**Full source:** https://github.com/Alok-mad98/vulcan-ai-trading-agent

---

## The Edge (one sentence)

> *"The edge is always the IV vs RV forecast - everything else is execution."*

Implied volatility is the market's price of risk. Realized volatility is what
actually happens. When IV > forecast RV, insurance is overpriced - sell it.
When IV < forecast RV, insurance is cheap - buy it. VULCAN quantifies that gap
every cycle and structures defined-risk trades around it.

---

## How the Maths Works (simple language)

**Step 1 - What is volatility?**
Volatility is how wildly a stock price swings. High volatility means big swings.
Every options contract has a price for volatility built into it. That price is
called **implied volatility (IV)** - it is what the market CHARGES for insurance.

**Step 2 - The forecast (Model 1)**
VULCAN forecasts what volatility SHOULD be using three classic models that vote:

- **HAR-RV** - looks at realized swings over day, week and month windows
- **GARCH(1,1)** - conditional volatility: calm days follow calm days, wild follows wild
- **Kalman filter** - sequential state estimate, updates the forecast with every new data point

Three models vote, the average wins: one forecast number per asset.

**Step 3 - The gap = the trade (Model 2)**
The **variance risk premium (VRP)** is simply:

```
VRP = implied volatility (what market charges) - forecast volatility (what it's worth)
```

- VRP > 0 means the market overcharges for insurance - SELL premium
- VRP < 0 means insurance is cheap - BUY it

VULCAN only opens when the gap clears the deterministic threshold.

**Step 4 - Pricing the structure**
Every strike is priced with **Black-Scholes**:

```
C = S*N(d1) - K*exp(-rT)*N(d2)
d1 = (ln(S/K) + (r + sigma^2/2)*T) / (sigma*sqrt(T))
d2 = d1 - sigma*sqrt(T)
```

The geometry is where the VRP thesis lives: short strikes are placed at
IMPLIED-sigma distances (where credit is rich), while the win probability is
computed with the FORECAST sigma (lower when VRP > 0) - positive Kelly edge
by construction.

**Step 5 - The structures (defined risk ONLY)**
- **Iron fly** - sell ATM strangle, buy wings at +/-1 sigma implied. Classic VRP harvest
- **Iron condor** - sell OTM strangle, buy wider wings. Rich credit, wider safety
- **Credit spreads** - directional premium with bounded loss

Every structure has maximum loss known in advance. No naked exposure. Ever.

**Step 6 - The self-improving backtest loop (loop engineering)**
The model never trusts itself. The research loop runs until convergence:

1. **Generate** - parameter grid over strike offsets, widths, VRP thresholds
2. **Backtest walk-forward** - every signal uses ONLY past data. Zero leakage
3. **Score** - monthly ICIR (kill < 0.3), Sharpe, profit factor, signal half-life
4. **Analyze** - failure modes feed the next round's grid
5. **Gate** - last 25% of data held out; survivors need OOS Sharpe >= 60% of IS,
   positive edge, and a deflated-Sharpe multiple-testing correction

Final converged region: ~0.65 sigma implied offset, 0.4 sigma width,
VRP threshold 0.015, IV markup 1.18 - stable across rounds, OOS P&L positive.

**Step 7 - The Monte Carlo engine (Model 2 risk gate)**
Every trade is stress-tested with **32,768 simulated price paths**:

- GBM exact solution: `S_T = S_0 * exp((r - q - sigma^2/2)*T + sigma*sqrt(T)*Z)`
- Antithetic variates - every path redrawn mirrored, variance halves
- Control variates - anchored to the analytic Black-Scholes value
- Sobol quasi-random sequences - low-discrepancy sampling
- Moment matching - exact mean and variance

Variance reduction ~3x, verified. Convergence law O(1/sqrt(N)) verified
empirically: SE halves as paths x4. The engine computes the full P&L
distribution, portfolio 99% VaR and CVaR per trade - the trade dies if
simulated losses exceed the defined max. It caught and fixed a real sign
bug during development. This is the gate that keeps the model honest.

**Step 8 - Kelly sizing (Model 2 position gate)**
Position size follows **quarter-Kelly** from the structural win probability
implied by Model 1's forecast distribution:

```
b = credit / (max_loss - credit)
f = (p_win * (b + 1) - 1) / b
contracts = equity * 0.25 * f / (max_loss * 100)
```

Probabilities below the 0.55 floor are refused - never inflated. Sizing is
capped by the exposure gates.

**Step 9 - The LLM debate (Model 3, veto/shrink ONLY)**
A multi-agent LLM pipeline (TradingAgents pattern) on Cloudflare Workers AI:

- **GLM-5.2 analysts** brief two adversarial agents
- **Bull agent** argues why the trade should be taken
- **Bear agent** (Kimi-K2.7) argues why it should be killed
- **GLM-5.3-Flash PM** issues the final verdict

**The LLM can only VETO or SHRINK a trade - never grow risk.** If the LLM is
unreachable, the system fails closed to the deterministic decision.

**Step 10 - The 7 deterministic risk gates**
Pure math. Cannot be overridden by any model output:

| Gate | Rule |
|------|------|
| G1 | Defined risk only - max loss known in advance |
| G2 | Turbulence gate - no entries when VIX spikes or HMM reads stress |
| G3 | Monte Carlo VaR - 32,768 paths per trade, tail risk checked |
| G4 | Quarter Kelly sizing from honest structural win probability |
| G5 | Exposure caps - 1.5% NAV per trade, 6% portfolio-wide |
| G6 | Daily loss circuit breaker - 2% NAV halts trading |
| G7 | Concentration control with rule-based exits |

**Step 11 - The 15-minute autonomous cycle (Model 1 orchestrator)**
Every 15 minutes, one idempotent cycle runs:

```
forecast -> VRP signal -> structure -> Monte Carlo -> Kelly -> LLM debate
-> execute (Alpaca mleg) -> manage exits -> journal -> dashboard push
```

**Step 12 - Execution on Alpaca**
All trading on a fresh $100,000 Alpaca paper account via the Trading API:

- Live SPY option chains and IV snapshots from `data.alpaca.markets`
- Multi-leg iron flys as single **mleg limit orders** (bounded slippage)
- Bracket orders (stop + trail) for the long/short equity sleeve
- `/v2/clock` market-hours gating

---

## The Result (Day 1, live paper)

| Metric | Value |
|--------|-------|
| Start equity | $100,000.00 |
| End equity (day 1, booked flat) | **$100,335.37** |
| Structure | Iron fly: sell ATM strangle @ IV 10.7% vs forecast 8.6% |
| Max premium at risk | 1.37% NAV (gate G5) |
| Exits | +430 short-put, +142 wing, -204 hedge, -62 cut leg |
| Cycles logged | 47 (every 15 min, fully autonomous) |

The math worked exactly as designed: the fly was short premium at IV 10.7%
vs forecast 8.6% - SPY's realized vol came in below implied, the short put
decayed +430, and every exit was executed through the verified mleg path.

---

## The Dashboard (React + TypeScript + Vite)

8 pages, live on Cloudflare Workers + KV:

| Page | What you see |
|------|--------------|
| Overview | Equity/P&L KPIs, vol-forecast bars, VRP panel, MC VaR, cycle log |
| Positions | Live Alpaca positions + orders (mleg class visible) |
| Trades | Full journal: legs, credit, VRP at entry, agent verdict |
| Agent Brain | The actual bull/bear/PM debate transcripts |
| Backtest Loop | Rounds, best variant, ICIR/OOS/DSR + Run Loop button with live progress |
| Monte Carlo | Fan chart (32k paths), P&L histogram with VaR/CVaR markers, convergence plot, tornado - with interactive sliders + Run Simulation |
| Risk Gates | The 7-gate constitution + authority chain |
| Data & Models | Data sources, honest backtest assumptions, upgrade path |

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
└── .env.example            # template - real keys live ONLY in local .env
```

---

## Quick Start

```bash
# 1. Python 3.11 venv + deps
py -3.11 -m venv venv
venv\\Scripts\\pip install alpaca-py pandas numpy scipy statsmodels scikit-learn arch hmmlearn python-dotenv tabulate requests

# 2. Secrets (never committed)
copy .env.example .env        # fill in your Alpaca paper keys

# 3. One trading cycle (safe, idempotent)
venv\\Scripts\\python -m vulcan.main --dry-run     # dry run first
venv\\Scripts\\python -m vulcan.main               # live paper cycle

# 4. The backtest loop (self-improving, until convergence)
venv\\Scripts\\python -m vulcan.loop_runner

# 5. Monte Carlo engine demo
venv\\Scripts\\python -m vulcan.montecarlo

# 6. Dashboard (React+TS+Vite -> Cloudflare Worker)
cd dashboard && npm install && npm run build && cd ..
npx wrangler deploy
```

---

## Honest Assumptions (read this)

- The backtest settles **synthetic condors**: entry priced by Black-Scholes at
  IV = RV20 x markup, settled European-style, with documented frictions
  ($0.65/leg + 25% credit slippage). This is the standard pedagogical VRP method -
  assumptions stated, not hidden.
- Live data = Alpaca IEX (15-min delayed, ~2% tape volume - closes accurate) +
  Alpaca indicative option chains (IV + greeks on ~10k SPY contracts).
- **#1 upgrade path**: Polygon.io free tier (2y real EOD option prices) to convert
  model validation into market validation. CBOE free VIX CSVs feed the turbulence gate.
- Paper trading results are hypothetical and do not guarantee future returns.

---

## Tech Stack

Python 3.11 (alpaca-py, pandas, numpy, scipy, statsmodels, arch, hmmlearn, scikit-learn)
- React 18 + TypeScript + Vite + Recharts - Cloudflare Workers + KV -
Cloudflare Workers AI (GLM-5.3-Flash / GLM-5.2 / Kimi-K2.7)

---

## License

MIT - see [LICENSE](LICENSE).

---

## Disclaimer

Educational hackathon project. Paper trading only. Nothing here is financial
advice. Options involve substantial risk of loss.
"""

p = Path(__file__).parent / "README.md"
p.write_text(DOC, encoding="utf-8")
print(f"README.md written: {p} ({p.stat().st_size} bytes)")
