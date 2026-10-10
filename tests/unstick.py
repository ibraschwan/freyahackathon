"""Mark simulations as completed that are still "running" although every call has a verdict. They block the workspace.

    python3 tests/unstick.py
"""
import collections, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya

r = freya.api("GET", "/api/v2/simulations", workspaceId=freya.workspace_id()); sims = r.get("simulations") or r.get("items") or r
for s in sims[:8]:
    if s.get("status") != "running": continue
    its = freya.api("GET", f"/api/v2/simulations/{s['id']}/iterations"); its = its.get("iterations") or its
    runs = freya.get_iteration(s["id"], its[0]["id"])["runs"] if its else []
    count = collections.Counter(x.get("outcome") for x in runs)
    busy = [x for x in runs if x.get("outcome") in (None, "queued", "running", "analyzing", "pending")]
    print(s["id"][:8], s.get("name"), "| running |", dict(count))
    if runs and not busy:
        freya.api("PUT", f"/api/v2/simulations/{s['id']}", {"status": "completed"}); print("   every call is judged: marked completed")
