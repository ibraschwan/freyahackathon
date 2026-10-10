"""Which scenarios does the same agent pass sometimes and fail sometimes? Read from auto/tests.jsonl.

    python3 auto/flaky.py [--version N]      # by default the newest agent version that has tests logged
"""
import collections, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
rows = [json.loads(l) for l in open(ROOT / "auto" / "tests.jsonl")]
ver = int(sys.argv[sys.argv.index("--version") + 1]) if "--version" in sys.argv else max(r.get("agent_version") or 0 for r in rows)
rows = [r for r in rows if (r.get("agent_version") or 0) == ver and not r.get("style")]
by = collections.defaultdict(list)
for r in rows: by[r["scenario"]].append(r)
print(f"agent version {ver}: {len(rows)} tests of {len(by)} scenarios")
always = [s for s, v in by.items() if all(x["pass"] for x in v)]; never = [s for s, v in by.items() if not any(x["pass"] for x in v)]
mixed = {s: v for s, v in by.items() if s not in always and s not in never}
print(f"always passed: {len(always)} | never passed: {len(never)} {' '.join(sorted(never))} | sometimes: {len(mixed)}")
for s, v in sorted(mixed.items()):
    print(f"  {s}: {sum(x['pass'] for x in v)}/{len(v)} passed, records right {sum(x['ledger_ok'] for x in v)}/{len(v)}, stall step in {sum(bool(x.get('stalled')) for x in v)}")
