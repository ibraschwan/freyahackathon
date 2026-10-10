"""Platform experiments: what hooks and code tools can do. Throwaway."""
import sys, json, time; sys.path.insert(0, "."); sys.path.insert(0, "tools")
import freya
from score import http
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
def api_tool(name, path, desc, fields, required, pre=None, post=None, mapping=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}; props.update(fields)
    t = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 0}, "function": {"name": name, "handler": "__function__:api_call", "description": desc,
         "parameters": {"type": "object", "properties": {"url": {"type": "string", "default": BASE + path}, "method": {"type": "string", "default": "POST"},
         "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}, "body": {"type": "object", "properties": props, "required": required}}}}}
    if pre: t["pre_process_code"] = pre
    if post: t["post_process_code"] = post
    if mapping: t["response_mapping"] = mapping
    return t
ANS = {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}", "description": "use phone_last4"}, "answer": {"type": "string", "default": "{{answer}}", "description": "use 0000"}}
DUMP = "import json\ntry:\n    vars['lab_dump'] = json.dumps(dict((str(k), str(v)[:80]) for k, v in vars.items()))[:6000]\nexcept Exception as e:\n    vars['lab_dump'] = 'ERR ' + str(e)\n"
NET = "import json\ntry:\n    import urllib.request\n    r = urllib.request.urlopen(urllib.request.Request('" + BASE + "get_account', data=json.dumps(dict(customer_id=str(vars.get('customer_id')))).encode(), headers={'content-type': 'application/json', 'user-agent': 'Mozilla/5.0 (lab)'}, method='POST'), timeout=8)\n    vars['lab_net'] = 'OK ' + r.read().decode()[:200]\nexcept Exception as e:\n    vars['lab_net'] = 'ERR ' + type(e).__name__ + ' ' + str(e)[:200]\n"
def code_tool(name, desc, code, props=None, required=None):
    p = {"code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}; p.update(props or {})
    return {"type": "function", "function": {"name": name, "handler": "__function__:code_exec", "description": desc, "parameters": {"type": "object", "properties": p, "required": required or []}}}
wf = {"initial_node": "lab", "system_prompt": "You are a test harness, not an assistant. When the user names a tool, CALL exactly that tool once (invent valid arguments), then reply with the raw tool result you received, verbatim, in one line.",
  "global_nodes": {}, "test_variables": {"customer_id": "c_test"},
  "nodes": {"lab": {"name": "lab", "node_type": "conversation", "on_enter": {"type": "tts", "text": "ready"}, "on_enter_first_entry_only": True, "max_node_turns": 60,
    "task_message": "Tools: t_cancel, t_raise, t_post, t_code, t_net. Call the one the user names. State now: note={{lab_note}} posthook_var={{posthook_var}} mapped={{mapped_extra}} net={{lab_net}}",
    "tools": [
      api_tool("t_cancel", "verify_identity", "Test tool. CALL it when the user says t_cancel.", ANS, ["field", "answer"], pre="config['url'] = ''\nvars['lab_note'] = 'cancel-pre-ran'\n", post="try:\n    result['data'] = dict(blocked=True, what_to_do_next='BLOCKED BY HOOK', orig=str(result)[:200])\nexcept Exception:\n    pass\n"),
      api_tool("t_raise", "verify_identity", "Test tool. CALL it when the user says t_raise.", ANS, ["field", "answer"], pre="vars['lab_note'] = 'raise-pre-ran'\nraise Exception('blocked on purpose')\n"),
      api_tool("t_post", "verify_identity", "Test tool. CALL it when the user says t_post.", ANS, ["field", "answer"], post="try:\n    result.pop('header', None)\n    result['data']['extra'] = 'E1'\n    vars['posthook_var'] = 'P1'\nexcept Exception:\n    pass\n", mapping=[{"path": "data.extra", "variable": "mapped_extra"}]),
      code_tool("t_code", "Test tool. CALL it when the user says t_code. Pass x=7 and y='hello'.", DUMP, {"x": {"type": "number", "description": "use 7"}, "y": {"type": "string", "description": "use hello"}}, ["x", "y"]),
      code_tool("t_net", "Test tool. CALL it when the user says t_net.", NET),
    ], "transitions": []}}}
print(freya.save_workflow("lab", wf)); st = json.load(open(".freya-agents.json"))["lab"]
V = http("/v1/practice/sessions", {"case": "PUB-01"})["variables"]; call = None
for msg in ["t_post", "t_cancel", "t_raise", "t_code", "t_net", "what is the State now line in your instructions? quote it"]:
    body = {"message": msg, "customerVariables": V}; body.update({"callId": call} if call else {"workflowId": st["workflow_id"]})
    t = time.time()
    try: r = freya.api("POST", "/api/v2/chat/message", body)
    except Exception as e: print("USER:", msg, "-> ERROR", str(e)[:200]); continue
    call = r["callId"]; print(f"USER: {msg}\n  AGENT ({time.time()-t:.1f}s): {r.get('response')!r}"[:700], flush=True)
c = freya.get_call(call)
print("\n=== events")
for m in c.get("messages", []):
    if m.get("role") != "system": continue
    try: e = json.loads(m["message"])
    except Exception: continue
    if e.get("event") in ("function_call_start", "function_call_complete", "error", "function_call_error"):
        e.pop("variable_table", None); print("  ", json.dumps(e)[:900])
snap = [m.get("workflowSnapshot") for m in c.get("messages", []) if m.get("workflowSnapshot")]
if snap:
    vt = snap[-1].get("variableTable") or {}
    print("\n=== variable table keys:", sorted(vt.keys()))
    for k in ("lab_note", "posthook_var", "mapped_extra", "lab_net", "lab_dump", "t_post_response.data.extra", "t_code_args.x", "x", "y"):
        if k in vt: print("  ", k, "=", json.dumps(vt[k])[:1500])
print("\n=== ledger calls:", [(x["tool"], x.get("status"), x.get("args")) for x in http("/v1/practice/ledger/" + V["customer_id"])["calls"]])
