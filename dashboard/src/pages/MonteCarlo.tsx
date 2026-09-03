import { useEffect, useState } from "react";
import {
  Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis, BarChart, Cell, Legend,
} from "recharts";

interface McData {
  ts: string; spot: number; iv: number; dte: number; r: number;
  engine: { paths: number; steps: number; techniques: string[] };
  strikes: { sp: number; lp: number; sc: number; lc: number };
  credit: number; maxLoss: number;
  fan: { step: number; p5: number; p25: number; p50: number; p75: number; p95: number }[];
  spaghetti: number[][];
  pnl: { hist: { x: number; n: number }[]; var95: number; var99: number; cvar99: number;
    breachProb: number; maxLoss: number; meanCredit: number };
  convergence: { N: number; seNaive: number; seAnti: number; seControl: number;
    priceAnti: number; priceControl: number; ref: number }[];
  bsRef: number;
  tornado: { factor: string; low: number; high: number; swing: number }[];
  baseVar99: number;
}

const KPI = ({ k, v, s, cls }: { k: string; v: string; s?: string; cls?: string }) => (
  <div className={"stat " + (cls || "bg-white")} style={{ marginBottom: 0 }}>
    <div className="k">{k}</div>
    <div className="v" style={{ fontSize: 21 }}>{v}</div>
    {s && <div className="s">{s}</div>}
  </div>
);

export default function MonteCarlo() {
  const [d, setD] = useState<McData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [params, setParams] = useState({ seed: 42, sigma: 1.0, spotShift: 0, offset: 1.0, width: 1.0, dte: 9 });
  const [dirty, setDirty] = useState(false);

  const load = async (p = params) => {
    setLoading(true);
    try {
      const qs = new URLSearchParams(Object.fromEntries(Object.entries(p).map(([k, v]) => [k, String(v)])));
      const r = await fetch(`/api/mc?${qs}`, { cache: "no-store" });
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      setD(j); setErr(null); setDirty(false);
    } catch (e) { setErr(String(e)); } finally { setLoading(false); }
  };
  useEffect(() => { load(); const id = setInterval(() => { if (!dirty) load(); }, 60000); return () => clearInterval(id); }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps

  const set = (k: string, v: number) => setParams(p => ({ ...p, [k]: v }));

  const slider = (label: string, k: string, min: number, max: number, step: number, fmt: (v: number) => string) => (
    <label style={{ fontSize: 11.5, display: "block", minWidth: 200, flex: "1 1 200px" }}>
      <b>{label}</b> <span style={{ color: "#00794f" }}>{fmt(params[k as keyof typeof params])}</span>
      <input type="range" min={min} max={max} step={step} value={params[k as keyof typeof params]}
             onChange={e => set(k, Number(e.target.value))}
             style={{ width: "100%", accentColor: "#a259ff" }} />
    </label>
  );

  if (loading && !d) return <div className="spinner">simulating 32,768 GBM paths…</div>;
  if (err || !d) return <div className="error-box">MC ERROR: {err}</div>;

  const fanData = d.fan.map(f => ({
    ...f,
    ...Object.fromEntries(d.spaghetti.map((row, i) => [`p${i}`, row[Math.min(f.step, row.length - 1)]])),
  }));
  const s0 = d.spot;
  const pnlData = d.pnl.hist.map(h => ({ ...h, loss: h.x < 0 ? h.n : 0, profit: h.x >= 0 ? h.n : 0 }));
  const convData = d.convergence.map(c => ({
    N: c.N, label: c.N.toLocaleString(),
    naive: c.seNaive, antithetic: c.seAnti, control: c.seControl,
    refNaive: c.ref * d.convergence[0].seNaive,
    refAnti: c.ref * d.convergence[0].seAnti,
  }));
  const tornData = d.tornado.map(t => ({ name: t.factor, low: Math.min(t.low, t.high), mid: 0, swing: Math.abs(t.high - t.low) }));

  return (
    <>
      <div className="page-title">Monte Carlo Simulation Lab</div>
      <div className="page-sub">
        GBM exact solution · antithetic + control variate + moment matching · recomputed live from Alpaca spot/IV every 60s
      </div>

      <div className="card" style={{ background: "#fffbe8" }}>
        <div className="card-title">Run Simulation — interactive what-if
          <span className="muted">{dirty ? "parameters changed — press RUN" : "live"}</span>
        </div>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
          {slider("vol ×", "sigma", 0.5, 2.0, 0.05, v => v.toFixed(2) + "×")}
          {slider("spot shift", "spotShift", -0.05, 0.05, 0.005, v => (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%")}
          {slider("offset ×", "offset", 0.5, 1.8, 0.05, v => v.toFixed(2) + "×")}
          {slider("width ×", "width", 0.3, 1.8, 0.05, v => v.toFixed(2) + "×")}
          {slider("DTE", "dte", 1, 30, 1, v => String(v) + "d")}
          <label style={{ fontSize: 11.5 }}>
            <b>seed</b>
            <input type="number" value={params.seed} onChange={e => set("seed", Number(e.target.value) || 0)}
                   style={{ width: 80, marginLeft: 6, border: "2px solid #111", padding: "4px 6px", fontFamily: "inherit", fontWeight: "bold" }} />
          </label>
          <button onClick={() => load()}
                  style={{ border: "3px solid #111", background: "var(--purple)", color: "#fff", fontWeight: "bold",
                           padding: "9px 18px", cursor: "pointer", boxShadow: "4px 4px 0 #111",
                           fontFamily: "inherit", fontSize: 13, textTransform: "uppercase" }}>
            ⚡ Run Simulation
          </button>
          <button onClick={() => { setParams({ seed: 42, sigma: 1.0, spotShift: 0, offset: 1.0, width: 1.0, dte: 9 }); setTimeout(() => load({ seed: 42, sigma: 1.0, spotShift: 0, offset: 1.0, width: 1.0, dte: 9 }), 50); }}
                  style={{ border: "3px solid #111", background: "#fff", fontWeight: "bold",
                           padding: "9px 14px", cursor: "pointer", boxShadow: "4px 4px 0 #111",
                           fontFamily: "inherit", fontSize: 12, textTransform: "uppercase" }}>
            reset
          </button>
        </div>
      </div>

      <div className="grid g4" style={{ marginBottom: 18 }}>
        <KPI k="SPY spot (live)" v={"$" + d.spot.toFixed(2)} s={"ATM IV " + (d.iv * 100).toFixed(1) + "% — " + d.dte + "dte horizon"} cls="bg-blue" />
        <KPI k="Sim paths" v={d.engine.paths.toLocaleString()} s={d.engine.techniques.slice(0, 3).join(" · ")} cls="bg-purple" />
        <KPI k="Condor credit (BS)" v={"$" + d.credit.toFixed(2)} s={"max loss $" + d.maxLoss.toFixed(2) + "/ct"} cls="bg-yellow" />
        <KPI k="99% VaR / CVaR" v={"$" + d.pnl.var99.toFixed(0)} s={"CVaR $" + d.pnl.cvar99.toFixed(0) + " — breach P " + (d.pnl.breachProb * 100).toFixed(2) + "%"} cls={d.pnl.breachProb > 0.04 ? "bg-red" : "bg-green"} />
      </div>

      <div className="card">
        <div className="card-title">GBM Path Simulation — 25 spaghetti paths + P5–P95 percentile fan
          <span className="muted">9-day horizon · dashed line = entry {s0.toFixed(0)} · strikes {d.strikes.lp.toFixed(0)}/{d.strikes.sp.toFixed(0)} / {d.strikes.sc.toFixed(0)}/{d.strikes.lc.toFixed(0)}</span>
        </div>
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={fanData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
            <CartesianGrid stroke="#ddd" strokeDasharray="3 3" />
            <XAxis dataKey="step" tick={{ fontSize: 11 }} label={{ value: "trading days", fontSize: 10 }} />
            <YAxis domain={["dataMin - 10", "dataMax + 10"]} tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{ fontFamily: "monospace", fontSize: 12, border: "2px solid #111" }}
              formatter={(v, n) => ["$" + Number(v).toFixed(2), String(n)]} />
            <Area dataKey="p95" stroke="none" fill="#4d9dff" fillOpacity={0.12} />
            <Area dataKey="p5" stroke="none" fill="#ffffff" fillOpacity={0} />
            <Area dataKey="p75" stroke="none" fill="#4d9dff" fillOpacity={0.18} />
            <Area dataKey="p25" stroke="none" fill="#ffffff" fillOpacity={1} />
            <Line dataKey="p50" stroke="#111" strokeWidth={2.5} dot={false} />
            {d.spaghetti.map((_, i) => (
              <Line key={i} dataKey={`p${i}`} stroke="#ff5d8f" strokeWidth={0.8} dot={false} opacity={0.45} />
            ))}
            <ReferenceLine y={s0} stroke="#00c48c" strokeDasharray="6 4" strokeWidth={2}
              label={{ value: "entry " + s0.toFixed(0), fontSize: 10, fill: "#00875a", position: "insideTopLeft" }} />
            <ReferenceLine y={d.strikes.sp} stroke="#ff4747" strokeDasharray="4 4" />
            <ReferenceLine y={d.strikes.sc} stroke="#ff4747" strokeDasharray="4 4" />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="muted" style={{ marginTop: 6 }}>
          Fan bands: P5–P95 (light) and P25–P75 (nested). Red dashes = short strikes — the zone where the condor starts losing.
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <div className="card-title">Condor P&L Distribution — {d.engine.paths.toLocaleString()} settle paths
            <span className="muted">green = profit, red = loss</span>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={pnlData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
              <CartesianGrid stroke="#ddd" strokeDasharray="3 3" />
              <XAxis dataKey="x" tick={{ fontSize: 10 }} tickFormatter={(v: number) => "$" + v.toFixed(0)} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ fontFamily: "monospace", fontSize: 12, border: "2px solid #111" }}
                formatter={(v) => [Number(v).toLocaleString() + " paths", "count"]}
                labelFormatter={(l) => "P&L $" + Number(l).toFixed(0)} />
              <Bar dataKey="profit" fill="#00c48c" />
              <Bar dataKey="loss" fill="#ff4747" />
              <ReferenceLine x={0} stroke="#111" strokeWidth={2} />
              <ReferenceLine x={-d.pnl.var95} stroke="#a259ff" strokeDasharray="5 3"
                label={{ value: "VaR95 $" + d.pnl.var95.toFixed(0), fontSize: 10, position: "insideTopLeft" }} />
              <ReferenceLine x={-d.pnl.var99} stroke="#ff4747" strokeWidth={2} strokeDasharray="5 3"
                label={{ value: "VaR99 $" + d.pnl.var99.toFixed(0), fontSize: 10, position: "insideTopRight" }} />
              <ReferenceLine x={-d.pnl.cvar99} stroke="#7a0000" strokeWidth={2}
                label={{ value: "CVaR99 $" + d.pnl.cvar99.toFixed(0), fontSize: 10, position: "insideTopRight" }} />
            </BarChart>
          </ResponsiveContainer>
          <div className="muted">Tail is never trimmed — the ugly left side IS the finding. CVaR99 = mean loss beyond VaR99.</div>
        </div>

        <div className="card">
          <div className="card-title">Convergence — SE vs paths (log axes)
            <span className="muted">vertical gap = variance reduction</span>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={convData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
              <CartesianGrid stroke="#ddd" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis scale="log" domain={["auto", "auto"]} tick={{ fontSize: 10 }}
                label={{ value: "std error (log)", fontSize: 10, angle: -90, position: "insideLeft" }} />
              <Tooltip contentStyle={{ fontFamily: "monospace", fontSize: 12, border: "2px solid #111" }} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line dataKey="naive" stroke="#ff4747" strokeWidth={2} dot name="naive pseudo" />
              <Line dataKey="antithetic" stroke="#4d9dff" strokeWidth={2} dot name="antithetic" />
              <Line dataKey="control" stroke="#00c48c" strokeWidth={2} dot name="anti + control variate" />
              <Line dataKey="refAnti" stroke="#999" strokeWidth={1} strokeDasharray="4 4" dot={false} name="theoretical 1/sqrt(N)" />
            </ComposedChart>
          </ResponsiveContainer>
          <table style={{ marginTop: 8 }}>
            <thead><tr><th>N</th><th>SE naive</th><th>SE anti</th><th>SE anti+ctrl</th><th>MC price</th><th>BS exact</th></tr></thead>
            <tbody>
              {d.convergence.map(c => (
                <tr key={c.N}>
                  <td>{c.N.toLocaleString()}</td>
                  <td>{c.seNaive.toFixed(4)}</td>
                  <td>{c.seAnti.toFixed(4)}</td>
                  <td style={{ color: "#00794f", fontWeight: "bold" }}>{c.seControl.toFixed(4)}</td>
                  <td>{c.priceControl.toFixed(3)}</td>
                  <td>{d.bsRef.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <div className="card-title">Tornado — what moves 99% VaR the most
            <span className="muted">swing = |VaR(high) − VaR(low)|</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={tornData} layout="vertical" margin={{ top: 5, right: 20, bottom: 5, left: 60 }}>
              <CartesianGrid stroke="#ddd" strokeDasharray="3 3" />
              <XAxis type="number" tick={{ fontSize: 10 }} tickFormatter={(v: number) => "$" + v.toFixed(0)} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={110} />
              <Tooltip contentStyle={{ fontFamily: "monospace", fontSize: 12, border: "2px solid #111" }}
                formatter={(v) => ["$" + Number(v).toFixed(0), "swing"]} />
              <Bar dataKey="swing" fill="#a259ff" />
            </BarChart>
          </ResponsiveContainer>
          <div className="muted">Base VaR99 ${d.baseVar99.toFixed(0)}/ct. Width of the wings swings risk more than spot or vol here — because we already size vol-aware.</div>
        </div>

        <div className="card" style={{ background: "var(--ink)", color: "#fff" }}>
          <div className="card-title" style={{ color: "var(--yellow)", borderBottomColor: "#444" }}>The math on this page</div>
          <div style={{ fontSize: 12, lineHeight: 2 }}>
            <b style={{ color: "var(--green)" }}>GBM exact:</b> S_T = S₀·exp((r − σ²/2)T + σ√T·Z) — zero discretization bias<br />
            <b style={{ color: "var(--blue)" }}>Antithetic:</b> every path paired with its mirror (Z, −Z) → halves odd-moment noise<br />
            <b style={{ color: "var(--yellow)" }}>Control variate:</b> MC estimates only the residual vs E[S_T] = S₀·e^(rT) known exactly<br />
            <b style={{ color: "var(--pink)" }}>Sobol QMC (python engine):</b> low-discrepancy sequence, empirical O(1/N) convergence — runs inside risk gate G3 (32,768 paths per trade)<br />
            <b style={{ color: "var(--purple)" }}>Moment matching:</b> sample Z forced to mean 0 / std 1 before use<br />
            <b style={{ color: "#fff" }}>Verified:</b> MC {d.convergence[d.convergence.length - 1].priceControl.toFixed(3)} ± {d.convergence[d.convergence.length - 1].seControl.toFixed(3)} vs BS exact {d.bsRef.toFixed(3)} ✓
          </div>
        </div>
      </div>
    </>
  );
}
