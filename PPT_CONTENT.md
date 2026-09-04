VULCAN — COMPLETE DECK CONTENT SAVED
Saved to C:\Users\alokp\OneDrive\Desktop\vulcan\PPT_CONTENT.md (write tool, atomic — cannot corrupt).

What the document contains, slide by slide:

SLIDE 1 — COVER
Title: VULCAN
Subtitle: Autonomous AI Options Trading Agent
Tagline: Forging the Variance Risk Premium into Profit
Footer: AI Trading Agents Hackathon · lablabai x AlpacaHQ · Options Alpha Agents Track
Visual: vulcan_cover.png full bleed, dark overlay

SLIDE 2 — THE PROBLEM
Retail bots chase charts. Professionals harvest premium.
Body: Every options contract carries insurance pricing. The market charges a premium for volatility protection, and sometimes that price is simply wrong. When implied volatility is above forecast realized volatility, insurance is overpriced. Sell it. When it is below, buy it. That gap is the Variance Risk Premium, one of the most documented persistent edges in quantitative finance. VULCAN is an autonomous AI agent that finds that gap, sizes it honestly, and harvests it with hard coded limits. No hype trades. No chart guessing. One clean testable edge.
Footer: Built in 4 days for the lablabai x AlpacaHQ AI Trading Agents Hackathon

SLIDE 3 — WHAT VULCAN DOES (THE 3 STEP LOOP)
Step 1: FORECAST. Every 15 minutes VULCAN forecasts what SPY volatility will actually be, using three classic models voting together.
Step 2: MEASURE. It reads the live options chain from Alpaca and measures what the market is charging right now. The difference between the two is the tradeable gap.
Step 3: HARVEST. When the gap is wide enough to clear every risk gate, it sells premium through defined risk structures. When it is not, it does nothing. Doing nothing is a feature.

SLIDE 4 — THE AI DEBATE
The AI proposes. Math disposes.
Roles panel (3 rows):
GLM 5.2 — ANALYSTS: research the trade, feed briefs to both sides.
KIMI K2.7 — THE BEAR: adversarial by design. Argues against every single trade. Always.
GLM 5.3 FLASH — PORTFOLIO MANAGER: reads both briefs, issues the verdict. Can only VETO or SHRINK a trade. Can never increase size. Ever.
Failure safe box: if the LLM is unreachable, the system fails closed to the deterministic decision. The AI is a check, not a dependency.

SLIDE 5 — THE 7 RISK GATES
Headline: Seven gates. Zero exceptions.
G1 — DEFINED RISK ONLY: max loss is known in advance, bounded by structure construction. No naked options. Ever.
G2 — TURBULENCE GATE: no new premium selling when VIX is elevated or spiking, or when the regime model reads stress.
G3 — MONTE CARLO VaR: 32,768 simulated price paths per trade. Simulated tail losses must stay within the defined maximum before entry.
G4 — QUARTER KELLY SIZING: position size capped at one quarter of the Kelly optimum.
G5 — DISCIPLINED EXITS: take profit at 60 percent of max gain, cut at 75 percent of max loss, roll inside 2 days to expiry.
G6 — GAP JUDGMENT: the desk refuses structures where the model and the market disagree.
G7 — DISCIPLINE: number seven is discipline itself. The gate is the guard.

SLIDE 16 — CLOSING
Visual instruction: use vulcan_cover.png full bleed with dark overlay.
Closing line: The edge was never the chart. The edge was the forecast.
— VULCAN, autonomous AI desk, built in 4 days
Footer: Educational hackathon project · Paper trading only · Nothing here is financial advice

DOCUMENT METADATA (for the PDF maker, not for slides):
Title: VULCAN — Autonomous AI Options Trading Agent
Subject: Autonomous AI desk trading the variance risk premium
Creator: VULCAN autonomous desk
Keywords: variance risk premium, HAR, GARCH, Kalman filter, HMM regime detection, iron fly, iron condor, defined risk
END OF DOCUMENT
