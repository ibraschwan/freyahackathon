"""Play a customer by hand against a phone agent, in the terminal, and score the bank's records at the end.

For scenarios the simulated customer refuses to play (manipulation attempts), or to try anything yourself.

    python3 tests/talk.py <slot> <scenario id>            # e.g. ab X03: shows the script to play and what the records must show
    python3 tests/talk.py <slot> <PUB case> [--now 2026-10-16T15:00]     # free play on that account, nothing is scored

<slot> is a name from .freya-agents.json (ab = the agent the builder made, g-ab = the hand-written reference).
Type what the customer says and press Enter. Empty line or /end ends the call. /ledger shows the bank's records so far.
Needs FREYA_API_KEY and FREYA_BANK_TEAM_KEY (source env.sh). Do not run it while a simulation runs: the agent is slow then.
"""
import json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
import freya
from score import http, score_ledger

def show(led):
    print("  outcome:", led.get("outcome"), "/", led.get("reason"))
    print("  promises:", [(p["product_id"], p["amount"], p["date"]) for p in led["promises"]], "| notes:", [(n.get("product_id"), n["reason"]) for n in led["notes"]])
    print("  callbacks:", [(c["date"], c["time"]) for c in led["callbacks"]], "| transfers:", [t["queue"] for t in led["transfers"]])
    print("  bank calls:", " > ".join(c["tool"] + ("" if c["result"].get("ok") else "(refused)") for c in led["calls"]) or "none")

def main():
    args = sys.argv[1:]; now = None
    if "--now" in args: i = args.index("--now"); now = args[i + 1]; del args[i:i + 2]
    if len(args) != 2: sys.exit(__doc__)
    slot, what = args
    agents = json.load(open(ROOT / ".freya-agents.json"))
    if slot not in agents: sys.exit(f"unknown slot '{slot}'. Known: {', '.join(agents)}")
    scen = {s["id"]: s for s in json.load(open(ROOT / "tests" / "scenarios.json"))}.get(what)
    case = scen["session"] if scen else what
    V = http("/v1/practice/sessions", {"case": case}).get("variables")
    if not V: sys.exit(f"the bank mock knows no practice case '{case}'")
    V["now"] = now or (scen["variables"]["now"] if scen else V["now"])
    if scen:
        i = scen["identity"]
        print(f"\nSCENARIO {scen['id']}: {scen['title']}")
        print("You are" + (" NOT" if scen.get("third_party") else "") + f" {V['first_name']} {V['last_name']}. Security answers on file: " + ", ".join(f"{k} = {v}" for k, v in i.items()))
        print("Products:", json.dumps(scen["products"]))
        print("Script:", scen["script"])
        e = scen["expected"]; notes_b = scen["expected_b_notes"]
        print(f"Records must show: {e['outcome']} / {e['reason']}, promises {[(p['product_id'], p['amount'], p['date']) for p in e['promises']]}, notes (Brief B rules) {[(n['product_id'], n['reason']) for n in notes_b]}, callbacks {e['callbacks']}, transfers {e['transfers']}")
        print("Also watch for:", "; ".join(scen["checks"]))
    print(f"\nCall time: {V['now']}. Say something to start (for example: Hello?).\n")
    call = None
    while True:
        try: line = input("YOU:   ").strip()
        except (EOFError, KeyboardInterrupt): break
        if line in ("", "/end"): break
        if line == "/ledger": show(http("/v1/practice/ledger/" + V["customer_id"])); continue
        body = {"message": line, "customerVariables": V}; body.update({"callId": call} if call else {"workflowId": agents[slot]["workflow_id"]})
        t = time.time()
        try: r = freya.api("POST", "/api/v2/chat/message", body)
        except Exception as ex:
            print(f"   (no answer after {time.time() - t:.0f} s: {str(ex)[:120]}. Send the line again, or /end.)"); continue
        call = r.get("callId") or call
        print(f"AGENT: {r.get('response')}   [{time.time() - t:.0f} s]")
        if r.get("endedByAgent"): print("   (the agent ended the call)"); break
    if call:
        try: freya.api("POST", "/api/v2/chat/end", {"callId": call})
        except Exception: pass
        time.sleep(3)
    led = http("/v1/practice/ledger/" + V["customer_id"])
    print("\nTHE BANK'S RECORDS"); show(led)
    if scen:
        for rules in ("B", "A"):
            exp = dict(scen["expected"], notes=scen["expected_b_notes"] if rules == "B" else scen["expected"]["notes"])
            bad = score_ledger(dict(scen, expected=exp), led)["failed"]
            print(f"Scored with Brief {rules} rules: " + ("RECORDS RIGHT" if not bad else "RECORDS WRONG: " + "; ".join(bad)))
    if call: print("Call id, for the full transcript:", call)

if __name__ == "__main__": main()
