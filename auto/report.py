"""Three readings of one stored result, kept apart. No simulation is run.

    python3 auto/report.py results/auto/<file>.json [--write]

- by the judge's verdict on the call (what the loop decides on)
- by the run outcome as it was read when the run ended (what the kit's run_cases.py reads)
- no verdict: the judge produced none for the call. Counted as failed in both readings, and listed.
- conflicts: run outcome and call verdict are both clear and disagree. Listed, and counted as FAILED in the first reading:
  a conflict is never settled in favour of the better result.
--write stores the first reading with conflicts failed back into the file.
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
import freya
path = pathlib.Path(sys.argv[1]); res = json.load(open(path))
none, conflict, by_call, by_run = [], [], {}, {}
for rep, rows in enumerate(res["all_rows"]):
    for row in rows:
        scr = (freya.get_call(row["call_id"]).get("successCriteriaResult") or {}) if row.get("call_id") else {}
        ledger_ok = row.get("ledger_ok", not [f for f in row["failed"] if not f.startswith("conversation")])
        call, run = scr.get("success"), row.get("run_outcome")
        if call is None: none.append((row["id"], rep + 1, run, row.get("call_id")))
        if run in ("pass", "fail") and call is not None and (run == "pass") != bool(call): conflict.append((row["id"], rep + 1, f"run {run}, call {'pass' if call else 'fail'}", row.get("call_id")))
        ok_call = bool(call) and not (run == "fail")                    # a clear fail on the run is not overruled by the call
        by_call.setdefault(row["id"], []).append(ledger_ok and ok_call)
        by_run.setdefault(row["id"], []).append(row.get("pass_by_run_outcome", ledger_ok and run == "pass"))
        row["verdict_on_call"] = call
n = len(by_call); reps = len(res["all_rows"])
full = lambda d: sum(all(v) for v in d.values())
print(f"{path.name}: {n} scenarios x {reps} run(s)")
print(f"  passed {reps} of {reps}, judge's verdict on the call: {full(by_call)} / {n}   failing: " + (" ".join(f"{k}({sum(v)}/{len(v)})" for k, v in sorted(by_call.items()) if not all(v)) or "none"))
print(f"  passed {reps} of {reps}, run outcome as read (kit's script): {full(by_run)} / {n}   failing: " + (" ".join(f"{k}({sum(v)}/{len(v)})" for k, v in sorted(by_run.items()) if not all(v)) or "none"))
print("  no verdict from the judge:", none or "none")
print("  run and call disagree:", conflict or "none")
if "--write" in sys.argv:
    res["readings"] = {"by_call_verdict": full(by_call), "by_run_outcome": full(by_run), "no_verdict": none, "conflicts": conflict}
    json.dump(res, open(path, "w"), indent=1)
