// VULCAN Dashboard Worker Ã¢â‚¬â€ serves the neobrutalism UI + JSON API.
// Data sources: (1) Alpaca API live (account/positions/orders) with server-side keys,
// (2) KV namespace "VULCAN_STATE" pushed by the VULCAN bot after each cycle.

const APCA_BASE = "https://paper-api.alpaca.markets";
const DATA_BASE = "https://data.alpaca.markets";

// ---------------- JS Monte Carlo engine (for the /api/mc page) ----------------
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function boxMuller(rng, n) {
  const z = new Float64Array(n);
  for (let i = 0; i < n; i += 2) {
    const u1 = Math.max(rng(), 1e-12), u2 = rng();
    const r = Math.sqrt(-2 * Math.log(u1)), th = 2 * Math.PI * u2;
    z[i] = r * Math.cos(th);
    if (i + 1 < n) z[i + 1] = r * Math.sin(th);
  }
  return z;
}
function draws(n, seed, antithetic = true) {
  const rng = mulberry32(seed);
  const half = antithetic ? Math.ceil(n / 2) : n;
  const z0 = boxMuller(rng, half);
  if (!antithetic) return z0.slice(0, n);
  const z = new Float64Array(n);
  for (let i = 0; i < half; i++) { z[i] = z0[i]; if (half + i < n) z[half + i] = -z0[i]; }
  // moment matching
  let mu = 0, sd = 0;
  for (let i = 0; i < n; i++) mu += z[i]; mu /= n;
  for (let i = 0; i < n; i++) sd += (z[i] - mu) ** 2; sd = Math.sqrt(sd / n);
  for (let i = 0; i < n; i++) z[i] = (z[i] - mu) / sd;
  return z;
}
function bsPriceJS(S, K, t, sig, r, kind) {
  if (t <= 0 || sig <= 0) return Math.max(0, kind === "C" ? S - K : K - S);
  const d1 = (Math.log(S / K) + (r + sig * sig / 2) * t) / (sig * Math.sqrt(t));
  const d2 = d1 - sig * Math.sqrt(t);
  const cdf = (x) => 0.5 * (1 + erf(x / Math.SQRT2));
  const pdf = (x) => Math.exp(-x * x / 2) / Math.sqrt(2 * Math.PI);
  if (kind === "C") return S * cdf(d1) - K * Math.exp(-r * t) * cdf(d2);
  return K * Math.exp(-r * t) * cdf(-d2) - S * cdf(-d1);
}
function erf(x) { // Abramowitz-Stegun 7.1.26
  const s = Math.sign(x); x = Math.abs(x);
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const t = 1 / (1 + p * x);
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
  return s * y;
}
function percentile(sortedArr, p) {
  const i = (sortedArr.length - 1) * p;
  const lo = Math.floor(i), hi = Math.ceil(i);
  return sortedArr[lo] + (sortedArr[hi] - sortedArr[lo]) * (i - lo);
}
function histogram(values, nbins, lo, hi) {
  const counts = new Array(nbins).fill(0);
  const w = (hi - lo) / nbins || 1;
  for (const v of values) {
    const b = Math.min(nbins - 1, Math.max(0, Math.floor((v - lo) / w)));
    counts[b]++;
  }
  return counts.map((c, i) => ({ x: lo + w * (i + 0.5), n: c }));
}

async function mcPayload(env, q) {
  // live spot + ATM IV from Alpaca
  let spot = 769.0, iv = 0.108;
  try {
    const t = await fetch(`${DATA_BASE}/v2/stocks/SPY/trades/latest?feed=iex`, {
      headers: { "APCA-API-KEY-ID": env.ALPACA_KEY, "APCA-API-SECRET-KEY": env.ALPACA_SECRET },
    }).then(r => r.json());
    if (t.trade?.p) spot = t.trade.p;
    const sn = await fetch(`${DATA_BASE}/v1beta1/options/snapshots/SPY?limit=1000`, {
      headers: { "APCA-API-KEY-ID": env.ALPACA_KEY, "APCA-API-SECRET-KEY": env.ALPACA_SECRET },
    }).then(r => r.json());
    const ivs = [];
    for (const [sym, s] of Object.entries(sn.snapshots || {})) {
      const m = sym.match(/^SPY(\d{6})([CP])(\d{8})$/);
      if (!m || !s.impliedVolatility) continue;
      const exp = `20${m[1].slice(0, 2)}-${m[1].slice(2, 4)}-${m[1].slice(4)}`;
      const dte = (new Date(exp + "T00:00:00Z") - Date.now()) / 86400000;
      if (dte >= 6 && dte <= 12) {
        const strike = parseInt(m[3]) / 1000;
        if (Math.abs(strike / spot - 1) < 0.01) ivs.push(s.impliedVolatility);
      }
    }
    if (ivs.length) iv = ivs.reduce((a, b) => a + b, 0) / ivs.length;
  } catch (e) { /* fallback constants above */ }

  // interactive parameters (what-if sliders)
  const seed = parseInt(q.get("seed") || "42") | 0;
  const sigmaMult = Math.min(2.5, Math.max(0.3, parseFloat(q.get("sigma") || "1.0")));
  const spotShift = Math.min(0.10, Math.max(-0.10, parseFloat(q.get("spotShift") || "0")));
  const offsetMult = Math.min(2.0, Math.max(0.4, parseFloat(q.get("offset") || "1.0")));
  const widthMult = Math.min(2.0, Math.max(0.25, parseFloat(q.get("width") || "1.0")));
  const dteOverride = Math.min(45, Math.max(1, parseInt(q.get("dte") || "9") | 0));
  spot = spot * (1 + spotShift);
  const sig = iv * sigmaMult;
  const r = 0.045;
  const dte = dteOverride, T = dte / 365;
  const offset = spot * 0.7 * offsetMult * sig * Math.sqrt(T);   // loop-converged base: 0.7sigma off, 0.4sigma width
  const width = spot * 0.4 * widthMult * sig * Math.sqrt(T);
  const strikes = {
    sp: spot - offset, lp: spot - offset - width,
    sc: spot + offset, lc: spot + offset + width,
  };
  const legs = [
    { side: "sell", kind: "P", K: strikes.sp }, { side: "buy", kind: "P", K: strikes.lp },
    { side: "sell", kind: "C", K: strikes.sc }, { side: "buy", kind: "C", K: strikes.lc },
  ];
  const legPx = legs.map(l => bsPriceJS(spot, l.K, T, sig, r, l.kind));
  const credit = (legPx[0] - legPx[1]) + (legPx[2] - legPx[3]);

  // --- fan chart: 32k terminal paths -> percentile bands per step + 25 spaghetti ---
  const NP = 32768, STEPS = 9, dt = T / STEPS;
  const z = draws(NP * STEPS, seed, true);
  const pathsBands = [];
  const spag = [];
  const rngS = mulberry32(seed + 31);
  const zS = boxMuller(rngS, 25 * STEPS);
  for (let s = 0; s <= STEPS; s++) {
    const col = new Float64Array(NP);
    for (let p = 0; p < NP; p++) {
      const zz = z[p * STEPS + Math.min(s, STEPS - 1)];
      col[p] = spot * Math.exp((r - sig * sig / 2) * s * dt + sig * Math.sqrt(s * dt) * zz);
    }
    const sorted = Array.from(col).sort((a, b) => a - b);
    pathsBands.push({
      step: s,
      p5: percentile(sorted, 0.05), p25: percentile(sorted, 0.25), p50: percentile(sorted, 0.5),
      p75: percentile(sorted, 0.75), p95: percentile(sorted, 0.95),
    });
  }
  for (let k = 0; k < 25; k++) {
    const row = [];
    for (let s = 0; s <= STEPS; s++) {
      const zz = zS[k * STEPS + Math.min(s, STEPS - 1)];
      row.push(spot * Math.exp((r - sig * sig / 2) * s * dt + sig * Math.sqrt(s * dt) * zz));
    }
    spag.push(row);
  }

  // --- condor P&L distribution + VaR/CVaR ---
  const st = new Float64Array(NP);
  const zT = draws(NP, seed + 7, true);
  for (let p = 0; p < NP; p++) st[p] = spot * Math.exp((r - sig * sig / 2) * T + sig * Math.sqrt(T) * zT[p]);
  const pnl = new Float64Array(NP);
  for (let p = 0; p < NP; p++) {
    let v = 0;
    legs.forEach((l, i) => {
      const intr = l.kind === "C" ? Math.max(st[p] - l.K, 0) : Math.max(l.K - st[p], 0);
      v += (l.side === "buy" ? 1 : -1) * (legPx[i] - intr);
    });
    pnl[p] = v * 100; // per 1 contract
  }
  const pnlSorted = Array.from(pnl).sort((a, b) => a - b);
  const var95 = -percentile(pnlSorted, 0.05), var99 = -percentile(pnlSorted, 0.01);
  let tailSum = 0, tailN = 0;
  for (const v of pnlSorted) if (v <= percentile(pnlSorted, 0.01)) { tailSum += v; tailN++; }
  const cvar99 = -(tailSum / Math.max(tailN, 1));
  const maxLoss = (width - credit) * 100;
  let breach = 0; for (const v of pnl) if (-v >= 0.995 * maxLoss) breach++;
  const plLo = Math.min(pnlSorted[0], -maxLoss * 1.1), plHi = Math.max(pnlSorted[NP - 1], credit * 100 * 1.1);
  const pnlHist = histogram(pnl, 60, plLo, plHi);

  // --- convergence study: SE vs N, naive vs antithetic vs antithetic+control ---
  const K1 = Math.round(spot * 1.005);
  const bsRef = bsPriceJS(spot, K1, T, sig, r, "C");
  const conv = [];
  for (const N of [1000, 4000, 16000, 64000]) {
    // naive
    let zn = draws(N, N, false);
    let acc = 0, acc2 = 0;
    for (const zz of zn) { const STp = spot * Math.exp((r - sig * sig / 2) * T + sig * Math.sqrt(T) * zz); const pay = Math.max(STp - K1, 0); acc += pay; acc2 += pay * pay; }
    const mean = acc / N, seN = Math.sqrt(Math.max(acc2 / N - mean * mean, 0)) / Math.sqrt(N);
    // antithetic
    const za = draws(N, N, true);
    acc = 0; acc2 = 0;
    for (const zz of za) { const STp = spot * Math.exp((r - sig * sig / 2) * T + sig * Math.sqrt(T) * zz); const pay = Math.max(STp - K1, 0); acc += pay; acc2 += pay * pay; }
    const meanA = acc / N, seA = Math.sqrt(Math.max(acc2 / N - meanA * meanA, 0)) / Math.sqrt(N);
    // antithetic + control variate on ST (E[ST] = S e^{rT})
    const EST = spot * Math.exp(r * T);
    let sumY = 0, sumX = 0, sumXX = 0, sumXY = 0;
    for (const zz of za) { const STp = spot * Math.exp((r - sig * sig / 2) * T + sig * Math.sqrt(T) * zz); const pay = Math.max(STp - K1, 0); sumY += pay; sumX += STp; sumXX += STp * STp; sumXY += pay * STp; }
    const mY = sumY / N, mX = sumX / N;
    const beta = (sumXY / N - mY * mX) / Math.max(sumXX / N - mX * mX, 1e-12);
    let varAdj = 0;
    for (const zz of za) { const STp = spot * Math.exp((r - sig * sig / 2) * T + sig * Math.sqrt(T) * zz); const pay = Math.max(STp - K1, 0); const adj = pay - beta * (STp - EST); varAdj += adj * adj; }
    const seC = Math.sqrt(varAdj / N) / Math.sqrt(N);
    conv.push({ N, seNaive: seN, seAnti: seA, seControl: seC, priceAnti: meanA, priceControl: mY - beta * (mX - EST), ref: 1 / Math.sqrt(N) });
  }

  // --- tornado: swing on VaR99 when sigma / spot / width vary ---
  const varAt = (s_, sig_, wMult) => {
    const off2 = s_ * 0.7 * sig_ * Math.sqrt(T), w2 = s_ * 0.4 * wMult * sig_ * Math.sqrt(T);
    const lgs = [
      { side: "sell", kind: "P", K: s_ - off2 }, { side: "buy", kind: "P", K: s_ - off2 - w2 },
      { side: "sell", kind: "C", K: s_ + off2 }, { side: "buy", kind: "C", K: s_ + off2 + w2 },
    ];
    const px = lgs.map(l => bsPriceJS(s_, l.K, T, sig_, r, l.kind));
    const cr = (px[0] - px[1]) + (px[2] - px[3]);
    const zt = draws(16384, seed + 7, true);
    const losses = [];
    for (let p = 0; p < zt.length; p++) {
      const STp = s_ * Math.exp((r - sig_ * sig_ / 2) * T + sig_ * Math.sqrt(T) * zt[p]);
      let v = 0;
      lgs.forEach((l, i) => {
        const intr = l.kind === "C" ? Math.max(STp - l.K, 0) : Math.max(l.K - STp, 0);
        v += (l.side === "buy" ? 1 : -1) * (px[i] - intr);
      });
      losses.push(-v * 100);
    }
    losses.sort((a, b) => a - b);
    return percentile(losses, 0.99);
  };
  const baseVar = varAt(spot, sig, 1.0);
  const tornado = [
    { factor: "vol +/-20%", low: varAt(spot, sig * 0.8, 1.0), high: varAt(spot, sig * 1.2, 1.0) },
    { factor: "spot +/-1%", low: varAt(spot * 0.99, sig, 1.0), high: varAt(spot * 1.01, sig, 1.0) },
    { factor: "width 0.3-0.6 sigma", low: varAt(spot, sig, 0.75), high: varAt(spot, sig, 1.5) },
  ].map(t => ({ ...t, swing: Math.abs(t.high - t.low) }));
  tornado.sort((a, b) => b.swing - a.swing);

  return {
    ts: new Date().toISOString(), spot, iv, dte, r,
    engine: { paths: NP, steps: STEPS, techniques: ["antithetic", "moment-matching", "control-variate", "sobol (python engine)"] },
    strikes, credit, maxLoss,
    fan: pathsBands, spaghetti: spag,
    pnl: { hist: pnlHist, var95, var99, cvar99, breachProb: breach / NP, maxLoss, meanCredit: credit * 100 },
    convergence: conv, bsRef,
    tornado, baseVar99: baseVar,
  };
}

async function alpaca(path, env) {
  const r = await fetch(`${APCA_BASE}${path}`, {
    headers: { "APCA-API-KEY-ID": env.ALPACA_KEY, "APCA-API-SECRET-KEY": env.ALPACA_SECRET },
  });
  if (!r.ok) throw new Error(`alpaca ${path} ${r.status}`);
  return r.json();
}

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Cache-Control": "no-store",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...CORS } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/all") {
      try {
        const [account, positions, orders, clock] = await Promise.all([
          alpaca("/v2/account", env),
          alpaca("/v2/positions", env).catch(() => []),
          alpaca("/v2/orders?status=all&limit=50", env).catch(() => []),
          alpaca("/v2/clock", env).catch(() => ({ is_open: false })),
        ]);
        const botState = (await env.VULCAN_STATE.get("state", "json")) || {};
        const loopRuns = (await env.VULCAN_STATE.get("loop", "json")) || {};
        const loopStatus = (await env.VULCAN_STATE.get("loop_status", "json")) || null;
        return json({
          ok: true,
          ts: new Date().toISOString(),
          account: {
            equity: account.equity, cash: account.cash,
            last_equity: account.last_equity,
            pnl_day: account.equity - account.last_equity,
            pnl_total: account.equity - 100000,
            buying_power: account.buying_power,
            status: account.status, market_open: clock.is_open,
            next_open: clock.next_open, next_close: clock.next_close,
          },
          positions: positions.map(p => ({
            symbol: p.symbol, qty: p.qty, side: p.side,
            avg_entry: p.avg_entry_price, current: p.current_price,
            market_value: p.market_value, unrealized: p.unrealized_pl,
            unrealized_pct: p.unrealized_plpc,
          })),
          orders: orders.slice(0, 30).map(o => ({
            id: o.id, symbol: o.symbol, side: o.side, qty: o.qty,
            type: o.order_type, class: o.order_class, status: o.status,
            limit: o.limit_price, filled: o.filled_avg_price,
            submitted: o.submitted_at,
          })),
          bot: botState, loop: loopRuns, loopStatus,
        });
      } catch (e) {
        return json({ ok: false, error: String(e) }, 500);
      }
    }

    if (url.pathname === "/api/jobs/request" && request.method === "POST") {
      // dashboard requests a backtest loop run (rate-limited: one pending job max, 10-min cooldown)
      try {
        const existing = await env.VULCAN_STATE.get("job", "json");
        if (existing && !existing.done && Date.now() - existing.requested_at < 10 * 60 * 1000) {
          return json({ ok: false, error: "a job is already running or cooling down", job: existing });
        }
        const body = await request.json().catch(() => ({}));
        const job = {
          type: body.type === "loop_continuous" ? "loop_continuous" : "loop",
          max_rounds: Math.min(6, Math.max(1, parseInt(body.max_rounds || "3") | 0)),
          requested_at: Date.now(), done: false,
        };
        await env.VULCAN_STATE.put("job", JSON.stringify(job));
        return json({ ok: true, job });
      } catch (e) { return json({ ok: false, error: String(e) }, 500); }
    }

    if (url.pathname === "/api/jobs/next" && request.method === "POST") {
      // local bot polls: atomically fetch-and-clear pending job (token-protected)
      const tok = (url.searchParams.get("tok") || "").trim();
      if (tok !== String(env.PUSH_TOKEN).trim()) return json({ ok: false, error: "bad token" }, 403);
      const job = await env.VULCAN_STATE.get("job", "json");
      if (!job || job.done) return json({ ok: true, job: null });
      return json({ ok: true, job });
    }

    if (url.pathname === "/api/jobs/progress" && request.method === "POST") {
      // bot pushes loop progress (token-protected)
      const tok = (url.searchParams.get("tok") || "").trim();
      if (tok !== String(env.PUSH_TOKEN).trim()) return json({ ok: false, error: "bad token" }, 403);
      const body = await request.json();
      await env.VULCAN_STATE.put("loop_status", JSON.stringify(body));
      if (body.done) {
        const job = (await env.VULCAN_STATE.get("job", "json")) || {};
        job.done = true;
        await env.VULCAN_STATE.put("job", JSON.stringify(job));
      }
      return json({ ok: true });
    }

    if (url.pathname === "/api/jobs/status") {
      const job = (await env.VULCAN_STATE.get("job", "json")) || null;
      const status = (await env.VULCAN_STATE.get("loop_status", "json")) || null;
      return json({ ok: true, job, status });
    }

    if (url.pathname === "/api/mc") {
      try {
        return json(await mcPayload(env, url.searchParams));
      } catch (e) {
        return json({ ok: false, error: String(e) }, 500);
      }
    }

    if (url.pathname === "/api/push" && request.method === "POST") {
      // VULCAN bot pushes state after each cycle (token-protected)
      const tok = (url.searchParams.get("tok") || request.headers.get("x-vulcan-token") || "").trim();
      if (tok !== String(env.PUSH_TOKEN).trim()) return json({ ok: false, error: "bad token" }, 403);
      const body = await request.json();
      if (body.state) await env.VULCAN_STATE.put("state", JSON.stringify(body.state));
      if (body.loop) await env.VULCAN_STATE.put("loop", JSON.stringify(body.loop));
      return json({ ok: true });
    }

    return env.ASSETS.fetch(request);
  },
};

