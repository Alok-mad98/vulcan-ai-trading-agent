import { useEffect, useState } from "react";

export interface VulcData {
  ok: boolean;
  ts: string;
  account?: {
    equity: string | number; cash: string | number; last_equity: string | number;
    pnl_day: number; pnl_total: number; buying_power: string | number;
    status: string; market_open: boolean;
  };
  positions?: PositionRow[];
  orders?: OrderRow[];
  bot?: BotState;
  loop?: LoopData;
}
export interface PositionRow {
  symbol: string; qty: string; side: string; avg_entry: string; current: string;
  market_value: string; unrealized: string; unrealized_pct: string;
}
export interface OrderRow {
  id: string; symbol: string; side: string; qty: string; type: string; class: string;
  status: string; limit: string; filled: string; submitted: string;
}
export interface BotState {
  cycles?: number; status?: string;
  last_forecast?: Forecast; last_signal?: Signal; last_agent?: Agent; last_mc?: McSummary;
  history?: { ts: string; line: string }[];
  trades?: Trade[];
}
export interface McSummary {
  var99: number; cvar99: number; var95: number; prob_breach: number;
  worst: number; vr_factor: number; n_paths: number;
}
export interface Forecast {
  ensemble: number; har: number; garch: number; kalman: number; realized_20: number;
  rv_ratio: number; regime: string; direction_bias: number;
}
export interface Signal {
  atm_iv: number; rv_forecast: number; vrp: number; vrp_ratio: number;
  iv_rank_proxy: number; term_slope: number | null; skew: number | null;
  action: string; confidence: number;
}
export interface Agent {
  decision: string; llm_used: boolean; pm_reason: string; bull_case: string;
  bear_case: string; risk_note: string;
}
export interface Trade {
  ts: string; name: string; contracts: number; credit: number;
  max_loss_per_ct: number; max_profit_per_ct: number; dte: number; risk_total: number;
  status: string; vrp: number; iv: number; rv_fc: number;
  legs?: { symbol: string; side: string; kind: string; strike: number; expiration: string }[];
  agent?: { decision: string; reason: string };
}
export interface LoopData {
  converged?: boolean;
  note?: string;
  rounds?: { round: number; n_variants: number; gate_pass?: boolean; dsr?: number;
    best?: LoopBest; failures?: string[]; note?: string }[];
  best?: LoopBest;
  frictions?: { fee_per_leg: number; slippage_pct_of_credit: number };
  started?: string; finished?: string;
}
export interface LoopBest {
  params?: Record<string, number>;
  trades_n?: number; win_rate?: number; profit_factor?: number; sharpe?: number;
  icir?: number; ic_months?: number; half_life?: number; oos_sharpe?: number;
  is_pnl?: number; oos_pnl?: number; total_pnl?: number;
}

export function useData(pollMs = 15000): { data: VulcData | null; error: string | null; loading: boolean } {
  const [data, setData] = useState<VulcData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch("/api/all", { cache: "no-store" });
        const j = await r.json();
        if (!alive) return;
        if (!j.ok) throw new Error(j.error || "api error");
        setData(j); setError(null);
      } catch (e) {
        if (alive) setError(String(e));
      } finally {
        if (alive) setLoading(false);
      }
    };
    tick();
    const id = setInterval(tick, pollMs);
    return () => { alive = false; clearInterval(id); };
  }, [pollMs]);
  return { data, error, loading };
}

export const money = (n: number | string | null | undefined) =>
  n == null ? "—" : (Number(n) < 0 ? "-$" : "$") + Math.abs(Number(n)).toLocaleString("en-US", { maximumFractionDigits: 2 });
export const pct = (n: number | string | null | undefined) =>
  n == null ? "—" : (100 * Number(n)).toFixed(2) + "%";
export const num = (n: number | string | null | undefined, d = 2) =>
  n == null ? "—" : Number(n).toFixed(d);
