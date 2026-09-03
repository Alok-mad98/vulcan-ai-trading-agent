"""VULCAN Model 3 — LLM Decision Agent (TradingAgents pattern).

Pipeline: 4 analysts -> bull/bear debate (capped) -> risk debate -> PM verdict.
Dual-tier LLMs: cheap for analysts, strong for PM. FAIL-CLOSED: if the LLM is
unreachable the deterministic quant decision stands (never blocks on AI).

The LLM can only VETO or SHRINK a trade — it can never grow risk beyond what
Model 2 proposed and the risk gates approved (Pin Desk / Horizon Blackline rule).
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

ZAI_KEY = os.getenv("Z_AI_API_KEY", "")
ZAI_URL = "https://api.z.ai/api/paas/v4/chat/completions"
CF_ACCOUNT = os.getenv("CF_ACCOUNT_ID", "")
CF_TOKEN = os.getenv("CF_API_TOKEN", "")

# VULCAN brain — Cloudflare Workers AI (startup plan)
BRAIN_MAIN = "@cf/zai-org/glm-5.3-flash"        # PM / final decisions (main brain)
BRAIN_DEEP = "@cf/zai-org/glm-5.2"              # analysts + deep work
BRAIN_BEAR = "@cf/moonshotai/kimi-k2.7-code"    # adversarial bear researcher

STRONG_MODEL = "pm"     # -> BRAIN_MAIN
QUICK_MODEL = "analyst" # -> BRAIN_DEEP (glm-5.2)


def _run_model(model: str, system: str, user: str, max_tokens: int = 1200) -> str | None:
    body = json.dumps({"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user}], "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/ai/run/{model}",
        data=body, method="POST")
    req.add_header("Authorization", f"Bearer {CF_TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read())
        msg = resp["result"]["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        if not content:
            content = (msg.get("reasoning_content") or "").strip()[-600:]
        return content or None
    except Exception:
        return None


def _chat(model: str, system: str, user: str, timeout: int = 45) -> str | None:
    """Route: pm -> GLM-5.3-flash (fallback GLM-5.2), analyst -> Llama-3.3-70b-fast,
    bear -> Kimi-K2.7. Z.ai tried first if key present (paid direct API)."""
    if ZAI_KEY:
        zai_model = "glm-4.6" if model in ("pm", "strong") else "glm-4.5-air"
        body = json.dumps({
            "model": zai_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0.2, "max_tokens": 900,
        }).encode()
        req = urllib.request.Request(ZAI_URL, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {ZAI_KEY}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception:
            pass
    cf_model = {"pm": BRAIN_MAIN, "bear": BRAIN_BEAR,
                "analyst": BRAIN_DEEP, "strong": BRAIN_DEEP}.get(model, BRAIN_MAIN)
    out = _run_model(cf_model, system, user)
    if out is None and cf_model != BRAIN_DEEP:
        out = _run_model(BRAIN_DEEP, system, user)
    return out


# ---------------- analysts ----------------
def analyst_technical(fc) -> str:
    d = fc.direction
    return (f"TECHNICAL: SPY momentum ROC5={d['roc5']*100:+.2f}%, range-position RSV10={d['rsv10']:.2f}, "
            f"up-day count CNTP5={d['cntp5']:.0%}, price-volume corr10={d.get('corr10') if d.get('corr10') is not None else 'n/a'}. "
            f"Direction bias {fc.direction_bias:+.2f} (tanh-blended).")


def analyst_volatility(fc, sig) -> str:
    return (f"VOLATILITY: HAR={fc.har*100:.1f}% GARCH={fc.garch*100:.1f}% Kalman={fc.kalman*100:.1f}% "
            f"-> ensemble {fc.ensemble*100:.1f}% vs ATM IV {sig.atm_iv*100:.1f}% "
            f"(VRP {sig.vrp*100:+.1f} pts, ratio {sig.vrp_ratio:.2f}, IV-rank-proxy {sig.iv_rank_proxy:.2f}). "
            f"Term slope {sig.term_slope if sig.term_slope is None else round(sig.term_slope,3)}, "
            f"put skew {sig.skew if sig.skew is None else round(sig.skew,3)}. Regime={fc.regime['regime']} "
            f"(p_stress={fc.regime['prob_stress']:.2f}), rv5/rv20={fc.rv_ratio:.2f}.")


def analyst_news() -> str:
    """News/sentiment: cheap-model scan. Degrades to 'no data' silently (fail-closed)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    txt = _chat(QUICK_MODEL, "You are a market news analyst. Reply in 2 sentences max.",
                f"Any major macro/event risk in the next 7 days ({today}) that could spike SPY volatility "
                f"by more than 1.5x (CPI/FOMC/geopolitics)? If unsure say 'No known catalysts'.")
    return f"NEWS: {txt.strip() if txt else 'No news feed available (fail-closed: assume no shock).'}"


def analyst_flow(chain: list) -> str:
    """Options-flow microstructure: put/call IV gap + skew snapshot."""
    puts_iv = [s["impliedVolatility"] for s in chain if s.get("impliedVolatility") and "P" in s["symbol"][-9:]]
    calls_iv = [s["impliedVolatility"] for s in chain if s.get("impliedVolatility") and "C" in s["symbol"][-9:]]
    if not puts_iv or not calls_iv:
        return "FLOW: chain IV unavailable."
    return (f"FLOW: chain-wide mean put IV {sum(puts_iv)/len(puts_iv)*100:.1f}% vs call IV "
            f"{sum(calls_iv)/len(calls_iv)*100:.1f}% -> {'put bid (defensive)' if sum(puts_iv)/len(puts_iv) > sum(calls_iv)/len(calls_iv)*1.05 else 'balanced/call-tilt'} "
            f"across {len(puts_iv)+len(calls_iv)} priced contracts.")


# ---------------- debate + PM ----------------
@dataclass
class AgentVerdict:
    decision: str            # APPROVE / VETO / SHRINK
    shrink_factor: float = 1.0
    bull_case: str = ""
    bear_case: str = ""
    risk_note: str = ""
    pm_reason: str = ""
    llm_used: bool = False


def run_agent(fc, sig, plan, risk_reasons: list[str], contracts: int) -> AgentVerdict:
    """Debate pipeline. Returns verdict; LLM failure -> APPROVE deterministic (fail-closed)."""
    brief = "\n".join([
        analyst_technical(fc),
        analyst_volatility(fc, sig),
        analyst_news(),
    ])

    bull = _chat(QUICK_MODEL, "You are the BULL researcher. Argue FOR this trade in <=3 sentences. Cite the numbers.",
                 f"{brief}\n\nTRADE: {plan.name} {plan.dte}dte credit={plan.credit:+.2f} "
                 f"max_loss=${plan.max_loss:.2f}/ct risked on {contracts} contracts.\nRisk gates: {'; '.join(risk_reasons)}")
    bear = _chat(QUICK_MODEL, "You are the BEAR researcher. Argue AGAINST this trade in <=3 sentences. Find the failure mode.",
                 f"{brief}\n\nTRADE: {plan.name} {plan.dte}dte credit={plan.credit:+.2f} "
                 f"max_loss=${plan.max_loss:.2f}/ct on {contracts} contracts.")

    risk_note = _chat(QUICK_MODEL,
                      "You are the RISK manager. In <=2 sentences, state the worst realistic outcome and whether the defined risk is acceptable.",
                      f"{brief}\nStructure: {plan.name}, width={plan.width:.1f}, credit={plan.credit:+.2f}, "
                      f"max_loss=${plan.max_loss:.2f}/ct, dte={plan.dte}, regime={fc.regime['regime']}, "
                      f"VRP={sig.vrp*100:+.1f}pts")

    pm_raw = _chat(STRONG_MODEL,
                   "You are the PORTFOLIO MANAGER. Final authority. Respond with ONLY JSON: "
                   '{"decision":"APPROVE|VETO|SHRINK","shrink_factor":1.0,"reason":"..."} '
                   "Rules: you may VETO (kill) or SHRINK (reduce size, shrink_factor<1) but never increase size. "
                   "Veto if: (a) news shows a hard catalyst inside the DTE window, (b) the bear case exposes a gap risk "
                   "the defined risk does not cover, (c) VRP thesis contradicted by term structure/skew.",
                   f"{brief}\nBULL: {bull}\nBEAR: {bear}\nRISK: {risk_note}\n"
                   f"PROPOSED: {plan.name} x{contracts} @ credit {plan.credit:+.2f}, max loss ${plan.max_loss*contracts:.0f}")

    verdict = AgentVerdict(decision="APPROVE", bull_case=bull or "", bear_case=bear or "",
                           risk_note=risk_note or "", pm_reason="")
    if pm_raw:
        verdict.llm_used = True
        try:
            j = json.loads(pm_raw[pm_raw.index("{"): pm_raw.rindex("}") + 1])
            verdict.decision = j.get("decision", "APPROVE").upper()
            verdict.shrink_factor = float(j.get("shrink_factor", 1.0) or 1.0)
            verdict.pm_reason = j.get("reason", "")
            if verdict.decision == "SHRINK" and not (0 < verdict.shrink_factor <= 1.0):
                verdict.shrink_factor = 1.0
        except Exception:
            verdict.decision = "APPROVE"
    else:
        verdict.pm_reason = "LLM unavailable — fail-closed to deterministic decision (risk gates already enforced)."
    return verdict
