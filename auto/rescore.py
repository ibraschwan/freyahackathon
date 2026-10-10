"""Score a stored result again from the judge's verdict on each call (not from the run outcome) and from the ledger.

Used once, when it turned out that the run outcome of a simulation is not reliable (see verdict() in
tests/run_scenarios.py). No simulation is run: the calls and ledgers already exist.

    python3 auto/rescore.py results/auto/<file>.json
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
import freya
path = pathlib.Path(sys.argv[1]); res = json.load(open(path)); changed = []
for rep, rows in enumerate(res["all_rows"]):
    for row in rows:
        scr = (freya.get_call(row["call_id"]).get("successCriteriaResult") or {}) if row.get("call_id") else {}
        ledger_failed = [f for f in row["failed"] if not f.startswith("conversation")]
        ok = scr.get("success") is True
        new = ledger_failed + ([] if ok else ["conversation (call): " + " ".join(str(scr.get("reason") or "no verdict").split())[:600]])
        if (not new) != row["pass"]: changed.append((row["id"], rep + 1, "pass" if not new else "fail"))
        row.setdefault("pass_by_run_outcome", row["pass"]); row["pass"], row["failed"], row["judge_source"] = not new, new, "call"
n = len(res["final"])
for k, f in enumerate(res["final"]): f["passes"] = sum(rows[k]["pass"] for rows in res["all_rows"])
res["passed"] = sum(f["passes"] == f["runs"] for f in res["final"])
if "summary" in res:
    res["summary"].update(passed=res["passed"], failed={f["id"]: f"{f['passes']}/{f['runs']}" for f in res["final"] if f["passes"] < f["runs"]}, rescored="from the judge's verdict on each call")
json.dump(res, open(path, "w"), indent=1)
print(path.name, "->", res["passed"], "/", n, "| changed:", changed or "nothing", "| failing:", {f["id"]: f"{f['passes']}/{f['runs']}" for f in res["final"] if f["passes"] < f["runs"]})
