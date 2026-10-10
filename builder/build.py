"""Build a phone agent from a bank's brief. One command, no manual step.

    python3 builder/build.py <brief file> [more brief files] <tool API file> [--slot NAME] [--no-deploy] [--spec FILE]

Arguments ending in .json are the tool API file, the others are brief files (a brief that builds on another: pass both,
base first). What it does:
  1. reads the brief and the tool API file into a policy spec (model calls, see extract.py)
  2. compiles the spec into a workflow (engine.py), with no model involved
  3. checks the workflow and runs its in-call code against a fake bank
  4. saves it to Freya (the same slot updates the same workflow), exports it to submission/<slot>.workflow.json
  5. asks the agent for its first line over the chat route, to see that the workflow starts

It writes a plain-text trace to traces/<slot>.log and the spec to out/<slot>.spec.json.
--spec FILE skips step 1 and compiles that spec (for development). Needs FREYA_API_KEY, and a Claude login or ANTHROPIC_API_KEY.
"""
import json, os, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from builder import engine, extract, llm

def selftest(spec, openapi, trace):
    """The compiled code against a fake bank, on an account made up from the tool API file. Raises if a basic call breaks."""
    from local_sim import Sim
    api = engine.read_api(openapi); P = spec["product"]
    types = [t for t in P.get("types", {}) if t != "*"] or ["product"]
    def product(i, t):
        p = {P["id_field"]: f"p{i + 1}", P["type_field"]: t, P["full_field"]: 300.0 * (i + 1), P["days_late_field"]: (spec["bands"][min(i, len(spec["bands"]) - 1)].get("min") or 1)}
        for k in api["get_account"]["response"].get(P["list_field"], {}).get("items", {}).get("properties", {}):
            if k not in p: p[k] = "1234" if "last" in k else 90.0 * (i + 1)
        return p
    identity = {q["field"]: {"date": "1980-02-03", "digits": "1234"}.get(q["kind"], "x") for q in spec["identity"]["questions"]}
    now = str(spec.get("test_variables", {}).get(spec["now_variable"]) or "2026-01-05T11:00")
    ran = []
    for n in ((1, 3) if spec["notes"].get("enabled") else (1,)):
        ps = [product(i, types[i % len(types)]) for i in range(n)]
        s = Sim(spec, ps, now, identity=identity).login()
        st = s.state
        assert st["stage"] == "verified" and len(st["products"]) == n, "the account did not load"
        for p in st["products"]: assert p["deadline"] and p["floor"] <= p["full"], "a product has no deadline or a floor above the full amount"
        d = min(p["deadline"] for p in st["products"])
        s.tool("set_promise", product_id="all" if n > 1 else st["products"][0]["id"], amount="full", date=d); s.tool("confirm")
        s.tool("finish", outcome=spec["outcomes"]["promise_recorded"][0])
        assert s.ledger["outcome"] == spec["outcomes"]["promise_recorded"][0] and len(s.ledger["promises"]) == n, "a simple promise call did not end as a promise"
        assert [c["tool"] for c in s.ledger["calls"]][-1] == "close_call" and [c["tool"] for c in s.ledger["calls"]].count("close_call") == 1, "the call was not closed exactly once at the end"
        s = Sim(spec, ps, now, identity=identity).login(); s.hang_up()
        assert s.ledger["outcome"], "a call that breaks off was not closed"
        ran.append(f"{n} product(s): promise on {d}, break-off closes as {s.ledger['outcome']}/{s.ledger['reason']}")
    trace.log("SELF-TEST against a fake bank passed: " + "; ".join(ran))

def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    opt = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else True) for a in argv if a.startswith("--")}
    for i, a in enumerate(argv):                                   # "--slot NAME" as well as "--slot=NAME"
        if a in ("--slot", "--spec") and i + 1 < len(argv): opt[a] = argv[i + 1]; args.remove(argv[i + 1])
    apis = [a for a in args if a.endswith(".json")]; briefs = [a for a in args if not a.endswith(".json")]
    if len(apis) != 1 or not briefs: sys.exit(__doc__)
    slot = opt.get("--slot") or pathlib.Path(briefs[-1]).stem
    trace = llm.Trace(str(ROOT / "traces" / (slot + ".log")))
    trace.log(f"builder run for slot '{slot}' | briefs: {', '.join(briefs)} | tool API: {apis[0]} | builder model: {llm.MODEL}")
    api_text = open(apis[0]).read(); openapi = json.loads(api_text)
    (ROOT / "out").mkdir(exist_ok=True)
    if opt.get("--spec"):
        spec = json.load(open(opt["--spec"])); trace.log("spec read from " + str(opt["--spec"]) + " (no model call)")
    else:
        spec = llm.run(extract.extract(trace, [(pathlib.Path(b).name, open(b).read()) for b in briefs], openapi, api_text))
        (ROOT / "out" / (slot + ".spec.json")).write_text(json.dumps(spec, indent=1))
        trace.log(f"spec written to out/{slot}.spec.json")
    wf = engine.lint(engine.build_workflow(spec, openapi))
    (ROOT / "out" / (slot + ".workflow.json")).write_text(json.dumps(wf, indent=1))
    trace.log(f"workflow compiled: {len(wf['nodes'])} steps, {len(json.dumps(wf))} bytes, checks passed")
    selftest(spec, openapi, trace)
    if opt.get("--no-deploy"): trace.end("not deployed"); return
    import freya
    freya.validate_workflow(slot, wf); trace.log("Freya dry run: valid")
    ids = freya.save_workflow(slot, wf, state_file=str(ROOT / ".freya-agents.json"))
    trace.log(f"CREATED ON FREYA: workflow {ids['workflow_id']} agent {ids['agent_id']}" + (f" (updated in place, published version {ids['version']})" if ids.get("version") else " (new workflow)"))
    (ROOT / "submission").mkdir(exist_ok=True)
    out = freya.export_workflow(ids["workflow_id"], str(ROOT / "submission" / (slot + ".workflow.json")))
    trace.log("exported to " + os.path.relpath(out, ROOT))
    try:
        r = freya.api("POST", "/api/v2/chat/message", {"workflowId": ids["workflow_id"], "message": "Hello?", "customerVariables": spec.get("test_variables") or {}})
        trace.log("TEST over the chat route, first line of the agent: " + json.dumps(r.get("response")))
        try: freya.api("POST", "/api/v2/chat/end", {"callId": r["callId"]})
        except Exception: pass
    except Exception as e:
        trace.log("TEST over the chat route did not answer: " + str(e)[:200])
    trace.end(f"workflow {ids['workflow_id']} agent {ids['agent_id']}")
    print(json.dumps(ids))

if __name__ == "__main__": main(sys.argv[1:])
