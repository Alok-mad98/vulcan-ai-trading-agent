const GATES = [
  { n: 1, t: "Defined-risk only", d: "Every structure must have bounded max loss (spreads/condors). Max loss = net debit paid. Naked shorts are impossible by construction." },
  { n: 2, t: "VIX / turbulence gate", d: "No NEW premium selling when VIX > 28, when VIX jumps > +12% intraday, or when the HMM regime flips to stress." },
  { n: 3, t: "Monte Carlo VaR gate", d: "32,768 GBM paths (antithetic + Sobol QMC + moment matching) price the FULL P&L distribution. Veto if 99% VaR > defined max loss or P(breach) > 4%. Deterministic 3-sigma gap stress kept as backstop." },
  { n: 4, t: "Quarter-Kelly sizing", d: "contracts = Kelly(edge, payoff) × 0.25 fraction. No edge → no contracts. Size ∝ win-probability × payoff ratio." },
  { n: 5, t: "Exposure caps", d: "Max premium-at-risk 1.5% NAV per trade, 6% NAV portfolio-wide. Buying power checked pre-order." },
  { n: 6, t: "Daily circuit breaker", d: "Realized loss > 2% NAV in one day → trading halts until the next session." },
  { n: 7, t: "Concentration control", d: "No overlapping structures on the same expiry + side. Exits: +60% max profit taken, -75% max loss breach stop, roll inside 2 DTE." },
];

export default function Risk() {
  return (
    <>
      <div className="page-title">Risk Constitution</div>
      <div className="page-sub">Deterministic gates — pure math, no LLM can ever override these</div>

      <div className="card">
        {GATES.map((g) => (
          <div className="risk-item" key={g.n}>
            <div className="risk-num">{g.n}</div>
            <div>
              <b>{g.t}</b>
              <div className="muted" style={{ marginTop: 3 }}>{g.d}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Authority Chain (who can do what)</div>
        <div style={{ fontSize: 12.5, lineHeight: 2 }}>
          <b style={{ color: "var(--green)" }}>Model 1+2 (math)</b> → propose trade + size via Kelly<br />
          <b style={{ color: "var(--blue)" }}>Risk gates G1-G7</b> → hard approve/veto, cannot be argued with<br />
          <b style={{ color: "var(--yellow)" }}>Model 3 (LLM PM)</b> → may VETO or SHRINK only — never grow risk<br />
          <b style={{ color: "var(--pink)" }}>Executor</b> → mleg limit orders at mid±slippage, bracket orders for equity sleeve
        </div>
      </div>

      <div className="card">
        <div className="card-title">Monte Carlo Engine — the math inside G3</div>
        <div style={{ fontSize: 12.5, lineHeight: 1.9 }}>
          <b>GBM exact solution:</b> S_T = S₀·exp((r − q − σ²/2)T + σ√T·Z) — zero discretization bias<br />
          <b>Variance reduction:</b> antithetic variates (Z,−Z pairs) + Sobol quasi-random (low-discrepancy,
          empirical O(1/N)) + moment matching + BS control variate on pricing → <b>3× variance reduction</b><br />
          <b>Convergence:</b> standard error ∝ 1/√N — verified: SE 0.179 → 0.092 → 0.046 → 0.024 as N×4<br />
          <b>Applications live:</b> option pricing cross-check (MC 3.048 ± 0.040 vs BS 3.0475 ✓),
          portfolio 99% VaR/CVaR (this gate), CVA module for OTC-style books (LGD × EE × PD discounted)
        </div>
      </div>
    </>
  );
}
