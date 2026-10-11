"""The engine against tool APIs shaped differently from the practice one: services under other names, roles the bank
does not have, services the engine has no role for, colliding path segments. Compiles lab/golden.py's spec against
variants of tools/openapi.json built here, and runs the in-call code in Sim where the shape matters to it.

    python3 tests/api_shapes.py
"""
import copy, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "lab")); sys.path.insert(0, str(ROOT / "tests"))
from builder import engine, extract
from local_sim import Sim, Rule
import golden

API = json.load(open(ROOT / "tools" / "openapi.json"))
PUB = {c["id"]: c for c in json.load(open(ROOT / "public-test-set.json"))}
SEVEN = engine.SEVEN

def api_with(rename=None, drop=(), add=None):
    """A copy of the practice tool API with paths renamed ("/a" -> "/b"), dropped, or added ({"/name": {field: schema}})."""
    a = copy.deepcopy(API); paths = {}
    for p, item in a["paths"].items():
        n = p.strip("/")
        if n in drop: continue
        paths["/" + (rename or {}).get(n, n)] = item
    for p, fields in (add or {}).items():
        paths[p] = {"post": {"summary": "extra", "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": dict({"customer_id": {"type": "string"}}, **fields), "required": ["customer_id"] + list(fields)}}}},
                             "responses": {"200": {"content": {"application/json": {"schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}}}}}}}}
    a["paths"] = paths; return a

def compiled(spec, api):
    return engine.lint(engine.build_workflow(spec, api))

def tool_names(wf, node): return [t["function"]["name"] for t in wf["nodes"][node]["tools"]]
def tool(wf, node, name): return next(t for t in wf["nodes"][node]["tools"] if t["function"]["name"] == name)
def url(t): return t["function"]["parameters"]["properties"]["url"]["default"]
def frames(wf): return wf["system_prompt"] + wf["nodes"]["opening"]["task_message"] + wf["nodes"]["negotiate"]["task_message"]
def every_text(wf, path=""):
    """Every string of the workflow but the code snippets (they embed the spec, in which a null role is data, not a tool)."""
    if isinstance(wf, dict): return "".join(every_text(v, path + "/" + k) for k, v in wf.items() if k not in ("pre_process_code", "post_process_code") and not (k == "code" and path.endswith("/properties")))
    if isinstance(wf, list): return "".join(every_text(v, path) for v in wf)
    return str(wf) + "\n"
def error(fn, *a):
    try: fn(*a)
    except ValueError as e: return str(e)
    raise AssertionError("expected a ValueError")
def happy(spec):
    c = PUB["PUB-01"]; s = Sim(spec, [dict(c["products"][0], product_id="p1")], c["variables"]["now"], identity=c["identity"]).login()
    s.tool("set_promise", product_id="p1", amount="full", date="2026-10-14"); s.tool("confirm"); s.tool("finish", outcome="promise"); return s
def refusal(spec):
    c = PUB["PUB-01"]; s = Sim(spec, [dict(c["products"][0], product_id="p1")], c["variables"]["now"], identity=c["identity"]).login()
    for _ in range(4):
        if s.ended: break
        s.tool("refusal", product_id="p1", kind="flat_refusal")
    return s

n = 0
def check(name, got, want):
    global n; n += 1
    if got != want: print("FAIL", name, "\n   got ", got, "\n   want", want); sys.exit(1)
    print("ok  ", name)

# ---- the default: the practice API and the golden spec, as before
base = compiled(golden.spec(True), API)
check("default compiles with the seven tools under their names", sorted(k for k in SEVEN if k in engine.read_api(API)), sorted(SEVEN))
check("default frames name the three model-called bank tools", all(x in frames(base) for x in ("schedule_callback", "transfer_to_agent", "verify_identity")), True)
check("default: nothing extra in the frames", "extra" in frames(base), False)

# ---- A. every service under another name, the four required ones included
ren = {t: t + "_x" for t in SEVEN}
api_x = api_with(rename=ren)
sp = golden.spec(True)
for t in SEVEN: sp["tools"].setdefault(t, {})["service"] = t + "_x"
check("renamed: check() accepts the aliases", extract.check(sp, api_x), [])
wf = compiled(sp, api_x)
check("renamed: opening function names are the role names", tool_names(wf, "opening"), tool_names(base, "opening"))
check("renamed: negotiate function names are the role names", tool_names(wf, "negotiate"), tool_names(base, "negotiate"))
check("renamed: model tools point at the renamed paths", [url(tool(wf, "opening", t)).rsplit("/", 1)[1] for t in ("verify_identity", "schedule_callback", "transfer_to_agent")], ["verify_identity_x", "schedule_callback_x", "transfer_to_agent_x"])
check("renamed: engine-run nodes point at the renamed paths", [url(wf["nodes"][k]["pre_actions"][0]).rsplit("/", 1)[1] for k in ("get_account", "create_promise", "add_note", "close_call")], ["get_account_x", "create_promise_x", "add_note_x", "close_call_x"])
check("renamed: the end-of-call safety net too", url(wf["tools"][0]).rsplit("/", 1)[1], "close_call_x")
check("renamed: no old url survives", "_x" in url(wf["tools"][0]) and all(url(t).endswith("_x") for node in ("opening", "negotiate") for t in wf["nodes"][node]["tools"] if t["function"]["handler"] == "__function__:api_call"), True)
check("renamed: the frames still speak of the role names", all(x in frames(wf) for x in ("schedule_callback", "transfer_to_agent", "verify_identity")) and "_x" not in frames(wf), True)
s = happy(sp)
check("renamed: Sim happy path records and closes", s.summary()[:3], ("promise", None, [("p1", 420.0, "2026-10-14")]))
bad = copy.deepcopy(sp); bad["tools"]["create_promise"]["service"] = "nothing_here"
check("renamed: an alias the API lacks is reported", any("tools.create_promise.service" in b and "nothing_here" in b for b in extract.check(bad, api_x)), True)
check("renamed: and the engine refuses it clearly", error(engine.build_workflow, bad, api_x), "the tool API file lacks: create_promise (as nothing_here)")
check("renamed: an alias does not move the field names", any("tools.create_promise.product" in b for b in extract.check(dict(sp, tools=dict(sp["tools"], create_promise=dict(sp["tools"]["create_promise"], product="nope"))), api_x)), True)

# ---- A2. the full path as the key, and colliding last segments
api_deep = api_with(rename={"create_promise": "promise/create", "add_note": "note/create"})
r = engine.read_api(api_deep)
check("paths: full path keys exist", ("promise/create" in r, "note/create" in r), (True, True))
check("paths: a shared last segment is marked, not picked", r["create"], {"ambiguous": ["promise/create", "note/create"]})
check("paths: unique last segments keep their key", r["verify_identity"] is r.get("verify_identity"), True)
sp = golden.spec(True); sp["tools"]["create_promise"]["service"] = "create"; sp["tools"]["add_note"]["service"] = "note/create"
check("paths: check() demands the full path on a collision", [b for b in extract.check(sp, api_deep) if "full path" in b], ["'create' is the last segment of several paths (promise/create, note/create): tools.create_promise.service must be the full path"])
check("paths: the engine refuses it too", "full path" in error(engine.build_workflow, sp, api_deep), True)
sp["tools"]["create_promise"]["service"] = "promise/create"
check("paths: with the full path it compiles", extract.check(sp, api_deep), [])
wf = compiled(sp, api_deep)
check("paths: the nodes call the full paths", [url(wf["nodes"][k]["pre_actions"][0]).split("/v1/")[1] for k in ("create_promise", "add_note")], ["promise/create", "note/create"])
check("paths: a role name with no alias still resolves by last segment", url(wf["nodes"][k := "get_account"]["pre_actions"][0]).endswith("/get_account"), True)

# ---- B. roles the bank does not have
api_b = api_with(drop=("schedule_callback", "transfer_to_agent"))
sp = golden.spec(True); sp["tools"]["schedule_callback"] = None; sp["tools"]["transfer_to_agent"] = None
check("null roles: check() accepts", extract.check(sp, api_b), [])
check("null roles: check_prompts flags instructions that still mention them", sorted(b for b in extract.check_prompts(sp["prompts"], sp) if "no such service" in b),
      ["negotiation mentions transfer_to_agent although the bank has no such service (tools.transfer_to_agent is null)", "opening mentions schedule_callback although the bank has no such service (tools.schedule_callback is null)",
       "opening mentions transfer_to_agent although the bank has no such service (tools.transfer_to_agent is null)"])
prm = {"global_rules": [], "opening": "CALL verify_identity. CALL no_answer. CALL wrap_up.", "negotiation": "CALL check_terms. CALL customer_refused. CALL customer_confirmed. CALL skip_product."}
check("null roles: instructions without them pass, {{callback_facts}} not demanded", extract.check_prompts(prm, sp), [])
sp["prompts"] = prm
wf = compiled(sp, api_b)
check("null roles: no such tool anywhere outside the embedded spec", ("schedule_callback" in every_text(wf), "transfer_to_agent" in every_text(wf), "verify_identity" in every_text(wf)), (False, False, True))
check("null roles: opening tools", tool_names(wf, "opening"), ["verify_identity", "no_answer", "wrap_up"])
check("null roles: negotiate tools", tool_names(wf, "negotiate"), ["check_terms", "customer_refused", "customer_confirmed", "skip_product", "wrap_up"])
check("null roles: Sim happy path", happy(sp).summary()[:3], ("promise", None, [("p1", 420.0, "2026-10-14")]))
s = refusal(sp)
check("null roles: Sim refusal path closes without a promise", (s.ledger["outcome"], s.ledger["promises"], s.ended), ("no_promise", [], True))
check("null roles: the key left out still means the service is required", error(engine.build_workflow, golden.spec(True), api_b), "the tool API file lacks: schedule_callback, transfer_to_agent")
sp = golden.spec(True); sp["tools"]["get_account"] = None
check("null on a required role is refused by check()", [b for b in extract.check(sp, API) if "tools.get_account is null" in b], ["tools.get_account is null, but the engine cannot work without this service"])
sp = golden.spec(False); sp["tools"]["add_note"] = None
wf = compiled(sp, api_with(drop=("add_note",)))
check("no add_note, notes off: compiles without a note node", "add_note" in wf["nodes"], False)
sp = golden.spec(True); sp["tools"]["add_note"] = None
check("no add_note, notes on: check() says so", "notes.enabled is true but tools.add_note is null" in extract.check(sp, API), True)

# ---- C. a service the engine has no role for
api_c = api_with(add={"/lookup_branch": {"city": {"type": "string", "description": "The city the customer names."}, "kind": {"type": "string", "enum": ["branch", "atm"]}}})
sp = golden.spec(True)
check("extra: without an entry the service is not exposed", "lookup_branch" in every_text(compiled(sp, api_c)), False)
sp["extra_tools"] = {"lookup_branch": {"step": "negotiation", "when": "When the customer asks for the nearest branch, CALL it with the city they name and read the result to them."}}
check("extra: check() accepts", extract.check(sp, api_c), [])
wf = compiled(sp, api_c)
check("extra: present in the negotiation step only", ("lookup_branch" in tool_names(wf, "negotiate"), "lookup_branch" in tool_names(wf, "opening")), (True, False))
t = tool(wf, "negotiate", "lookup_branch")
check("extra: its url, fields and result unchanged", (url(t).endswith("/lookup_branch"), sorted(t["function"]["parameters"]["properties"]["body"]["properties"]), t["function"]["parameters"]["properties"]["body"]["required"], "post_process_code" in t, "response_mapping" in t),
      (True, ["city", "customer_id", "kind"], ["city", "kind"], False, False))
check("extra: the call variable is filled by the engine", t["function"]["parameters"]["properties"]["body"]["properties"]["customer_id"]["default"], "{{customer_id}}")
check("extra: the negotiation frame lists it with its when text", "- lookup_branch(city, kind): When the customer asks for the nearest branch" in wf["nodes"]["negotiate"]["task_message"] and "lookup_branch" in wf["nodes"]["negotiate"]["task_message"].split("Your tools in this step: ")[1].split(".\n")[0], True)
check("extra: the opening frame does not", "lookup_branch" in wf["nodes"]["opening"]["task_message"], False)
sp["extra_tools"]["lookup_branch"]["step"] = "both"
wf = compiled(sp, api_c)
check("extra: both steps", ("lookup_branch" in tool_names(wf, "negotiate"), "lookup_branch" in tool_names(wf, "opening"), "- lookup_branch(city, kind)" in wf["nodes"]["opening"]["task_message"]), (True, True, True))
check("extra: a name the API lacks is rejected", [b for b in extract.check(dict(sp, extra_tools={"nowhere": {"when": "x"}}), api_c)], ["extra_tools.nowhere: the tool API has no service of that name"])
check("extra: a service a role uses is rejected", [b for b in extract.check(dict(sp, extra_tools={"create_promise": {"when": "x"}}), api_c)], ["extra_tools.create_promise: this service already plays one of the seven roles"])
check("extra: a service a role uses under an alias is rejected too", [b for b in extract.check(dict(sp, tools=dict(sp["tools"], create_promise=dict(sp["tools"]["create_promise"], service="create_promise_x")), extra_tools={"create_promise_x": {"when": "x"}}), api_with(rename={"create_promise": "create_promise_x"}))],
      ["extra_tools.create_promise_x: this service already plays one of the seven roles"])
check("extra: an empty when is rejected", extract.check(dict(sp, extra_tools={"lookup_branch": {"step": "both"}}), api_c), ["extra_tools.lookup_branch: needs a 'when' text"])
check("extra: a wrong step is rejected", extract.check(dict(sp, extra_tools={"lookup_branch": {"step": "closing", "when": "x"}}), api_c), ["extra_tools.lookup_branch.step must be opening, negotiation or both"])

# ---- a required role missing from the tool API
check("missing required role: the clear error", error(engine.build_workflow, golden.spec(True), api_with(drop=("verify_identity",))), "the tool API file lacks: verify_identity")
check("missing required role: check() says the same", "the tool API file lacks: verify_identity" in extract.check(golden.spec(True), api_with(drop=("verify_identity",))), True)

print(f"\nall {n} checks passed")
