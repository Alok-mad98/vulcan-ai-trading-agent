import { useData } from "../api";

const box = (cls: string, who: string, model: string, txt?: string) => (
  <div className={"debate " + cls}>
    <div className="who">{who} <span className="tag info" style={{ float: "right" }}>{model}</span></div>
    <div className="txt">{txt || "—"}</div>
  </div>
);

export default function Agent() {
  const { data, error, loading } = useData();
  if (loading) return <div className="spinner">loading agent…</div>;
  if (error || !data?.ok) return <div className="error-box">API ERROR: {error}</div>;
  const ag = data.bot?.last_agent;
  if (!ag) return <div className="card"><div className="muted">no debate yet — first market-hours cycle will populate this</div></div>;

  return (
    <>
      <div className="page-title">Agent Brain — Live Debate</div>
      <div className="page-sub">TradingAgents pipeline: 4 analysts → bull/bear adversarial debate → risk → PM verdict</div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-title">Latest Verdict
          <span>
            <span className={"tag " + (ag.decision === "APPROVE" ? "yes" : ag.decision === "VETO" ? "no" : "warn")}>{ag.decision}</span>
            <span className={"tag " + (ag.llm_used ? "yes" : "warn")}>{ag.llm_used ? "LLM LIVE" : "fail-closed"}</span>
          </span>
        </div>
        <div style={{ fontSize: 12.5, lineHeight: 1.7 }}>
          The LLM can only <b>VETO</b> or <b>SHRINK</b> a trade — never grow risk. Deterministic gates hold final authority.
        </div>
      </div>

      {box("pm", "Portfolio Manager — final authority", "GLM-5.3-Flash", ag.pm_reason)}
      {box("bull", "Bull Researcher", "GLM-5.2", ag.bull_case)}
      {box("bear", "Bear Researcher — adversarial", "Kimi-K2.7", ag.bear_case)}
      {box("pm", "Risk Manager", "GLM-5.2", ag.risk_note)}
    </>
  );
}
