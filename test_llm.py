"""Quick LLM brain test — all 4 Cloudflare models through the agent router."""
import os
from dotenv import load_dotenv
load_dotenv()
from vulcan.agent import _chat, BRAIN_MAIN, BRAIN_BEAR, BRAIN_FAST

print("PM (glm-5.3-flash):", (_chat("pm", "Be terse.", "In one sentence: is selling a 9-DTE iron condor on SPY with VRP +2pts sensible in a calm regime?") or "FAILED")[:200])
print("\nBEAR (kimi-k2.7):", (_chat("bear", "Be terse.", "In one sentence: what kills a 9-DTE SPY condor fastest?") or "FAILED")[:200])
print("\nANALYST (llama-3.3-70b):", (_chat("analyst", "Be terse.", "One sentence: what does rv5/rv20=0.62 signal?") or "FAILED")[:200])
