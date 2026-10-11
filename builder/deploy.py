"""Putting a workflow on Freya when the platform is busy.

Around the deadline the API answered 504 or not at all for about every second request. Every step here is repeated
until it works, and no step can create a second workflow: an update replaces the whole definition, publishing the
newest version twice changes nothing, and a create that got no answer is looked up by its name before it is tried again.
"""
import json, pathlib, time

TRANSIENT = ("-> 500", "-> 502", "-> 503", "-> 504", "timed out", "Connection", "reset by peer", "IncompleteRead", "urlopen error", "Remote end closed", "EOF occurred")

def again(what, fn, trace, tries=10):
    for n in range(tries):
        try: return fn()
        except Exception as e:
            if n == tries - 1 or not any(t in str(e) or t in type(e).__name__ for t in TRANSIENT): raise
            wait = min(60, 10 * (n + 1))
            trace.log(f"{what}: the platform did not answer ({type(e).__name__}: {str(e)[:90]}). Again in {wait} s")
            time.sleep(wait)

def save(freya, slot, workflow, state_file, trace):
    """Create the slot's workflow the first time, update the same one afterwards, publish it. Returns {workflow_id, agent_id, version}."""
    f = pathlib.Path(state_file); state = json.loads(f.read_text()) if f.exists() else {}
    if slot not in state:
        name = f"{slot} {time.strftime('%m%d-%H%M%S')}"
        def create():
            try: return freya.create_workflow(name, workflow)
            except Exception:
                found = None
                try:                                                    # no answer does not mean it was not created
                    r = freya.api("GET", "/api/v2/workflow", workspaceId=freya.workspace_id()); items = r.get("workflows") or r.get("items") or r
                    found = next((w for w in items if w.get("name") == name), None)
                except Exception: pass
                if found: return {"workflow_id": found["id"], "agent_id": found.get("agentId")}
                raise
        state[slot] = again("creating the workflow", create, trace); f.write_text(json.dumps(state, indent=1))
        trace.log(f"new workflow {state[slot]['workflow_id']} for slot '{slot}'")
    # also after a create: this sets the event's model on the agent and publishes the newest version
    state[slot]["version"] = again("updating and publishing the workflow", lambda: freya.update_workflow(state[slot]["workflow_id"], workflow), trace)
    f.write_text(json.dumps(state, indent=1))
    return state[slot]
