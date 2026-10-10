"""Drive one text chat against a saved workflow with a real practice session, then print what happened.

    python3 lab/chat.py <slot> <PUB case> "msg 1" "msg 2" ... [--now 2026-10-16T15:00]
"""
import sys, json, time, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
import freya
from score import http
from run_scenarios import transcript
args = sys.argv[1:]; now = None
if "--now" in args: i = args.index("--now"); now = args[i + 1]; del args[i:i + 2]
slot, case, msgs = args[0], args[1], args[2:]
wf = json.load(open(ROOT / ".freya-agents.json"))[slot]["workflow_id"]
V = http("/v1/practice/sessions", {"case": case})["variables"]
if now: V["now"] = now
call = None
for m in msgs:
    body = {"message": m, "customerVariables": V}; body.update({"callId": call} if call else {"workflowId": wf})
    t = time.time()
    try: r = freya.api("POST", "/api/v2/chat/message", body)
    except Exception as e: print(f"USER: {m}\n  ERROR after {time.time() - t:.0f}s: {str(e)[:200]}"); break
    call = r["callId"]; print(f"USER: {m}\n  AGENT ({time.time() - t:.1f}s): {r.get('response')}" + (" [ended]" if r.get("endedByAgent") else ""), flush=True)
    if r.get("endedByAgent"): break
if call:
    try: freya.api("POST", "/api/v2/chat/end", {"callId": call})
    except Exception: pass
    time.sleep(2); print("\n--- timeline\n" + transcript(call))
led = http("/v1/practice/ledger/" + V["customer_id"])
print("\n--- ledger:", led.get("outcome"), led.get("reason"), "| promises", [(p["product_id"], p["amount"], p["date"]) for p in led["promises"]], "| notes", [(n.get("product_id"), n["reason"]) for n in led["notes"]],
      "| callbacks", led["callbacks"], "| transfers", led["transfers"], "\n    calls:", " > ".join(f"{c['tool']}{'' if c['result'].get('ok') else '(FAILED: ' + str(c['result'].get('error')) + ')'}" for c in led["calls"]))
