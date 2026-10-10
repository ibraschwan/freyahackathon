"""Record the decision on the last measurement in auto/results.tsv (one row per experiment, as in autoresearch).

    python3 auto/record.py keep|discard|crash|baseline|confirm|pending "<what was tried and what happened>"

keep / baseline on a full single run also makes it the run later experiments are compared with.
"""
import json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
status, text = sys.argv[1], sys.argv[2]
assert status in ("keep", "discard", "crash", "baseline", "confirm", "pending"), status
s = json.load(open(ROOT / "auto" / "last.json")) if status != "crash" or (ROOT / "auto" / "last.json").exists() else {}
tsv = ROOT / "auto" / "results.tsv"
if not tsv.exists(): tsv.write_text("time\tcommit\tharness\tpassed\ttotal\tledger\thung\tstalls\treps\tstyle\tstatus\texperiment\tdescription\n")
scope = "" if not s.get("only") else f" [only {s['only']}]"
with open(tsv, "a") as f:
    f.write("\t".join(str(x) for x in (time.strftime("%Y-%m-%d %H:%M"), s.get("commit", ""), s.get("harness", ""), s.get("passed", 0), s.get("total", 0), s.get("ledger", 0), s.get("hung", 0), s.get("stalls", 0),
                                       s.get("reps", 1), s.get("style") or "-", status, s.get("experiment", ""), text.replace("\t", " ") + scope)) + "\n")
if status in ("keep", "baseline") and not s.get("only") and not s.get("style") and s.get("reps") == 1:
    json.dump(s, open(ROOT / "auto" / "best.json", "w"), indent=1); print("this run is now the one to beat:", s["passed"], "/", s["total"])
print(open(tsv).read().splitlines()[-1])
