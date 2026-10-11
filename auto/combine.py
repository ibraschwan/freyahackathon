"""Several stored results of the SAME agent version read as runs of one set. No simulation is run.

    python3 auto/combine.py results/auto/<file>.json [more files ...]

Per scenario, over every run in every file: passes by the judge's verdict on the call (a clear fail on the run is not
overruled) and by the run outcome as it was read (the kit's script). A call without a verdict stays failed and is listed.
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
import freya
by_call, by_run, ledger, none, conflict, cut, runs = {}, {}, {}, [], [], [], 0
for f in sys.argv[1:]:
    res = json.load(open(f))
    for rows in res.get("all_rows") or [res["rows"]]:               # a file written by tests/recover.py holds one run
        runs += 1
        for row in rows:
            c = freya.get_call(row["call_id"]) if row.get("call_id") else {}
            call, run = (c.get("successCriteriaResult") or {}).get("success"), row.get("run_outcome")
            led = row.get("ledger_ok", not [x for x in row["failed"] if not x.startswith("conversation")])
            if call is None: none.append(f"{row['id']} (run {runs}, run outcome {run})")
            if run in ("pass", "fail") and call is not None and (run == "pass") != bool(call): conflict.append(f"{row['id']} (run {runs}: run {run}, call {'pass' if call else 'fail'})")
            if c.get("endedReason") == "customer-ended-call": cut.append(f"{row['id']} (run {runs})")
            by_call.setdefault(row["id"], []).append(led and bool(call) and run != "fail")
            by_run.setdefault(row["id"], []).append(row.get("pass_by_run_outcome", led and run == "pass"))
            ledger.setdefault(row["id"], []).append(bool(led))
n = len(by_call)
def line(name, d):
    bad = {k: v for k, v in sorted(d.items()) if not all(v)}
    print(f"  {name}: {n - len(bad)} / {n} in every run   not in every run: " + (" ".join(f"{k}({sum(v)}/{len(v)})" for k, v in bad.items()) or "none"))
print(f"{n} scenarios, {runs} runs, files: " + ", ".join(pathlib.Path(f).name[:28] for f in sys.argv[1:]))
line("judge's verdict on the call", by_call); line("run outcome as read (kit's script)", by_run); line("bank records right", ledger)
print("  per run, by call verdict:", [sum(v[i] for v in by_call.values() if len(v) > i) for i in range(runs)], "| by run outcome:", [sum(v[i] for v in by_run.values() if len(v) > i) for i in range(runs)])
print("  no verdict from the judge:", ", ".join(none) or "none")
print("  run and call disagree:", ", ".join(conflict) or "none")
print("  call ended by the customer:", ", ".join(cut) or "none")
