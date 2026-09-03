"""VULCAN remote job poller — bridges the dashboard to the local loop engine.

Flow: dashboard "Run Loop" -> worker KV job -> this poller (every 2 min via
scheduled task) picks it up -> runs loop_runner with progress callbacks ->
pushes % progress -> dashboard shows the bar.

Run modes:
  python -m vulcan.remote --once    # single poll (scheduled task every 2 min)
  python -m vulcan.remote           # continuous polling loop
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

TOKEN = (Path(__file__).resolve().parent.parent / ".push_token").read_text().strip()
DASH = "https://vulcan-dashboard.arechampionw.workers.dev"


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{DASH}{path}", data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (VULCAN poller)")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def push_progress(pct: float, round_no: int, total_rounds: int, msg: str, done: bool = False):
    try:
        _post(f"/api/jobs/progress?tok={TOKEN}",
              {"pct": round(pct, 1), "round": round_no, "total_rounds": total_rounds,
               "message": msg[:200], "done": done, "ts": time.time()})
        print(f"  [progress {pct:.0f}%] r{round_no}: {msg}")
    except Exception as e:
        print(f"  progress push failed: {e}")


def run_loop_job(job: dict):
    """Run the loop-engineering engine with live progress pushes."""
    import pandas as pd
    from vulcan import data as d
    from vulcan.loop_runner import run_until_perfect

    max_rounds = int(job.get("max_rounds", 3))
    push_progress(1, 0, max_rounds, "fetching SPY data...")
    bars = d.get_bars("SPY", days=400)
    close = pd.DataFrame(bars).set_index("t")["c"]
    push_progress(4, 0, max_rounds, f"{len(close)} bars — computing walk-forward RV forecasts...")

    # wrap run_until_perfect: easiest progress = monkey-patch the round loop via
    # a generator of progress pushes at round + variant granularity.
    # loop_runner already prints per variant; we add pushes by re-implementing
    # the outer progress accounting here via a callback thread.
    import threading

    prog = {"done": False}

    def progress_ticker():
        est_rounds = max_rounds
        # poll loop_runs.json growth + elapsed to estimate % (crude but honest)
        t0 = time.time()
        est_total = 60 * est_rounds  # ~60s per round empirical
        while not prog["done"]:
            el = time.time() - t0
            pct = min(95.0, 4 + 91 * el / est_total)
            push_progress(pct, min(est_rounds, 1 + int(el / 60)), est_rounds, "running variants...")
            time.sleep(12)

    th = threading.Thread(target=progress_ticker, daemon=True)
    th.start()
    try:
        log = run_until_perfect(close, max_rounds=max_rounds)
    finally:
        prog["done"] = True
        time.sleep(0.5)

    b = log.get("best") or {}
    msg = (f"converged={log.get('converged')} rounds={len(log.get('rounds', []))} "
           f"sr={b.get('sharpe', 0):.1f} icir={b.get('icir', 0):.2f} oos=${b.get('oos_pnl', 0):.0f}")
    push_progress(100, len(log.get("rounds", [])), max_rounds, msg, done=True)
    # push full loop results for the dashboard
    try:
        loop_p = Path(__file__).resolve().parent.parent / "data" / "loop_runs.json"
        _post(f"/api/push?tok={TOKEN}", {"loop": json.loads(loop_p.read_text())})
    except Exception as e:
        print(f"loop results push failed: {e}")
    print(f"LOOP JOB DONE: {msg}")


def poll_once():
    try:
        req = urllib.request.Request(f"{DASH}/api/jobs/next?tok={TOKEN}", data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "Mozilla/5.0 (VULCAN poller)")
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
    except Exception as e:
        print(f"poll failed: {e}")
        return
    job = resp.get("job")
    if not job:
        return
    print(f"JOB: {job.get('type')} max_rounds={job.get('max_rounds')}")
    try:
        if job.get("type") in ("loop", "loop_continuous"):
            run_loop_job(job)
    except Exception as e:
        push_progress(100, 0, 1, f"job FAILED: {e}", done=True)
        print(f"job error: {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=120)
    args = ap.parse_args()
    if args.once:
        poll_once()
    else:
        while True:
            poll_once()
            time.sleep(args.interval)
