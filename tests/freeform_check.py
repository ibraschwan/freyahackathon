"""Compiles a hand-written free-form spec against a small tool API, with no model and no network, and checks the workflow.

    python3 tests/freeform_check.py
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import freeform, engine

def svc(summary, body, resp):
    return {"post": {"summary": summary, "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": body, "required": list(body)}}}},
                     "responses": {"200": {"content": {"application/json": {"schema": {"type": "object", "properties": resp}}}}}}}

OPENAPI = {"openapi": "3.0.0", "servers": [{"url": "https://bank.example.test/v1"}], "paths": {
    "/confirm_person": svc("Check who is on the line", {"member_id": {"type": "string"}, "pin": {"type": "string"}}, {"ok": {"type": "boolean"}, "matched": {"type": "boolean"}}),
    "/book_visit": svc("Book a visit", {"member_id": {"type": "string"}, "day": {"type": "string", "format": "date"}, "slot": {"type": "string", "enum": ["morning", "afternoon"]}}, {"ok": {"type": "boolean"}, "visit_id": {"type": "string"}}),
    "/finish_contact": svc("Close the contact", {"member_id": {"type": "string"}, "result": {"type": "string", "enum": ["booked", "declined", "unreached"]}, "note": {"type": "string"}}, {"ok": {"type": "boolean"}}),
}}

SPEC = {"bank_name": "Test Bank", "language": "Turkish", "address": "{{title}} {{last_name}}", "call_variables": ["member_id", "title", "last_name", "now"], "now_variable": "now",
        "test_variables": {"member_id": "m_1", "title": "Sn.", "last_name": "Test", "now": "2026-10-14T11:00"},
        "calendar": {"weekend_days": [5, 6], "holidays": ["2026-10-29"], "weekday_names": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"], "month_names": ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]},
        "opening": "Merhaba {{title}} {{last_name}}, Test Bank'tan arıyorum.", "goodbye": "Teşekkürler, iyi günler.",
        "steps": [
            {"name": "identify", "goal": "confirm who is speaking", "entry_sentence": "", "tools": ["confirm_person"], "instructions": "Ask for the PIN. CALL confirm_person(pin).",
             "next": {"to": "book", "when": {"tool": "confirm_person", "field": "matched", "equals": "true"}}},
            {"name": "book", "goal": "book the visit", "entry_sentence": "Teşekkürler, kimliğiniz doğrulandı.", "tools": ["book_visit"], "instructions": "Offer a day from the DATE TABLE. CALL book_visit(day, slot). Then CALL wrap_up(result booked).", "next": None}],
        "global_rules": ["Never promise a discount."],
        "end": {"tool": "finish_contact", "fields": {"result": "booked when a visit was booked, declined when the customer refused"}, "default": {"result": "unreached"}}}

def main():
    wf = freeform.build_workflow(SPEC, OPENAPI)
    n = wf["nodes"]
    assert list(n) == ["setup", "step1", "step2", "goodbye", "close", "end"], list(n)
    assert wf["initial_node"] == "setup" and n["setup"]["node_type"] == "code"
    # the opening is spoken by the workflow, the second step says its entry sentence
    assert n["step1"]["on_enter"] == {"type": "tts", "text": SPEC["opening"]} and n["step1"]["on_enter_first_entry_only"]
    assert n["step2"]["on_enter"]["text"] == "Teşekkürler, kimliğiniz doğrulandı."
    # tools per step: the step's services plus wrap_up, every url from the tool API's server
    names = lambda node: [t["function"]["name"] for t in node["tools"]]
    assert names(n["step1"]) == ["confirm_person", "wrap_up"] and names(n["step2"]) == ["book_visit", "wrap_up"], (names(n["step1"]), names(n["step2"]))
    cp = n["step1"]["tools"][0]["function"]["parameters"]["properties"]
    assert cp["url"]["default"] == "https://bank.example.test/v1/confirm_person"
    assert cp["body"]["properties"]["member_id"]["default"] == "{{member_id}}" and cp["body"]["properties"]["pin"]["default"] == "{{pin}}", "call variable baked, pin left to the model"
    bv = n["step2"]["tools"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert bv["slot"]["enum"] == ["morning", "afternoon"] and "YYYY-MM-DD" in bv["day"]["description"]
    # the route: step1 -> step2 on confirm_person_response.data.matched = true (either case), and wrap_up -> goodbye in both steps
    r = n["step1"]["transitions"][0]
    assert r["target_node"] == "step2" and sorted((c["variable"], c["operand"]) for c in r["condition"]["conditions"]) == [("confirm_person_response.data.matched", "True"), ("confirm_person_response.data.matched", "true")], r
    assert [t["target_node"] for t in n["step1"]["transitions"]] == ["step2", "goodbye"] and [t["target_node"] for t in n["step2"]["transitions"]] == ["goodbye"]
    assert n["step1"]["max_turn_transition"] == "goodbye"
    # wrap_up carries the end service's model-set field with its enum, and nothing else
    wu = n["step2"]["tools"][1]["function"]["parameters"]["properties"]
    assert set(wu) == {"code", "timeout_ms", "result"} and wu["result"]["enum"] == ["booked", "declined", "unreached"] and "declined when" in wu["result"]["description"]
    # goodbye -> close -> end; close sends the baked fields, the member_id from the call, the rest from wrap_up's variables; a default for a call that broke off
    assert n["goodbye"]["on_enter"]["text"] == "Teşekkürler, iyi günler." and n["goodbye"]["transitions"][-1]["target_node"] == "close"
    close = n["close"]["pre_actions"][0]
    cb = close["function"]["parameters"]["properties"]["body"]["properties"]
    assert close["function"]["parameters"]["properties"]["url"]["default"] == "https://bank.example.test/v1/finish_contact"
    assert cb["member_id"]["default"] == "{{member_id}}" and cb["result"]["default"] == "{{ff_end_result}}" and cb["note"]["default"] == "{{ff_end_note}}"
    assert "unreached" in close["pre_process_code"] and "ff_closed" in close["post_process_code"]
    assert n["close"]["transitions"][-1]["target_node"] == "end" and n["end"]["node_type"] == "end_call"
    # the safety net: one end-of-call tool on the same service, that refuses when the call is already closed
    fb = wf["tools"]
    assert len(fb) == 1 and fb[0]["config"]["alwaysRunsAt"] == ["end_of_call"] and fb[0]["function"]["name"] == "finish_contact_at_end"
    assert "if str(vars.get('ff_closed') or '') == 'yes':\n    raise Exception('already closed')" in fb[0]["pre_process_code"]
    # the date facts: computed by the setup code, shown in every step
    assert "{{date_facts}}" in n["step1"]["task_message"] and "{{date_facts}}" in n["step2"]["task_message"]
    code = n["setup"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    v = {"now": "2026-10-14T11:00"}; exec(code, {"vars": v})
    facts = v["date_facts"]
    assert facts.startswith("TODAY: Çarşamba 14 Ekim 2026 [2026-10-14], time 11:00.") and "Perşembe 29 Ekim 2026 [2026-10-29]: NOT a business day (holiday)" in facts and "Cumartesi 17 Ekim 2026 [2026-10-17]: NOT a business day (weekend)" in facts
    assert facts.count("\n- ") == 46 and v["fin_state"] == "" and v["ff_closed"] == "no"
    v = {}; exec(code, {"vars": v}); assert v["date_facts"].startswith("TODAY:"), "no now variable: the code still sets the facts"
    # wrap_up's code keeps the fields and sets the route flag
    v = {}; exec(n["step2"]["tools"][1]["function"]["parameters"]["properties"]["code"]["default"], {"vars": v, "params": {"result": "booked", "note": ""}})
    assert v == {"ff_end_result": "booked", "fin_state": "go"}, v
    # the close pre-hook: unresolved and empty fields are dropped, the default fills in
    cfg = {"body": {"member_id": "m_1", "result": "{{ff_end_result}}", "note": ""}}; exec(close["pre_process_code"], {"vars": {}, "config": cfg})
    assert cfg["body"] == {"member_id": "m_1", "result": "unreached"}, cfg
    cfg = {"body": {"member_id": "m_1", "result": "booked"}}; exec(close["pre_process_code"], {"vars": {}, "config": cfg}); assert cfg["body"] == {"member_id": "m_1", "result": "booked"}
    # the safety net's pre-hook raises once the call is closed
    try: exec(fb[0]["pre_process_code"], {"vars": {"ff_closed": "yes"}, "config": {"body": {}}}); raise AssertionError("the safety net ran on a closed call")
    except Exception as e: assert "already closed" in str(e)
    # the system prompt and the step prompt
    assert "Test Bank" in wf["system_prompt"] and "- Never promise a discount." in wf["system_prompt"] and "Turkish" in wf["system_prompt"]
    assert "CALL confirm_person(pin)" in n["step1"]["task_message"] and "wrap_up(result)" in n["step2"]["task_message"]
    assert wf["test_variables"]["member_id"] == "m_1" and set(wf["test_variables"]) == {"member_id", "title", "last_name", "now"}
    # no double braces in any code
    for node in n.values():
        for t in (node.get("tools") or []) + (node.get("pre_actions") or []):
            for c in (t.get("pre_process_code"), t.get("post_process_code"), (t["function"]["parameters"]["properties"].get("code") or {}).get("default")):
                assert not c or ("{{" not in c and "}}" not in c)
    json.dumps(wf)

    # without an end service: goodbye -> end, no safety net, wrap_up without fields
    s2 = dict(SPEC, end=None); w2 = freeform.build_workflow(s2, OPENAPI)
    assert list(w2["nodes"]) == ["setup", "step1", "step2", "goodbye", "end"] and w2["tools"] == [] and w2["nodes"]["goodbye"]["transitions"][-1]["target_node"] == "end"
    # without a calendar: the date facts still exist (today and tomorrow), no table
    s3 = dict(SPEC, calendar=None); code = freeform.build_workflow(s3, OPENAPI)["nodes"]["setup"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    v = {"now": "2026-10-14"}; exec(code, {"vars": v}); assert v["date_facts"] == "TODAY: Wednesday 14 October 2026 [2026-10-14].\nTOMORROW: Thursday 15 October 2026 [2026-10-15].", v["date_facts"]

    # check(): an unknown tool, an unknown step, a route on a field the service does not return, a missing entry sentence
    assert freeform.check(SPEC, OPENAPI) == []
    bad = json.loads(json.dumps(SPEC)); bad["steps"][1]["tools"] = ["cancel_visit"]
    assert any("no service 'cancel_visit'" in b for b in freeform.check(bad, OPENAPI)), freeform.check(bad, OPENAPI)
    bad = json.loads(json.dumps(SPEC)); bad["steps"][0]["next"]["to"] = "pay"
    assert any("next.to must name a step" in b for b in freeform.check(bad, OPENAPI)), freeform.check(bad, OPENAPI)
    bad = json.loads(json.dumps(SPEC)); bad["steps"][0]["next"]["when"]["field"] = "verified"
    assert any("returns no field 'verified'" in b for b in freeform.check(bad, OPENAPI)), freeform.check(bad, OPENAPI)
    bad = json.loads(json.dumps(SPEC)); bad["steps"][1]["entry_sentence"] = ""
    assert any("entry_sentence is empty" in b for b in freeform.check(bad, OPENAPI))
    bad = json.loads(json.dumps(SPEC)); bad["end"]["default"] = {"status": "x"}
    assert any("no body field 'status'" in b for b in freeform.check(bad, OPENAPI))
    bad = json.loads(json.dumps(SPEC)); del bad["goodbye"]
    assert freeform.check(bad, OPENAPI) == ["missing key: goodbye"]
    try: freeform.build_workflow(bad, OPENAPI); raise AssertionError("build_workflow accepted a spec that fails the check")
    except ValueError as e: assert "missing key: goodbye" in str(e)

    # fits_engine: this tool API does not fit the engine, the practice tool API does
    assert freeform.fits_engine(OPENAPI) is False
    practice = json.load(open(ROOT / "tools" / "openapi.json"))
    assert freeform.fits_engine(practice) is True
    one_less = json.loads(json.dumps(practice)); one_less["paths"] = {p: v for p, v in one_less["paths"].items() if not p.endswith("create_promise")}
    assert freeform.fits_engine(one_less) is False
    print("freeform_check: all checks passed")

if __name__ == "__main__": main()
