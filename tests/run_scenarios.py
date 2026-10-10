"""Run our own scenarios (tests/scenarios.json) against a phone agent and score them like the kit does.

    python3 tests/run_scenarios.py <agent_id> --rules A|B [--only A01,B03] [--brief A|B] [--reps 3] [--style talkative] [--out results/x.json]

--rules says which brief the agent was built from. Under B a single-product call needs notes, so the expected
notes differ. --brief filters scenarios by their own kind (A = one product, B = several).
A transcript of every failed call is written next to --out.
"""
import argparse, hashlib, json, os, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import freya
from score import http, score_ledger
from run_cases import persona_for

def expected(s, rules):
    e = dict(s["expected"])
    if rules == "B": e["notes"] = s["expected_b_notes"]
    return e

def transcript(call_id):
    """The call as text: what was said and every tool call with its result."""
    out = []
    try: call = freya.get_call(call_id)
    except Exception as e: return "could not read call: " + str(e)
    for m in call.get("messages", []):
        role, msg = m.get("role"), m.get("message")
        if role in ("assistant", "user"): out.append(f"[{m.get('secondsFromStart')}] {role.upper()} @{m.get('nodeId')}: {msg}")
        else:
            try: e = json.loads(msg)
            except Exception: continue
            ev = e.get("event")
            if ev == "function_call_start":
                a = e.get("args") or {}; a = a.get("body", {k: v for k, v in a.items() if k not in ("code", "url", "method", "headers")})
                out.append(f"    > {e.get('function')}({json.dumps(a)})")
            elif ev == "function_call_complete":
                r = e.get("result") or {}; out.append(f"    < {json.dumps(r.get('data', r))[:900]}")
            elif ev in ("error", "function_call_error"): out.append(f"    ! {ev}: {str(e.get('error') or e.get('message'))[:600]}")
            elif ev == "node_enter": out.append(f"    ~ enter {e.get('node')} from {e.get('from_node')}")
    out.append(f"ended: {call.get('endedReason')}")
    return "\n".join(out)

def simulate(agent_id, name, variables_by_persona, concurrency, max_seconds=420):
    """Start a text simulation and wait until every call has a verdict. The platform sometimes leaves a simulation
    at "running" after all calls are judged (seen with an "inconclusive" verdict), so the calls are watched, not the status."""
    while True:
        try:
            sim = freya.api("POST", "/api/v2/simulations", {
                "agentId": agent_id, "name": name, "mode": "chat", "selectedPersonaIds": list(variables_by_persona), "customerVariablesMap": variables_by_persona,
                "maxConcurrentCalls": concurrency, "runsPerPersona": 1, "maxCallDurationSeconds": max_seconds,
                "assistantLlmOverride": freya.AGENT_LLM, "routingLlmOverride": freya.AGENT_LLM, "extractionLlmOverride": freya.AGENT_LLM,
                "personaLlmOverride": freya.SIM_LLM, "analysisLlmOverride": freya.SIM_LLM})
            break
        except RuntimeError as e:
            if "concurrent simulations" not in str(e): raise
            print("another simulation is running in this workspace, waiting 30 s", flush=True); time.sleep(30)
    sim_id = (sim.get("simulation") or sim)["id"]; it_id, settled = None, 0
    while True:
        time.sleep(10)
        st = freya.api("GET", f"/api/v2/simulations/{sim_id}"); st = (st.get("simulation") or st).get("status")
        if not it_id:
            its = freya.api("GET", f"/api/v2/simulations/{sim_id}/iterations"); its = its.get("iterations") or its.get("items") or its
            if its: it_id = its[0]["id"]
        runs = freya.get_iteration(sim_id, it_id)["runs"] if it_id else []
        open_runs = [r for r in runs if r.get("outcome") in (None, "queued", "running", "analyzing", "pending")]
        if st in ("completed", "failed", "paused"): return sim_id, it_id, runs
        settled = settled + 1 if runs and len(runs) >= len(variables_by_persona) and not open_runs else 0
        if settled >= 3:                                                  # every call judged for 30 s: done, whatever the status says
            try: freya.api("PUT", f"/api/v2/simulations/{sim_id}", {"status": "completed"})     # or the workspace stays blocked for the next run
            except Exception: pass
            return sim_id, it_id, runs

def run_once(agent_id, scen, ids, rules, concurrency):
    sessions = {s["id"]: dict(http("/v1/practice/sessions", {"case": s["session"]})["variables"], now=s["variables"]["now"]) for s in scen}
    t0 = time.time()
    sim_id, it_id, runs = simulate(agent_id, f"scen {time.strftime('%H:%M:%S')}", {ids[s["id"]]: sessions[s["id"]] for s in scen}, concurrency)
    took = time.time() - t0
    judge = {r["personaId"]: r for r in runs}
    rows = []
    for s in scen:
        led = http("/v1/practice/ledger/" + sessions[s["id"]]["customer_id"])
        r = score_ledger(dict(s, expected=expected(s, rules)), led)
        j = judge.get(ids[s["id"]], {})
        if j.get("outcome") != "pass": r["failed"].append("conversation: " + " ".join(str(j.get("reason") or "no verdict").split())[:600])
        rows.append({"id": s["id"], "family": s["family"], "pass": not r["failed"], "failed": r["failed"], "call_id": j.get("callId"),
                     "tools": [x["tool"] for x in led["calls"]], "customer_id": sessions[s["id"]]["customer_id"], "ledger_ok": not [f for f in r["failed"] if not f.startswith("conversation")]})
        print(("PASS" if not r["failed"] else "FAIL"), s["id"], f"{s['family']:<14}", "|", " > ".join(x["tool"].replace("verify_identity", "verify").replace("create_promise", "promise") for x in led["calls"]) or "(no tool calls)", flush=True)
        for f in r["failed"]: print("       -", f[:300])
    return rows, sim_id, took

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("agent_id"); ap.add_argument("--rules", required=True, choices=["A", "B"]); ap.add_argument("--brief", choices=["A", "B"])
    ap.add_argument("--only"); ap.add_argument("--reps", type=int, default=1); ap.add_argument("--style"); ap.add_argument("--out"); ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--scenarios", default=str(ROOT / "tests" / "scenarios.json"))
    a = ap.parse_args()
    scen = [s for s in json.load(open(a.scenarios)) if (not a.brief or s["brief"] == a.brief) and (not a.only or s["id"] in a.only.split(","))]
    store = ROOT / ".personas.json"; known = json.load(open(store)) if store.exists() else {}
    spec = {s["id"]: persona_for(dict(s, expected=expected(s, a.rules)), s, a.style) for s in scen}
    key = {i: "scen:" + i + ":" + hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:10] for i, p in spec.items()}
    new = [s for s in scen if key[s["id"]] not in known]
    for k in range(0, len(new), 20):
        made = freya.create_personas([spec[s["id"]] for s in new[k:k + 20]])["personas"]
        known.update({key[s["id"]]: p["id"] for s, p in zip(new[k:k + 20], made)}); json.dump(known, open(store, "w"), indent=1)
    ids = {s["id"]: known[key[s["id"]]] for s in scen}
    out = pathlib.Path(a.out or ROOT / "results" / f"scen-{time.strftime('%H%M%S')}.json"); out.parent.mkdir(parents=True, exist_ok=True)
    reps, total = [], 0
    for rep in range(a.reps):
        rows, sim_id, took = run_once(a.agent_id, scen, ids, a.rules, a.concurrency); reps.append(rows); total += took
        print(f"-- run {rep + 1} of {a.reps}: {sum(r['pass'] for r in rows)} / {len(rows)} passed, ledger right on {sum(r['ledger_ok'] for r in rows)}, {took:.0f} s\n", flush=True)
        tdir = out.with_suffix(""); tdir.mkdir(exist_ok=True)
        for r in rows:
            if not r["pass"] and r["call_id"]:
                (tdir / f"{r['id']}-run{rep + 1}.txt").write_text("\n".join("FAILED: " + f for f in r["failed"]) + "\n\n" + transcript(r["call_id"]))
    final = [{"id": s["id"], "passes": sum(r[k]["pass"] for r in reps), "runs": a.reps} for k, s in enumerate(scen)]
    n = sum(f["passes"] == a.reps for f in final)
    print(f"{n} / {len(final)} passed in all {a.reps} run(s). Failed: {' '.join(f['id'] + ('' if a.reps == 1 else '(' + str(f['passes']) + '/' + str(f['runs']) + ')') for f in final if f['passes'] < a.reps) or 'none'}. {total:.0f} s.")
    json.dump({"agent_id": a.agent_id, "rules": a.rules, "passed": n, "total": len(final), "runs": a.reps, "seconds": round(total), "final": final, "all_rows": reps}, open(out, "w"), indent=1)
    with open(ROOT / "results" / "log.jsonl", "a") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "agent_id": a.agent_id, "suite": "scenarios", "rules": a.rules, "runs": a.reps, "passed": n, "total": len(final), "seconds": round(total), "failed": [x["id"] for x in final if x["passes"] < a.reps]}) + "\n")

if __name__ == "__main__": main()
