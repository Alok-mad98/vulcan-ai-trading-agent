# VULCAN — One-Page Write-Up
### AI Logic · Risk Gates · Alpaca Infrastructure

## AI Logic

VULCAN is an autonomous options desk built on one quantified edge: the **variance
risk premium**. Model 1 forecasts SPY realized volatility with an ensemble of three
established models — HAR-RV (heterogeneous autoregressive), GARCH(1,1) (conditional
volatility), and a Kalman filter (sequential state estimate) — plus a 2-state
Gaussian HMM regime classifier and qlib-Alpha158 momentum features for direction
bias. Model 2 extracts implied volatility from the live SPY option chain (Alpaca
options snapshots, ~10k contracts with IV + Greeks), computes the VRP signal
(IV − RV forecast), and constructs defined-risk structures (iron fly / iron condor
/ credit spreads) via a Kelly-aware grid search: strike geometry is chosen to
maximize the same Kelly edge the risk gate later verifies — builder and gate share
one objective. Model 3 is a multi-agent LLM pipeline (TradingAgents pattern) on
Cloudflare Workers AI: GLM-5.2 analysts feed an adversarial bull/bear debate
(Kimi-K2.7 argues against every trade), and GLM-5.3-Flash — the Portfolio Manager —
issues the final verdict. **The LLM can only VETO or SHRINK a trade, never grow
risk.** If the LLM is unreachable the system fails closed to the deterministic
decision. Every debate transcript is logged and visible on the live dashboard.

## Risk Gates

Seven deterministic gates run on every ticket; they are pure math and cannot be
overridden by any model output. **G1** defined-risk only (max loss = net debit
bounded by construction). **G2** turbulence gate: no new premium selling when VIX
is elevated/spiking or the HMM regime reads stress. **G3** Monte Carlo gate: 32,768
GBM paths (antithetic variates + Sobol QMC + moment matching + control variates,
3× variance reduction, O(1/√N) convergence verified) price the full P&L
distribution — the trade dies if simulated VaR99/CVaR99 exceed the defined max
(this gate caught and fixed a real sign bug during development). **G4** honest
quarter-Kelly sizing from the structural win probability implied by Model 1's
forecast distribution — probabilities below the 0.55 floor are refused, never
inflated. **G5** exposure caps: 1.5% NAV premium-at-risk per trade, 6% portfolio-wide.
**G6** daily loss circuit breaker (2% NAV → halt). **G7** concentration control with
rule-based exits: take profit at 60% of max gain, breach stop at 75% of max loss,
roll inside 2 DTE. A 3σ gap-day stress test backstops G3.

## Alpaca Infrastructure

All trading runs on a fresh $100,000 Alpaca paper account via the Trading API:
options chains and snapshots from `data.alpaca.markets`, multi-leg spreads as
single **mleg limit orders** (net-price convention, worst-case slippage bounded),
bracket orders (stop + trail) for the long/short equity sleeve, positions and
orders polled for reconciliation, and `/v2/clock` for market-hours gating. The
agent runs as an idempotent 15-minute cycle (Windows Task Scheduler): forecast →
signal → structure → Monte Carlo → Kelly → LLM debate → execute → manage exits →
journal. State persists to JSON; a Cloudflare Worker (+ KV) serves the React
dashboard, receives state pushes, hosts an on-demand Monte Carlo simulation
endpoint computed from live Alpaca data, and queues backtest jobs that the local
poller executes with live progress streaming.

**Result:** first live paper session closed green — $100,000.00 → $100,335.37 —
with every decision logged, every gate enforced, and the full evidence trail public.
