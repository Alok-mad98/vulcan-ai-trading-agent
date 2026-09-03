import { useCallback, useEffect, useRef, useState } from "react";
import { useData, money, num } from "../api";

interface JobStatus { pct?: number; round?: number; total_rounds?: number; message?: string; done?: boolean; ts?: number }

function LoopRunner() {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [rounds, setRounds] = useState(3);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/jobs/status", { cache: "no-store" });
      const j = await r.json();
      setStatus(j.status);
      if (j.status && !j.status.done) setBusy(true);
      if (j.status?.done) setBusy(false);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    refresh();
    pollRef.current = window.setInterval(refresh, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [refresh]);

  const run = async (continuous: boolean) => {
    setBusy(true); setMsg(null);
    try {
      const r = await fetch("/api/jobs/request", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: continuous ? "loop_continuous" : "loop", max_rounds: rounds }),
      });
      const j = await r.json();
      setMsg(j.ok ? "Job queued — the local bot picks it up within ~2 min and streams progress here."
                  : j.error || "failed");
    } catch (e) { setMsg(String(e)); }
  };

  const pct = Math.min(100, status?.pct ?? 0);
  return (
    <div className="card" style={{ background: "#fffbe8" }}>
      <div className="card-title">Run the Loop — from this page
        <span>
          <span className="tag" style={{ background: busy ? "var(--yellow)" : "var(--green)", color: busy ? "#111" : "#fff" }}>
            {busy ? "RUNNING" : "idle"}
          </span>
        </span>
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ fontSize: 12 }}>rounds:
          <select value={rounds} onChange={e => setRounds(Number(e.target.value))}
                  style={{ marginLeft: 6, fontFamily: "inherit", fontSize: 12, border: "2px solid #111", padding: "4px 8px", fontWeight: "bold" }}>
            {[1, 2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button onClick={() => run(false)} disabled={busy}
                style={{ border: "3px solid #111", background: "var(--yellow)", fontWeight: "bold",
                         padding: "9px 18px", cursor: busy ? "not-allowed" : "pointer", boxShadow: "4px 4px 0 #111",
                         fontFamily: "inherit", fontSize: 13, textTransform: "uppercase" }}>
          ▶ Run Backtest Loop
        </button>
        <button onClick={() => run(true)} disabled={busy}
                style={{ border: "3px solid #111", background: "var(--pink)", color: "#fff", fontWeight: "bold",
                         padding: "9px 18px", cursor: busy ? "not-allowed" : "pointer", boxShadow: "4px 4px 0 #111",
                         fontFamily: "inherit", fontSize: 13, textTransform: "uppercase" }}>
          ↻ Continuous until perfect
        </button>
      </div>
      <div className="bar" style={{ marginTop: 14, height: 20 }}>
        <i style={{ width: `${pct}%`, background: pct >= 100 ? "var(--green)" : "var(--blue)",
                    transition: "width 1s" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 11.5 }}>
        <b>{pct.toFixed(0)}%</b>
        <span className="muted">
          {status?.message || (busy ? "waiting for bot…" : "generate → backtest → ICIR → refine → OOS gate")}
        </span>
      </div>
      {msg && <div className="muted" style={{ marginTop: 6 }}>{msg}</div>}
    </div>
  );
}

export default function Backtest() {
  const { data, error, loading } = useData();
  if (loading) return <div className="spinner">loading loop…</div>;
  if (error || !data?.ok) return <div className="error-box">API ERROR: {error}</div>;
  const L = data.loop;
  if (!L?.rounds?.length) return <div className="card"><div className="muted">no loop runs yet — run `python -m vulcan.loop_runner`</div></div>;

  const b = L.best;
  const p = b?.params || {};

  return (
    <>
      <div className="page-title">Backtest Loop — Loop Engineering</div>
      <div className="page-sub">
        Generate → walk-forward backtest → ICIR score → failure analysis → refine → OOS gate + deflated Sharpe
      </div>

      <LoopRunner />

      <div className="card">
        <div className="card-title">
          Status
          <span>
            <span className={"tag " + (L.converged ? "yes" : "warn")}>{L.converged ? "CONVERGED" : "REFINING"}</span>
            <span className="tag">{L.rounds.length} rounds</span>
            {L.note && <span className="tag info">{L.note}</span>}
          </span>
        </div>
        <div className="muted" style={{ lineHeight: 1.8 }}>
          {L.started?.slice(0, 16)} → {L.finished?.slice(0, 16)}Z · frictions: ${L.frictions?.fee_per_leg}/leg fee ·
          {" "}{((L.frictions?.slippage_pct_of_credit || 0) * 100).toFixed(0)}% credit slippage · walk-forward refit every step (no leakage)
        </div>
        {b && (L.rounds[L.rounds.length - 1]?.note) && (
          <div className="muted" style={{ marginTop: 8 }}>{L.rounds[L.rounds.length - 1].note}</div>
        )}
      </div>

      {b && (
        <div className="card">
          <div className="card-title">Best Stable Variant</div>
          <div style={{ marginBottom: 10 }}>
            <span className="tag">offset {num(p.offset_atm_sigma)}σ</span>
            <span className="tag">width {num(p.width_atm_sigma)}σ</span>
            <span className="tag">VRP thr {num(p.vrp_threshold_pts, 3)}</span>
            <span className="tag">markup ×{num(p.vrp_markup)}</span>
          </div>
          <table>
            <thead><tr><th>Metric</th><th>Value</th><th>Meaning</th></tr></thead>
            <tbody>
              <tr><td>Trades</td><td><b>{b.trades_n}</b></td><td>synthetic 9-DTE condors over sample</td></tr>
              <tr><td>Win rate</td><td><b>{((b.win_rate || 0) * 100).toFixed(0)}%</b></td><td>premium kept at expiry</td></tr>
              <tr><td>Profit factor</td><td><b>{num(b.profit_factor, 1)}</b></td><td>gross win / gross loss</td></tr>
              <tr><td>Sharpe (IS)</td><td><b>{num(b.sharpe, 1)}</b></td><td>in-sample daily</td></tr>
              <tr><td>Sharpe (OOS)</td><td><b>{num(b.oos_sharpe, 1)}</b></td><td>last 25% untouched — the honest number</td></tr>
              <tr><td>ICIR</td><td><b>{num(b.icir)}</b></td><td>signal consistency ({b.ic_months} monthly ICs)</td></tr>
              <tr><td>Half-life</td><td><b>{num(b.half_life, 0)}d</b></td><td>signal decay — must be ≥ 5d</td></tr>
              <tr><td>IS P&L</td><td className="up"><b>{money(b.is_pnl)}</b></td><td>per 1 contract, full sample</td></tr>
              <tr><td>OOS P&L</td><td className="up"><b>{money(b.oos_pnl)}</b></td><td>held-out validation</td></tr>
            </tbody>
          </table>
          <div className="muted" style={{ marginTop: 10 }}>
            ⚠ Synthetic assumptions documented: European-style settlement, BS entry pricing at IV=RV20×markup,
            mid-price fills with frictions above. Live sizing is capped by Kelly + 1.5% NAV gates regardless.
          </div>
        </div>
      )}

      {L.rounds.map((r) => (
        <div className="card" key={r.round}>
          <div className="card-title">
            <span>Round {r.round} — {r.n_variants} variants</span>
            <span className={"tag " + (r.gate_pass ? "yes" : "warn")}>{r.gate_pass ? "PASS" : "refine"}</span>
          </div>
          {r.best && (
            <div style={{ fontSize: 12, lineHeight: 1.9 }}>
              best: wr <b>{((r.best.win_rate || 0) * 100).toFixed(0)}%</b> · pf <b>{num(r.best.profit_factor, 1)}</b> ·
              sr <b>{num(r.best.sharpe, 1)}</b> · icir <b>{num(r.best.icir)}</b> ·
              oos_sr <b>{num(r.best.oos_sharpe, 1)}</b> · oos <b className="up">{money(r.best.oos_pnl)}</b>
            </div>
          )}
          {r.failures?.length ? (
            <div style={{ marginTop: 6 }}>{r.failures.slice(0, 5).map((f, i) => <span key={i} className="tag no">{f}</span>)}</div>
          ) : <div className="muted" style={{ marginTop: 6 }}>no failure modes this round</div>}
        </div>
      ))}
    </>
  );
}
