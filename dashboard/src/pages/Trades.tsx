import { useData, money } from "../api";
import { Trade } from "../api";

export default function Trades() {
  const { data, error, loading } = useData();
  if (loading) return <div className="spinner">loading trades…</div>;
  if (error || !data?.ok) return <div className="error-box">API ERROR: {error}</div>;
  const T: Trade[] = [...(data.bot?.trades || [])].reverse();

  return (
    <>
      <div className="page-title">Trade Journal</div>
      <div className="page-sub">Every VULCAN trade with its full evidence trail — VRP at entry, agent verdict, defined risk</div>

      {T.length === 0 && <div className="card"><div className="muted">no trades yet — the desk only fires when VRP clears the gate</div></div>}

      {T.map((t, i) => (
        <div className="card" key={i}>
          <div className="card-title">
            <span>{t.name.toUpperCase()} × {t.contracts} — {t.ts.slice(0, 16).replace("T", " ")}Z</span>
            <span>
              <span className={"tag " + (t.status === "open" ? "warn" : "info")}>{t.status}</span>
              <span className="tag">dte {t.dte}</span>
            </span>
          </div>
          <div style={{ fontSize: 12.5, lineHeight: 2 }}>
            <span className="tag">credit {money(t.credit)}</span>
            <span className="tag">max loss/ct {money(t.max_loss_per_ct)}</span>
            <span className="tag">max profit/ct {money(t.max_profit_per_ct)}</span>
            <span className="tag">risk {money(t.risk_total)}</span>
            <span className="tag info">VRP {(t.vrp * 100).toFixed(1)}pts</span>
            <span className="tag">IV {(t.iv * 100).toFixed(1)}%</span>
            <span className="tag">RVfc {(t.rv_fc * 100).toFixed(1)}%</span>
          </div>
          {t.legs && (
            <table style={{ marginTop: 10 }}>
              <thead><tr><th>Side</th><th>Leg</th><th>Strike</th><th>Expiry</th><th>Symbol</th></tr></thead>
              <tbody>
                {t.legs.map((l, j) => (
                  <tr key={j}>
                    <td><span className={"tag " + (l.side === "buy" ? "yes" : "no")}>{l.side}</span></td>
                    <td style={{ fontWeight: "bold" }}>{l.kind}{l.strike}</td>
                    <td>{l.strike}</td>
                    <td>{l.expiration}</td>
                    <td className="muted">{l.symbol}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {t.agent && (
            <div style={{ marginTop: 10, fontSize: 11.5 }}>
              <span className={"tag " + (t.agent.decision === "APPROVE" ? "yes" : t.agent.decision === "VETO" ? "no" : "warn")}>
                PM: {t.agent.decision}
              </span>
              <span className="muted"> {t.agent.reason?.slice(0, 220)}</span>
            </div>
          )}
        </div>
      ))}
    </>
  );
}
