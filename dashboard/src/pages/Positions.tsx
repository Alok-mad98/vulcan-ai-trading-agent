import { useData, money, pct } from "../api";

export default function Positions() {
  const { data, error, loading } = useData(10000);
  if (loading) return <div className="spinner">loading positions…</div>;
  if (error || !data?.ok) return <div className="error-box">API ERROR: {error}</div>;
  const P = data.positions || [];
  const O = (data.orders || []).filter((o) => o.status !== "expired").slice(0, 25);
  const totUnreal = P.reduce((s, p) => s + Number(p.unrealized || 0), 0);

  return (
    <>
      <div className="page-title">Positions & Orders</div>
      <div className="page-sub">Live from Alpaca paper account — refresh 10s</div>

      <div className="card">
        <div className="card-title">Open Positions ({P.length}) — unrealized {money(totUnreal)}</div>
        {P.length ? (
          <table>
            <thead><tr><th>Symbol</th><th>Qty</th><th>Side</th><th>Avg Entry</th><th>Now</th><th>Mkt Value</th><th>Unrealized</th><th>%</th></tr></thead>
            <tbody>
              {P.map((p, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: "bold" }}>{p.symbol}</td>
                  <td>{p.qty}</td>
                  <td><span className={"tag " + (p.side === "long" ? "yes" : "no")}>{p.side}</span></td>
                  <td>{money(p.avg_entry)}</td>
                  <td>{money(p.current)}</td>
                  <td>{money(p.market_value)}</td>
                  <td className={Number(p.unrealized) >= 0 ? "up" : "down"} style={{ fontWeight: "bold" }}>{money(p.unrealized)}</td>
                  <td className={Number(p.unrealized) >= 0 ? "up" : "down"}>{pct(p.unrealized_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="muted">flat — no open positions</div>}
      </div>

      <div className="card">
        <div className="card-title">Recent Orders</div>
        {O.length ? (
          <table>
            <thead><tr><th>Submitted</th><th>Class</th><th>Type</th><th>Status</th><th>Limit</th><th>Fill</th></tr></thead>
            <tbody>
              {O.map((o) => (
                <tr key={o.id}>
                  <td className="muted">{o.submitted?.replace("T", " ").slice(0, 16) || "—"}</td>
                  <td><span className="tag info">{o.class || "simple"}</span></td>
                  <td>{o.type}</td>
                  <td><span className={"tag " + (o.status === "filled" ? "yes" : o.status === "canceled" || o.status === "rejected" ? "no" : "warn")}>{o.status}</span></td>
                  <td>{o.limit ? money(o.limit) : "—"}</td>
                  <td>{o.filled ? money(o.filled) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="muted">no orders yet</div>}
      </div>
    </>
  );
}
