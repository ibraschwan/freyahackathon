"""Score a simulation that already ran, from Freya's records and the bank's ledgers (when the runner itself was lost).

    python3 tests/recover.py <simulation_id> --rules A|B [--out results/x.json]
"""
import argparse, json, pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
import freya
from score import http, score_ledger
from run_scenarios import expected, transcript, verdict

ap = argparse.ArgumentParser(); ap.add_argument("sim"); ap.add_argument("--rules", required=True); ap.add_argument("--out")
a = ap.parse_args()
scen = {s["id"]: s for s in json.load(open(ROOT / "tests" / "scenarios.json"))}
its = freya.api("GET", f"/api/v2/simulations/{a.sim}/iterations"); its = its.get("iterations") or its
runs = freya.get_iteration(a.sim, its[0]["id"])["runs"]
out = pathlib.Path(a.out or ROOT / "results" / f"recovered-{a.sim[:8]}.json"); tdir = out.with_suffix(""); tdir.mkdir(parents=True, exist_ok=True)
rows = []
for run in sorted(runs, key=lambda r: r.get("personaName", "")):
    sid = run["personaName"].split()[0]; s = scen.get(sid)
    if not s or not run.get("callId"): continue
    call = freya.get_call(run["callId"])
    m = re.search(r"c_[0-9a-f]{8}-[0-9a-f]{3}", json.dumps(call.get("messages", [])))
    led = http("/v1/practice/ledger/" + m.group(0)) if m else {}
    failed = score_ledger(dict(s, expected=expected(s, a.rules)), led)["failed"] if led.get("ok") else ["no ledger found"]
    ledger_ok = not failed
    ok, why, source = verdict(run)
    if not ok: failed.append(f"conversation ({source}): " + " ".join(str(why or "no verdict").split())[:700])
    rows.append({"id": sid, "family": s["family"], "pass": not failed, "ledger_ok": ledger_ok, "failed": failed, "call_id": run["callId"], "ended": call.get("endedReason"), "duration": call.get("duration"),
                 "run_outcome": run.get("outcome"), "judge_source": source, "pass_by_run_outcome": ledger_ok and run.get("outcome") == "pass"})   # the run outcome as it reads NOW, not when the run ended
    print(("PASS" if not failed else "FAIL"), sid, f"{s['family']:<14}", "|", " > ".join(c["tool"].replace("verify_identity", "verify").replace("create_promise", "promise") for c in led.get("calls", [])), "|", call.get("endedReason"))
    for f in failed: print("       -", f[:330])
    if failed: (tdir / f"{sid}.txt").write_text("\n".join("FAILED: " + f for f in failed) + "\n\n" + transcript(run["callId"]))
n = sum(r["pass"] for r in rows)
print(f"\n{n} / {len(rows)} passed, ledger right on {sum(r['ledger_ok'] for r in rows)}. Calls the customer ended: {sum(r['ended'] == 'customer-ended-call' for r in rows)}.")
json.dump({"simulation_id": a.sim, "rules": a.rules, "passed": n, "total": len(rows), "rows": rows}, open(out, "w"), indent=1)
