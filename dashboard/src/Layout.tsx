import { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", icon: "◎", label: "Overview" },
  { to: "/positions", icon: "▤", label: "Positions" },
  { to: "/trades", icon: "✦", label: "Trades" },
  { to: "/agent", icon: "◈", label: "Agent Brain" },
  { to: "/backtest", icon: "∑", label: "Backtest Loop" },
  { to: "/montecarlo", icon: "∿", label: "Monte Carlo" },
  { to: "/risk", icon: "⛨", label: "Risk Gates" },
  { to: "/data", icon: "⛁", label: "Data & Models" },
];

export default function Layout({ children, live, ts }: { children: ReactNode; live: boolean; ts: string }) {
  return (
    <>
      <aside className="sidebar">
        <div className="logo">VULCAN</div>
        <div className="sub">Autonomous VRP Options Desk<br />Alpaca Paper — $100k</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => "nav-item" + (isActive ? " active" : "")}>
            <span className="nav-icon">{n.icon}</span>{n.label}
          </NavLink>
        ))}
        <div className="side-footer">
          <div style={{ marginBottom: 6 }}>
            <span className="live-dot" style={{ background: live ? "#00c48c" : "#ff4747" }}></span>
            <span className="side-badge">{live ? "LIVE" : "OFFLINE"}</span>
          </div>
          GLM-5.3-Flash PM<br />GLM-5.2 Analysts<br />Kimi-K2.7 Bear<br />
          <span style={{ color: "#666" }}>{ts}</span>
        </div>
      </aside>
      <main className="main">{children}</main>
    </>
  );
}
