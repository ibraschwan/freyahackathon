"""Platform experiments 2: code tools with args, raising in a code tool, engine loops over api_request nodes, hooks on pre_actions."""
import sys, json, time; sys.path.insert(0, "."); sys.path.insert(0, "tools")
import freya
from score import http
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
def code_fn(code): return {"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec", "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}
def code_node(name, code, nxt, trans=None): return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt, "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [code_fn(code)], "transitions": (trans or []) + [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}]}
def code_tool(name, desc, code, props=None, required=None):
    p = {"code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}; p.update(props or {})
    return {"type": "function", "function": {"name": name, "handler": "__function__:code_exec", "description": desc, "parameters": {"type": "object", "properties": p, "required": required or []}}}
def eq(var, val): return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": val}]}
ARGS = """import json
out = dict()
try:
    out['vars_args_x'] = str(vars.get('t_args_args.x'))
    out['vars_x'] = str(vars.get('x'))
    out['keys_args'] = [str(k) for k in vars.keys() if 'args' in str(k) or str(k) in ('x', 'y', 'params')]
except Exception as e:
    out['e1'] = str(e)
for nm in ('params', 'args', 'x', 'y', 'arguments', 'kwargs'):
    try:
        out['g_' + nm] = str(eval(nm))[:80]
    except Exception as e:
        out['g_' + nm] = 'NA'
try:
    out['globals'] = sorted([str(k) for k in globals().keys() if not str(k).startswith('__')])[:40]
except Exception as e:
    out['globals'] = str(e)
vars['lab_args'] = json.dumps(out)
vars['go'] = '1'
"""
STEP_A = "vars['cur_field'] = 'phone_last4'\nvars['cur_answer'] = '0000'\nvars['loop_i'] = '0'\nvars['lab_log'] = ''\n"
STEP_C = """import json
try:
    i = int(str(vars.get('loop_i') or '0')) + 1
    snap = dict((str(k), str(vars.get(k))[:40]) for k in vars.keys() if 'verify_identity' in str(k) and 'header' not in str(k))
    snap['m_verified'] = str(vars.get('m_verified')); snap['posthook_pre_action'] = str(vars.get('posthook_pre_action')); snap['m_hooked'] = str(vars.get('m_hooked'))
    vars['lab_log'] = str(vars.get('lab_log') or '') + ' ##' + str(i) + ' ' + json.dumps(snap)
    vars['loop_i'] = str(i)
    if i < 2:
        vars['cur_answer'] = '4471'
        vars['loop_state'] = 'again'
    else:
        vars['loop_state'] = 'done'
        vars['lab_summary'] = 'iterations ' + str(i)
except Exception as e:
    vars['loop_state'] = 'done'
    vars['lab_summary'] = 'ERR ' + str(e)
"""
verify = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 0}, "function": {"name": "verify_identity", "handler": "__function__:api_call", "description": "check",
    "parameters": {"type": "object", "properties": {"url": {"type": "string", "default": BASE + "verify_identity"}, "method": {"type": "string", "default": "POST"},
    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
    "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}, "field": {"type": "string", "default": "{{cur_field}}"}, "answer": {"type": "string", "default": "{{cur_answer}}"}}, "required": []}}}},
    "post_process_code": "try:\n    vars['posthook_pre_action'] = 'ran'\n    result.pop('header', None)\n    result['data']['hooked'] = 'yes'\nexcept Exception:\n    pass\n"}
wf = {"initial_node": "talk", "system_prompt": "You are a test harness, not an assistant. When the user names a tool, CALL exactly that tool once with the arguments the user gives, then reply with the raw tool result you received, verbatim, in one line.",
  "global_nodes": {}, "test_variables": {"customer_id": "c_test"},
  "nodes": {
    "talk": {"name": "talk", "node_type": "conversation", "on_enter": {"type": "tts", "text": "ready"}, "on_enter_first_entry_only": True, "max_node_turns": 60,
      "task_message": "Tools: t_args, t_raise. NOTE FROM SYSTEM: {{lab_summary}}",
      "tools": [code_tool("t_args", "Test tool. CALL it when the user says t_args.", ARGS, {"x": {"type": "number", "description": "a number"}, "y": {"type": "string", "description": "a word"}}, ["x", "y"]),
                code_tool("t_raise", "Test tool. CALL it when the user says t_raise.", "vars['raise_ran'] = 'yes'\nraise Exception('RULE: the date is after the deadline. Offer Friday 23 October instead.')\n")],
      "transitions": [{"target_node": "step_a", "description": "go", "condition": eq("go", "1")}]},
    "step_a": code_node("step_a", STEP_A, "verify_identity"),
    "verify_identity": {"name": "verify_identity", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "step_c", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "suppress_tool_results": True,
      "pre_actions": [verify], "response_mapping": [{"path": "data.verified", "variable": "m_verified"}, {"path": "data.hooked", "variable": "m_hooked"}],
      "transitions": [{"target_node": "step_c", "description": "always", "condition": {"operator": "always"}}]},
    "step_c": code_node("step_c", STEP_C + "vars['go'] = '0'\n", "say", [{"target_node": "verify_identity", "description": "again", "condition": eq("loop_state", "again")}]),
    "say": {"name": "say", "node_type": "conversation", "passthrough": True, "passthrough_default_transition": "talk", "on_enter": {"type": "tts", "text": "Loop finished: {{lab_summary}}."},
      "task_message": "Say nothing more. Do not call a tool in this turn.", "transitions": [{"target_node": "talk", "description": "always", "condition": {"operator": "always"}}]},
  }}
print(freya.save_workflow("lab", wf)); st = json.load(open(".freya-agents.json"))["lab"]
V = http("/v1/practice/sessions", {"case": "PUB-01"})["variables"]; call = None
for msg in ["t_raise", "t_args with x=1 and y=abc", "what does the NOTE FROM SYSTEM say?"]:
    body = {"message": msg, "customerVariables": V}; body.update({"callId": call} if call else {"workflowId": st["workflow_id"]})
    t = time.time()
    try: r = freya.api("POST", "/api/v2/chat/message", body)
    except Exception as e: print("USER:", msg, "-> ERROR", str(e)[:200]); continue
    call = r["callId"]; print(f"USER: {msg}\n  AGENT ({time.time()-t:.1f}s): {r.get('response')!r}"[:900], flush=True)
c = freya.get_call(call)
print("\n=== timeline")
for m in c.get("messages", []):
    if m.get("role") in ("assistant", "user"): print(f"  [{m.get('secondsFromStart')}] {m['role']} @{m.get('nodeId')}: {str(m.get('message'))[:200]}"); continue
    try: e = json.loads(m["message"])
    except Exception: continue
    ev = e.get("event")
    if ev in ("function_call_start",): a = e.get("args") or {}; print("   >", e.get("function"), json.dumps(a.get("body", {k: v for k, v in a.items() if k != "code"}))[:200])
    elif ev in ("function_call_complete",): print("   <", e.get("function"), json.dumps(e.get("result"))[:300])
    elif ev in ("error", "function_call_error"): print("   !", ev, str(e.get("error") or e.get("message"))[:300])
    elif ev == "node_enter": print("   ~ enter", e.get("node"), "from", e.get("from_node"))
snap = [m.get("workflowSnapshot") for m in c.get("messages", []) if m.get("workflowSnapshot")]
vt = (snap[-1].get("variableTable") or {}) if snap else {}
for k in ("lab_args", "lab_log", "lab_summary", "raise_ran", "loop_state", "t_raise_failure_count", "verify_identity_success_count", "verify_identity_failure_count"):
    if k in vt: print("\n", k, "=", json.dumps(vt[k].get("value"))[:2500])
print("\n=== ledger calls:", [(x["tool"], x.get("status"), x.get("args"), x.get("result")) for x in http("/v1/practice/ledger/" + V["customer_id"])["calls"]])
