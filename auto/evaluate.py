"""One measurement of the improvement loop. Fixed: this file is not changed while the loop runs.

    python3 auto/evaluate.py <slot> --tag "<what this experiment changes>" [--only A01,B03] [--reps 2] [--style talkative] [--concurrency 10]

Before measuring it checks that builder/ holds nothing from a brief and that the in-call code passes its local checks.
It runs the scenarios against the agent in <slot>, writes the full result to results/auto/, appends ONE LINE PER TEST
to auto/tests.jsonl, and prints which scenarios changed against the best kept run. It does not decide: see record.py.
"""
import argparse, hashlib, json, pathlib, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))

def harness():
    h = hashlib.sha1()
    for f in ("tests/scenarios.json", "tests/run_scenarios.py", "tools/score.py", "auto/evaluate.py"): h.update((ROOT / f).read_bytes())
    return h.hexdigest()[:8]

def sh(*cmd): return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("slot"); ap.add_argument("--tag", required=True); ap.add_argument("--only"); ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--style"); ap.add_argument("--concurrency", type=int, default=10); ap.add_argument("--rules", default="B")
    a = ap.parse_args()
    for check in ("auto/check_generic.py", "tests/local_sim.py"):
        r = sh(sys.executable, check)
        if r.returncode != 0: sys.exit(f"{check} failed, nothing was measured:\n{(r.stdout + r.stderr)[-1500:]}")
    agents = json.load(open(ROOT / ".freya-agents.json"))
    commit = sh("git", "rev-parse", "--short", "HEAD").stdout.strip() + ("+" if sh("git", "status", "--porcelain", "builder").stdout.strip() else "")
    stamp = time.strftime("%m%d-%H%M%S"); slug = "".join(c if c.isalnum() else "-" for c in a.tag.lower())[:40].strip("-")
    out = ROOT / "results" / "auto" / f"{stamp}-{slug}.json"; out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "tests/run_scenarios.py", agents[a.slot]["agent_id"], "--rules", a.rules, "--concurrency", str(a.concurrency), "--reps", str(a.reps), "--out", str(out)]
    if a.only: cmd += ["--only", a.only]
    if a.style: cmd += ["--style", a.style]
    t0 = time.time(); r = sh(*cmd)
    (out.with_suffix(".log")).write_text(r.stdout + "\n" + r.stderr)
    if not out.exists(): sys.exit("the run produced no result (crash). Log: " + str(out.with_suffix(".log")) + "\n" + (r.stdout + r.stderr)[-1200:])
    res = json.load(open(out))
    import freya
    hung = stalls = 0
    with open(ROOT / "auto" / "tests.jsonl", "a") as log:
        for rep, rows in enumerate(res["all_rows"]):
            for row in rows:
                ended, stalled = None, False
                if row.get("call_id"):
                    try:
                        call = freya.get_call(row["call_id"]); ended = call.get("endedReason")
                        stalled = any('"node": "stall"' in str(m.get("message")) for m in call.get("messages", []) if m.get("role") == "system")
                    except Exception: pass
                row["ended"], row["stalled"] = ended, stalled
                hung += ended == "customer-ended-call"; stalls += stalled
                log.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "experiment": out.stem, "commit": commit, "harness": harness(), "slot": a.slot, "agent_version": agents[a.slot].get("version"),
                                      "scenario": row["id"], "rep": rep + 1, "style": a.style, "pass": row["pass"], "ledger_ok": row["ledger_ok"], "ended": ended, "stalled": stalled,
                                      "failed": row["failed"], "bank_calls": row["tools"], "call_id": row.get("call_id")}) + "\n")
    n = len(res["final"]); ledger = sum(all(rows[k]["ledger_ok"] for rows in res["all_rows"]) for k in range(n))
    summary = {"experiment": out.stem, "tag": a.tag, "commit": commit, "harness": harness(), "slot": a.slot, "only": a.only, "reps": a.reps, "style": a.style, "passed": res["passed"], "total": n, "ledger": ledger,
               "hung": int(hung), "stalls": int(stalls), "seconds": round(time.time() - t0), "result": str(out.relative_to(ROOT)),
               "failed": {f["id"]: f"{f['passes']}/{f['runs']}" for f in res["final"] if f["passes"] < f["runs"]}}
    json.dump(dict(res, summary=summary), open(out, "w"), indent=1); json.dump(summary, open(ROOT / "auto" / "last.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))
    best = ROOT / "auto" / "best.json"
    if best.exists() and not a.only and not a.style:
        b = json.load(open(ROOT / json.load(open(best))["result"]))
        was = {f["id"]: f["passes"] == f["runs"] for f in b["final"]}; now = {f["id"]: f["passes"] == f["runs"] for f in res["final"]}
        fixed = sorted(i for i in now if now[i] and was.get(i) is False); broke = sorted(i for i in now if not now[i] and was.get(i) is True)
        print(f"\nagainst the best kept run ({json.load(open(best))['experiment']}, {json.load(open(best))['passed']}/{json.load(open(best))['total']}):")
        print("  newly passing:", " ".join(fixed) or "none"); print("  newly failing:", " ".join(broke) or "none")
        if fixed or broke: print("  confirm with: python3 auto/evaluate.py", a.slot, "--tag confirm --reps 2 --only", ",".join(fixed + broke))
    for f in res["final"]:
        if f["passes"] < f["runs"]:
            rows = [rows[k] for rows in res["all_rows"] for k in range(n) if rows[k]["id"] == f["id"] and not rows[k]["pass"]]
            print(f"\nFAIL {f['id']} ({f['passes']}/{f['runs']}):", ("records right, " if rows[0]["ledger_ok"] else "RECORDS WRONG, ") + " | ".join(x[:230] for x in rows[0]["failed"]))

if __name__ == "__main__": main()
