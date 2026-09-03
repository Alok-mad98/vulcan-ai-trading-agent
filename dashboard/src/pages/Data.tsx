export default function Data() {
  return (
    <>
      <div className="page-title">Data & Models</div>
      <div className="page-sub">What we trade on, where it comes from, and what is honest about it</div>

      <div className="card">
        <div className="card-title">Live Data (execution feed)</div>
        <table>
          <thead><tr><th>Feed</th><th>What</th><th>Notes</th></tr></thead>
          <tbody>
            <tr><td>Alpaca IEX daily bars</td><td>SPY OHLCV — 400d lookback</td><td>free, 15-min delayed, ~2% tape volume (closes are accurate)</td></tr>
            <tr><td>Alpaca options snapshots</td><td>13k+ SPY contracts, IV + greeks</td><td>indicative feed — live chains for signal + execution</td></tr>
            <tr><td>CBOE VIX (planned)</td><td>free official CSV history</td><td>feeds turbulence gate G2</td></tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-title">Backtest Data (research feed) — honest</div>
        <div style={{ fontSize: 12.5, lineHeight: 1.9 }}>
          Current backtester settles <b>synthetic 9-DTE condors</b>: strikes from forecast σ, entry priced by
          Black-Scholes at IV = RV20 × markup, settled European-style vs realized path, with documented frictions
          (fees per leg + 25% credit slippage). This is the standard pedagogical VRP method — with assumptions
          stated, not hidden.
        </div>
        <div className="card-title" style={{ marginTop: 14 }}>Upgrade Path (ranked by impact)</div>
        <table>
          <thead><tr><th>#</th><th>Source</th><th>Free tier gives</th><th>Verdict</th></tr></thead>
          <tbody>
            <tr><td>1</td><td><b>Polygon.io options</b></td><td>2yr SPY EOD option prices (5 req/min)</td><td className="up">#1 upgrade — real settle prices</td></tr>
            <tr><td>2</td><td>CBOE DataShop VIX/VIX3M</td><td>free official CSVs</td><td className="up">VRP regime filter — do next</td></tr>
            <tr><td>3</td><td>Tiingo</td><td>30yr daily EOD equities</td><td>deeper walk-forward samples</td></tr>
            <tr><td>4</td><td>ThetaData</td><td>$40/mo → 4yr chains + real IV/greeks</td><td>gold standard if paid</td></tr>
            <tr><td>—</td><td>tradingview-mcp</td><td>indicators/sentiment only, no chains</td><td className="down">skip for backtest</td></tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-title">Model Roster</div>
        <table>
          <thead><tr><th>Model</th><th>Stack</th><th>Job</th></tr></thead>
          <tbody>
            <tr><td><b>Model 1 — Vol Forecaster</b></td><td>HAR-RV + GARCH(1,1) + Kalman ensemble, HMM regime, qlib-Alpha158 features</td><td>forecast realized vol + direction bias</td></tr>
            <tr><td><b>Model 2 — Pricer + Loop</b></td><td>Black-Scholes greeks, VRP signal, ICIR/OOS/DSR loop engineering</td><td>find + size the IV-RV gap trade</td></tr>
            <tr><td><b>Model 3 — Agent Brain</b></td><td>TradingAgents pattern on Cloudflare Workers AI</td><td>debate + veto/shrink authority</td></tr>
          </tbody>
        </table>
        <div style={{ marginTop: 10 }}>
          <span className="tag info">GLM-5.3-Flash — PM (main brain)</span>
          <span className="tag info">GLM-5.2 — analysts + risk</span>
          <span className="tag info">Kimi-K2.7 — adversarial bear</span>
        </div>
      </div>

      <div className="card">
        <div className="card-title">What VULCAN Trades</div>
        <div style={{ fontSize: 12.5, lineHeight: 2 }}>
          <span className="tag yes">OPTIONS — core (hackathon requirement)</span> VRP spreads/condors on SPY chains<br />
          <span className="tag yes">STOCKS — long/short sleeve</span> SPY bracket orders from the same vol brain<br />
          <span className="tag no">FOREX / COMMODITIES / FUTURES-PERPS</span> not available on Alpaca broker — platform limit, not strategy choice
        </div>
      </div>
    </>
  );
}
