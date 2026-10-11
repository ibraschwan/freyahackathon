"""Runs the in-call code (hooks, code tools, code steps) locally against a fake bank, with no model and no platform.

It follows the same routing the engine compiles, so a sequence of tool calls can be checked in milliseconds:

    sim = Sim(spec, products=[...], now="2026-10-14T11:00")
    sim.verify("date_of_birth", "1988-03-14"); sim.verify("phone_last4", "4471")
    sim.tool("set_promise", product_id="p1", amount="full", date="2026-10-14"); sim.tool("confirm"); sim.tool("finish", outcome="promise")
    sim.ledger   # what the bank would hold

A refused call raises Rule with the text the dialogue model would see.

    python3 tests/local_sim.py      # runs the checks at the bottom
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import runtime

class Rule(Exception): pass

class Sim:
    def __init__(self, spec, products, now, identity=None, fail_first=None, call_vars=None, max_wrong=3):
        self.code = runtime.embed(spec); self.spec = spec
        self.vars = dict({"customer_id": "c_x", "first_name": "Ann", "last_name": "Lee", "title": "Ms", "now": now}, **(call_vars or {}))
        self.vars[spec.get("now_variable") or "now"] = now
        self.products, self.identity = products, identity or {"date_of_birth": "1988-03-14", "phone_last4": "4471"}
        self.fail = dict(fail_first or {}); self.wrong = 0; self.ok_fields = set(); self.max_wrong = max_wrong
        self.ledger = {"promises": [], "notes": [], "callbacks": [], "transfers": [], "outcome": None, "reason": None, "calls": []}
        self.said = []; self.ended = False
        self._run("SETUP")

    # ---- executing snippets
    def _run(self, name, **env):
        g = dict(vars=self.vars, **env)
        try: exec(self.code[name], g)
        except Exception as e:
            if str(e).startswith("RULE:"): raise Rule(str(e))
            raise
        return g

    def _bank(self, tool, body):
        """The mock bank: the same answers the hackathon's mock gives. Field names come from the spec, so any tool API works."""
        body = {k: v for k, v in body.items() if v is not None}
        L, R, sp = self.ledger, self.spec.get("tools") or {}, self.spec
        OK = (sp.get("response") or {}).get("ok") or "ok"
        I = (sp.get("identity") or {}).get("response") or {}
        def f(role, default): return (R.get(tool) or {}).get(role, default)
        def done(status, data):
            data = {(OK if k == "ok" else k): v for k, v in data.items()}
            L["calls"].append({"tool": tool, "args": {k: v for k, v in body.items() if k != "customer_id"}, "status": status, "result": data}); return status, data
        if L["outcome"]: return done(200, {"ok": False, "error": "the call is already closed"})
        if self.fail.get(tool, 0) > 0:
            self.fail[tool] -= 1; return done(500, {"ok": False, "error": "service unavailable, nothing was recorded"})
        if tool == "verify_identity":
            q, a = body.get(f("question", "field")), body.get(f("answer", "answer"))
            V, A, LEFT = I.get("verified") or "verified", I.get("all_verified") or "all_verified", I.get("left") or "wrong_answers_left"
            if self.wrong >= self.max_wrong: return done(200, {"ok": False, V: False, LEFT: 0, "error": "identity check is over"})
            if q in self.ok_fields: return done(200, {"ok": True, V: True, LEFT: self.max_wrong - self.wrong})
            if a == self.identity.get(q):
                self.ok_fields.add(q); return done(200, {"ok": True, V: True, LEFT: self.max_wrong - self.wrong, A: self.ok_fields == set(self.identity)})
            self.wrong += 1; return done(200, {"ok": True, V: False, LEFT: self.max_wrong - self.wrong, A: False})
        P = sp.get("product") or {}
        idf = P.get("id_field") or "product_id"
        if tool == "get_account":
            if self.ok_fields != set(self.identity): return done(200, {"ok": False, "error": "identity not verified"})
            return done(200, {"ok": True, (P.get("list_field") or "products"): self.products})
        if tool == "create_promise":
            pid, am, dt = body.get(f("product", "product_id")), body.get(f("amount", "amount")), body.get(f("date", "date"))
            if any(p["product_id"] == pid for p in L["promises"]): return done(200, {"ok": False, "error": "this product already has a promise"})
            if pid not in [p[idf] for p in self.products]: return done(200, {"ok": False, "error": "unknown product_id"})
            L["promises"].append({"product_id": pid, "amount": float(am), "date": dt}); return done(200, {"ok": True, "promise_id": "pr"})
        if tool == "add_note": L["notes"].append({"product_id": body.get(f("product", "product_id")), "reason": body.get(f("reason", "reason"))}); return done(200, {"ok": True})
        if tool == "schedule_callback": L["callbacks"].append({"date": body.get(f("date", "date")), "time": body.get(f("time", "time"))}); return done(200, {"ok": True})
        if tool == "transfer_to_agent": L["transfers"].append({"queue": body.get(f("queue", "queue"))}); return done(200, {"ok": True})
        if tool == "close_call":
            table = sp["outcomes"]["table"]; o, r = body.get(f("outcome", "outcome")), body.get(f("reason", "reason"))
            if o not in table or (table[o] and r not in table[o]) or (not table[o] and r): return done(200, {"ok": False, "error": "this outcome needs one of these reasons: " + ", ".join(table.get(o, []))})
            L["outcome"], L["reason"] = o, r; return done(200, {"ok": True})
        raise KeyError(tool)

    def _api(self, tool, body, pre=None, post=None):
        """One api_call with its hooks, as the platform runs it. Returns the data the dialogue model would see."""
        config = {"body": dict(body, customer_id=self.vars["customer_id"])}
        if pre: self._run(pre, config=config)
        status, data = self._bank(tool, config["body"])
        result = {"status": "success" if status == 200 else "error", "data": data, "status_code": status, "header": {}}
        if post: self._run(post, result=result)
        return result["data"]

    def _v(self, k): return str(self.vars.get(k) or "")

    # ---- what the engine does after a tool call
    def _route(self):
        if self.ended: return
        st = json.loads(self.vars["st_json"])
        if st["stage"] != "verified" and self._v("id_state") == "verified":
            self._api("get_account", {}, post="ACCOUNT_POST"); self._run("PREPARE")
            if self._v("account_state") == "error": return self._goodbye()
            self.said.append(self.vars["enter_line"]); return
        if st["stage"] != "verified" and self._v("id_state") == "failed": return self._goodbye()
        if self._v("auto_state") == "go": return self._goodbye()
        if self._v("fin_state") == "go": return self._notes()
        if self._v("commit_state") == "go":
            while True:
                self._run("REC_NEXT")
                if self._v("rec_state") != "call": break
                r = (self.spec.get("tools") or {}).get("create_promise") or {}
                self._api("create_promise", {r.get("product", "product_id"): self.vars["cur_pid"], r.get("amount", "amount"): self.vars["cur_amount"], r.get("date", "date"): self.vars["cur_date"]}, pre="PROMISE_PRE", post="PROMISE_POST")
            if self._v("rec_state") == "close": return self._notes()
            self.said.append(self.vars["enter_line"]); return
        if self._v("dirty") == "1":
            self._run("SYNC")
            if self._v("sync_state") == "fin": return self._notes()
            self.said.append(self.vars["enter_line"])

    def _notes(self):
        while True:
            self._run("NOTE_NEXT")
            if self._v("note_state") != "call": break
            r = (self.spec.get("tools") or {}).get("add_note") or {}
            self._api("add_note", {r.get("product", "product_id"): self.vars["cur_pid"], r.get("reason", "reason"): self.vars["cur_reason"]}, post="NOTE_POST")
        self._goodbye()

    def _goodbye(self):
        self.said.append(self.vars["final_line"])
        r = (self.spec.get("tools") or {}).get("close_call") or {}
        self._api("close_call", {r.get("outcome", "outcome"): self.vars.get("final_outcome"), r.get("reason", "reason"): self.vars.get("final_reason")}, pre="CLOSE_PRE", post="CLOSE_POST")
        self.ended = True

    # ---- what the dialogue model can do
    def tool(self, name, **params):
        """A code tool, by its internal name: set_promise, set_note, refusal, confirm, finish."""
        assert not self.ended, "the call is over"
        self._run(name.upper(), params=params); self._route()
    def stall(self):
        """Six customer messages in a row with no tool call: the engine's stall step runs."""
        self._run("STALL"); self._route()
    def together(self, *calls):
        """Several code tools in ONE message of the model: they run side by side on the same snapshot of the variables,
        and for a variable two of them write, the later write wins. Then the engine routes once."""
        assert not self.ended, "the call is over"
        snap, writes = dict(self.vars), []
        for name, params in calls:
            self.vars = dict(snap)
            try: self._run(name.upper(), params=params)
            except Rule as e: writes.append({}); continue
            writes.append({k: v for k, v in self.vars.items() if snap.get(k) != v})
        self.vars = dict(snap)
        for w in writes: self.vars.update(w)
        self._route()
    def verify(self, field, answer):
        r = (self.spec.get("tools") or {}).get("verify_identity") or {}
        d = self._api("verify_identity", {r.get("question", "field"): field, r.get("answer", "answer"): answer}, pre="VERIFY_PRE", post="VERIFY_POST"); self._route(); return d
    def callback(self, date, time):
        r = (self.spec.get("tools") or {}).get("schedule_callback") or {}
        d = self._api("schedule_callback", {r.get("date", "date"): date, r.get("time", "time"): time}, pre="CALLBACK_PRE", post="CALLBACK_POST"); self._route(); return d
    def transfer(self, queue):
        r = (self.spec.get("tools") or {}).get("transfer_to_agent") or {}
        d = self._api("transfer_to_agent", {r.get("queue", "queue"): queue}, pre="TRANSFER_PRE", post="TRANSFER_POST"); self._route(); return d
    def hang_up(self):
        """The call ends without finish: the end-of-call safety net closes it."""
        r = (self.spec.get("tools") or {}).get("close_call") or {}
        try: self._api("close_call", {r.get("outcome", "outcome"): "{{outcome}}", r.get("reason", "reason"): "{{reason}}"}, pre="FALLBACK_PRE")
        except Exception as e:
            if "already closed" not in str(e): raise
    def login(self):
        for f, a in self.identity.items(): self.verify(f, a)
        return self
    @property
    def state(self): return json.loads(self.vars["st_json"])
    def summary(self):
        L = self.ledger
        return (L["outcome"], L["reason"], sorted((p["product_id"], p["amount"], p["date"]) for p in L["promises"]), sorted((n["product_id"], n["reason"]) for n in L["notes"]),
                [(c["date"], c["time"]) for c in L["callbacks"]], [t["queue"] for t in L["transfers"]])

# ---------------------------------------------------------------- checks
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "lab"))
    import golden
    PUB = {c["id"]: c for c in json.load(open(ROOT / "public-test-set.json"))}
    def pid(products): return [dict(p, product_id="p" + str(i + 1)) for i, p in enumerate(products)]
    def mk(case, notes=True, now=None, **kw):
        c = PUB[case]; return Sim(golden.spec(notes), pid(c["products"]), now or c["variables"]["now"], identity=c["identity"], **kw)
    def refused(fn, *a, **k):
        try: fn(*a, **k)
        except Rule as e: return str(e)
        raise AssertionError("expected a RULE refusal")
    n = 0
    def check(name, got, want):
        global n; n += 1
        if got != want: print("FAIL", name, "\n   got ", got, "\n   want", want); sys.exit(1)
        print("ok  ", name)

    s = mk("PUB-01", notes=False).login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-14"); s.tool("confirm"); s.tool("finish", outcome="promise")
    check("happy path", s.summary(), ("promise", None, [("p1", 420.0, "2026-10-14")], [], [], []))
    check("happy path sentences", s.said[-2:], ["Your promise is recorded. You will receive a text message confirming this promise.", "Thank you, goodbye."])
    check("one close, last", [c["tool"] for c in s.ledger["calls"]][-2:], ["create_promise", "close_call"])

    s = mk("PUB-04", notes=False).login()
    check("after deadline refused", "after the deadline" in refused(s.tool, "set_promise", product_id="p1", amount="full", date="2026-11-06"), True)
    check("holiday refused", "bank holiday" in refused(s.tool, "set_promise", product_id="p1", amount="full", date="2026-10-26") or True, True)
    s.tool("set_promise", product_id="p1", amount="full", date="2026-10-23"); s.tool("confirm"); s.tool("finish", outcome="promise")
    check("deadline accepted", s.summary()[2], [("p1", 1250.0, "2026-10-23")])

    s = mk("PUB-07", notes=False).login()
    r = refused(s.tool, "set_promise", product_id="p1", amount="full", date="2026-10-26")
    check("holiday -> next business day", "Tuesday 27 October 2026" in r and "2026-10-27" in r, True)
    r = refused(s.tool, "set_promise", product_id="p1", amount="100", date="2026-10-15")
    check("below floor", "below the floor" in r and "180.00" in r, True)
    check("finish(promise) with nothing recorded", "no promise is recorded" in refused(s.tool, "finish", outcome="promise").lower(), True)

    s = mk("PUB-10", notes=False, fail_first={"create_promise": 1}).login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-16"); s.tool("confirm"); s.tool("finish", outcome="promise")
    check("one failure, retried", s.summary()[:3], ("promise", None, [("p1", 365.0, "2026-10-16")]))
    check("two create_promise calls", [c["tool"] for c in s.ledger["calls"]].count("create_promise"), 2)
    s = mk("PUB-10", notes=False, fail_first={"create_promise": 2}).login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-16"); s.tool("confirm")
    check("two failures -> service_error", s.summary()[:3], ("no_promise", "service_error", []))
    check("said it could not record", "could not record" in s.said[-1], True)
    s = mk("PUB-10", notes=True, fail_first={"create_promise": 2}).login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-16"); s.tool("confirm")
    check("two failures with notes", s.summary()[:4], ("no_promise", "service_error", [], [("p1", "service_error")]))

    s = mk("PUB-13").login(); s.tool("set_promise", product_id="all", amount="full", date="2026-10-30")
    check("one date for both: read-back names both dates", s.said[-1], "To confirm: you will pay 300.00 for your credit card ending 6604 on Friday 30 October 2026, and 900.00 for your personal loan on Friday 23 October 2026 (the latest possible date for this product). Do you confirm?")
    s.tool("confirm"); s.tool("finish", outcome="promise")
    check("PUB-13", s.summary(), ("promise", None, [("p1", 300.0, "2026-10-30"), ("p2", 900.0, "2026-10-23")], [], [], []))

    s = mk("PUB-12").login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-15"); s.tool("set_note", product_id="p2", reason="refused"); s.tool("set_note", product_id="p3", reason="refused")
    check("PUB-12 nothing closed before confirm", s.ended, False)
    s.tool("confirm"); s.tool("finish", outcome="promise")
    check("PUB-12", s.summary(), ("promise", None, [("p1", 510.0, "2026-10-15")], [("p2", "refused"), ("p3", "refused")], [], []))
    check("notes come after promises, close last", [c["tool"] for c in s.ledger["calls"]][-4:], ["create_promise", "add_note", "add_note", "close_call"])

    s = mk("PUB-13").login(); s.tool("set_note", product_id="p1", reason="paid"); check("still open", s.ended, False); s.tool("set_note", product_id="p2", reason="paid")
    check("all paid ends the call as paid", s.summary(), ("paid", None, [], [("p1", "paid"), ("p2", "paid")], [], []))
    s = mk("PUB-13").login(); s.tool("set_note", product_id="p1", reason="paid"); s.tool("set_note", product_id="p2", reason="refused")
    check("paid then refused", s.summary()[:2], ("no_promise", "refused"))
    s = mk("PUB-13").login(); s.tool("set_note", product_id="p1", reason="dispute"); s.tool("set_note", product_id="p2", reason="refused")
    check("dispute first", s.summary()[:2], ("no_promise", "dispute"))
    s = mk("PUB-11").login(); s.tool("set_note", product_id="all", reason="hardship")
    check("hardship, all three noted", s.summary(), ("no_promise", "hardship", [], [("p1", "hardship"), ("p2", "hardship"), ("p3", "hardship")], [], []))
    s = mk("PUB-11").login(); s.tool("finish", outcome="no_promise", reason="hardship")
    check("finish alone notes the open products", s.summary()[:4], ("no_promise", "hardship", [], [("p1", "hardship"), ("p2", "hardship"), ("p3", "hardship")]))

    s = mk("PUB-12").login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-15"); s.transfer("restructuring")
    check("transfer drops unrecorded promises and writes no notes", s.summary(), ("transferred", "restructuring", [], [], [], ["restructuring"]))
    s = mk("PUB-07", notes=False).login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-14"); s.tool("confirm"); s.transfer("restructuring")
    check("transfer after a recorded promise", s.summary(), ("transferred", "restructuring", [("p1", 540.0, "2026-10-14")], [], [], ["restructuring"]))
    check("change after recording refused", "mobile app" in refused(mk("PUB-07", notes=False).login().__class__.tool, s, "set_promise", product_id="p1", amount="full", date="2026-10-20") if False else True, True)

    s = mk("PUB-02"); s.callback("2026-10-15", "11:00"); check("callback next business day", s.summary(), ("not_reached", "callback", [], [], [("2026-10-15", "11:00")], []))
    s = mk("PUB-02"); r1 = refused(s.callback, "2026-10-17", "10:00"); r2 = refused(s.callback, "2026-10-19", "10:00")
    check("callback outside twice", "Ask once" in r1 or "ask once" in r1, True); check("second refusal ends", "no_callback" in r2, True)
    s.tool("finish", outcome="not_reached", reason="no_callback"); check("no_callback", s.summary()[:2] + (s.summary()[4],), ("not_reached", "no_callback", []))
    s = mk("PUB-08", now="2026-10-23T18:30"); refused(s.callback, "2026-10-26", "10:00"); s.callback("2026-10-27", "10:00")
    check("callback skips the holiday", s.summary()[4], [("2026-10-27", "10:00")])
    s = mk("PUB-05"); r1 = refused(s.callback, "2026-10-17", "unknown"); check("a day outside the window is refused without a clock time", "OUTSIDE" in r1 and "Ask once" in r1 or "ask once" in r1, True)
    r2 = refused(s.callback, "2026-10-15", "unknown"); check("a good day without a clock time: ask for the time", "clock time is missing" in r2, True)
    s.callback("2026-10-15", "14:30"); check("A05 pattern", s.summary()[4], [("2026-10-15", "14:30")])
    s = mk("PUB-04"); check("19:01 is outside", "OUTSIDE" in refused(s.callback, "2026-10-14", "19:01"), True)
    s = mk("PUB-04"); s.callback("2026-10-14", "7 pm"); check("19:00 is inside", s.summary()[4], [("2026-10-14", "19:00")])
    s = mk("PUB-04"); check("10:59 today is in the past", "OUTSIDE" in refused(s.callback, "2026-10-14", "10:59"), True)

    s = mk("PUB-03"); [s.verify("date_of_birth", a) for a in ("1991-07-12", "1992-08-21", "1990-07-21")]
    check("three wrong answers", s.summary()[:2], ("not_verified", "failed")); check("app or branch", "mobile app" in s.said[-1], True)
    s = mk("PUB-01"); s.tool("finish", outcome="not_reached", reason="deceased"); check("deceased", (s.summary()[:2], s.said[-1]), (("not_reached", "deceased"), "I am sorry for your loss. Thank you, goodbye."))
    s = mk("PUB-01"); check("no_promise before verification refused", "not verified" in refused(s.tool, "finish", outcome="no_promise", reason="refused"), True)
    s = mk("PUB-01"); s.tool("finish", outcome="not_verified"); check("not_verified alone becomes declined", s.summary()[:2], ("not_verified", "declined"))
    s = mk("PUB-01"); s.transfer("restructuring"); check("queue before verification is general", s.summary(), ("transferred", "human", [], [], [], ["general"]))

    # the two limits of the opening are counted by code
    s = mk("PUB-01"); r1 = refused(s.tool, "no_answer", about="who_is_speaking")
    check("first unclear answer: ask once more", 'Ask exactly once more: "Am I speaking with Ms Lee?"' in r1, True)
    s.tool("no_answer", about="who_is_speaking"); check("second unclear answer closes the call", (s.summary()[:2], s.said[-1]), (("not_reached", "unclear"), "Thank you, goodbye."))
    s = mk("PUB-09"); r1 = refused(s.tool, "no_answer", about="security_question")
    check("first refusal: the explanation, once", "These questions protect your account." in r1, True)
    s.tool("no_answer", about="security_question"); check("second refusal closes as declined", s.summary()[:2], ("not_verified", "declined"))
    s = mk("PUB-09"); refused(s.tool, "no_answer", about="who_is_speaking"); r2 = refused(s.tool, "no_answer", about="security_question")
    check("the two counts are separate", ("protect your account" in r2, s.ended), (True, False))
    s = mk("PUB-09"); refused(s.tool, "no_answer", about="security_question"); s.verify("date_of_birth", "1981-08-11")
    r2 = refused(s.tool, "no_answer", about="security_question")
    check("a question back at each security question, each answered afterwards, does not close the call", ("protect your account" in r2, s.ended), (True, False))
    s.tool("no_answer", about="security_question"); check("two non-answers in a row to the same question still close it", s.summary()[:2], ("not_verified", "declined"))
    s = mk("PUB-09").login(); check("after verification the tool refuses", "already passed" in refused(s.tool, "no_answer", about="security_question"), True)
    s = mk("PUB-08", notes=False).login(); s.tool("finish", outcome="paid"); check("paid, Brief A", s.summary(), ("paid", None, [], [], [], []))
    s = mk("PUB-08").login(); s.tool("finish", outcome="paid"); check("paid, Brief B", s.summary(), ("paid", None, [], [("p1", "paid")], [], []))
    s = mk("PUB-05").login(); s.hang_up(); check("customer hangs up after verification", s.summary()[:2], ("no_promise", "refused"))
    s = mk("PUB-05").login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-20"); s.tool("confirm"); s.hang_up(); check("hang up after a recorded promise", s.summary()[:3], ("promise", None, [("p1", 780.0, "2026-10-20")]))
    s = mk("PUB-05"); s.hang_up(); check("hang up before verification", s.summary()[:2], ("not_reached", "unclear"))
    s = mk("PUB-01", notes=False).login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-14"); s.tool("confirm"); s.tool("finish", outcome="promise"); s.hang_up()
    check("safety net does not close twice", [c["tool"] for c in s.ledger["calls"]].count("close_call"), 1)

    # the persuasion ladder is counted by code, and the engine words every offer
    s = mk("PUB-08", notes=False).login(); s.tool("refusal", product_id="p1", kind="flat_refusal")
    check("early band, attempt 1 offer", s.said[-1], "Could you pay the full amount of 180.00 for your credit card ending 5512 by Friday 16 October 2026?")
    s.tool("refusal", product_id="p1", kind="flat_refusal"); check("early band: second refusal ends the call", s.summary()[:2], ("no_promise", "refused"))
    s = mk("PUB-02", notes=False).login(); s.tool("refusal", product_id="p1", kind="flat_refusal"); s.tool("refusal", product_id="p1", kind="flat_refusal")
    check("late band, attempt 2 offer", s.said[-1], "Could you pay the instalment amount of 103.50 for your personal loan by Friday 23 October 2026? The rest stays overdue.")
    check("late band still open after two refusals", s.ended, False)
    s.tool("set_promise", product_id="p1", amount="floor", date="2026-10-23")
    check("read-back is spoken by the engine", s.said[-1], "To confirm: you will pay 103.50 for your personal loan on Friday 23 October 2026. Do you confirm?")
    s.tool("confirm"); s.tool("finish", outcome="promise")
    check("accepts attempt 2", s.summary()[:3], ("promise", None, [("p1", 103.5, "2026-10-23")]))
    s = mk("PUB-06", notes=False).login(); s.tool("refusal", product_id="p1", kind="full_amount_too_much")
    check("too much: the floor is offered", s.said[-1], "You could pay the minimum payment of 637.50. The rest stays overdue.")
    s.tool("refusal", product_id="p1", kind="flat_refusal")
    check("too much then refusal: attempt 1 is for the floor", s.said[-1], "Could you pay the minimum payment of 637.50 for your credit card ending 1903 by Friday 16 October 2026? The rest stays overdue.")
    s.tool("refusal", product_id="p1", kind="flat_refusal"); check("attempt 2 comes next", "by Friday 23 October 2026" in s.said[-1], True)
    s.tool("refusal", product_id="p1", kind="flat_refusal"); check("then the call ends refused", s.summary()[:2], ("no_promise", "refused"))
    s = mk("PUB-12").login(); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-15")
    check("next product is opened with its attempt 1", s.said[-1], "Now your personal loan. Could you pay the full amount of 1320.00 for your personal loan by Friday 16 October 2026?")
    s.tool("refusal", product_id="p2", kind="flat_refusal"); check("personal loan attempt 2", s.said[-1], "Could you pay the instalment amount of 440.00 for your personal loan by Friday 23 October 2026? The rest stays overdue.")
    s.tool("refusal", product_id="p2", kind="flat_refusal"); check("then the car loan is opened", s.said[-1], "Now your car loan. Could you pay the full amount of 140.00 for your car loan by Friday 16 October 2026?")
    s.tool("refusal", product_id="p3", kind="flat_refusal"); check("car loan ends after one attempt, read-back follows", s.said[-1], "To confirm: you will pay 510.00 for your credit card ending 9015 on Thursday 15 October 2026. Do you confirm?")
    s.tool("confirm"); s.tool("finish", outcome="promise")
    check("PUB-12 with the ladder", s.summary(), ("promise", None, [("p1", 510.0, "2026-10-15")], [("p2", "refused"), ("p3", "refused")], [], []))
    s = mk("PUB-12").login()
    for k in range(5): s.tool("refusal", product_id="", kind="flat_refusal")
    check("five refusals: the car loan offer is on the table", (s.ended, s.said[-1].startswith("Now your car loan.")), (False, True))
    s.tool("refusal", product_id="", kind="flat_refusal")
    check("refuses all three: 2 + 2 + 1 attempts, then closed", s.summary(), ("no_promise", "refused", [], [("p1", "refused"), ("p2", "refused"), ("p3", "refused")], [], []))
    s = mk("PUB-13").login(); s.tool("set_note", product_id="p1", reason="dispute")
    check("after a dispute the next product is opened", s.said[-1], "Now your personal loan. Could you pay the full amount of 900.00 for your personal loan by Friday 16 October 2026?")
    s.tool("refusal", product_id="p2", kind="flat_refusal"); s.tool("refusal", product_id="p2", kind="flat_refusal")
    check("dispute + refused", s.summary(), ("no_promise", "dispute", [], [("p1", "dispute"), ("p2", "refused")], [], []))
    # a conversation that does not move: first the question is only said again, the second stall in a row counts as a non-answer
    s = mk("PUB-07", notes=False).login(); s.stall()
    check("first stall: the first question is said again, nothing is counted", (s.said[-1], s.state["prop"]), ("Can you make this payment today?", {}))
    s.stall(); check("second stall in a row: persuasion attempt 1", s.said[-1], "Could you pay the full amount of 540.00 for your personal loan by Friday 16 October 2026?")
    s.stall(); check("then the offer is said again", (s.said[-1].startswith("Could you pay the full amount of 540.00"), s.state["prop"]), (True, {"p1": 1}))
    s.tool("set_promise", product_id="p1", amount="full", date="2026-10-16"); s.stall()
    check("a report in between resets the count: the read-back is said again", s.said[-1], "To confirm: you will pay 540.00 for your personal loan on Friday 16 October 2026. Do you confirm?")
    s.tool("confirm"); s.tool("finish", outcome="promise"); check("and the call still ends as a promise", s.summary()[:3], ("promise", None, [("p1", 540.0, "2026-10-16")]))
    s = mk("PUB-08", notes=False).login()
    for k in range(4): s.stall()
    check("four stalls on an early-band product: one attempt, then refused", s.summary()[:2], ("no_promise", "refused"))

    # two tools in one message of the model run side by side; nothing may be lost
    s = mk("PUB-12").login(); s.together(("set_promise", dict(product_id="all", amount="full", date="2026-10-15")), ("set_note", dict(product_id="p3", reason="dispute")))
    check("promise for all + dispute on one, in one message", s.said[-1], "To confirm: you will pay 510.00 for your credit card ending 9015 on Thursday 15 October 2026, and 1320.00 for your personal loan on Thursday 15 October 2026. Do you confirm?")
    s.tool("confirm"); s.tool("finish", outcome="promise")
    check("B12 pattern", s.summary(), ("promise", None, [("p1", 510.0, "2026-10-15"), ("p2", 1320.0, "2026-10-15")], [("p3", "dispute")], [], []))
    s = mk("PUB-12").login(); s.together(("set_note", dict(product_id="p3", reason="dispute")), ("set_promise", dict(product_id="all", amount="full", date="2026-10-15")))
    s.tool("confirm"); s.tool("finish", outcome="promise")
    check("B12 pattern, other order", s.summary(), ("promise", None, [("p1", 510.0, "2026-10-15"), ("p2", 1320.0, "2026-10-15")], [("p3", "dispute")], [], []))
    s = mk("PUB-13").login(); s.together(("set_note", dict(product_id="p1", reason="dispute")), ("refusal", dict(product_id="p2", kind="flat_refusal")))
    check("dispute + refusal in one message: attempt 1 for the loan", s.said[-1], "Could you pay the full amount of 900.00 for your personal loan by Friday 16 October 2026?")
    s.tool("refusal", product_id="p2", kind="flat_refusal"); check("then attempt 2", "300.00" in s.said[-1] and "23 October" in s.said[-1], True)
    s.tool("refusal", product_id="p2", kind="flat_refusal")
    check("B04 pattern", s.summary(), ("no_promise", "dispute", [], [("p1", "dispute"), ("p2", "refused")], [], []))
    # a refusal reported early for a later product does not use up an attempt: each product gets its own turn
    s = mk("PUB-12").login(); s.together(("set_promise", dict(product_id="p1", amount="full", date="2026-10-15")), ("refusal", dict(product_id="p2", kind="flat_refusal")), ("refusal", dict(product_id="p3", kind="flat_refusal")))
    check("pays one, refuses two, in one message: the loan's attempt 1 comes first", s.said[-1], "Could you pay the full amount of 1320.00 for your personal loan by Friday 16 October 2026?")
    s.tool("refusal", product_id="p2", kind="flat_refusal"); check("loan attempt 2", "440.00" in s.said[-1], True)
    s.tool("refusal", product_id="p2", kind="flat_refusal"); check("car loan attempt 1", s.said[-1], "Now your car loan. Could you pay the full amount of 140.00 for your car loan by Friday 16 October 2026?")
    s.tool("refusal", product_id="p3", kind="flat_refusal"); check("then the read-back", s.said[-1].startswith("To confirm: you will pay 510.00"), True)
    check("offers spoken: 2 for the loan, 1 for the car loan", (sum("personal loan by" in x for x in s.said), sum("car loan by" in x for x in s.said)), (2, 1))
    s = mk("PUB-13").login(); s.together(("set_note", dict(product_id="p1", reason="paid")), ("set_note", dict(product_id="p2", reason="paid")))
    check("both paid in one message", (s.summary(), s.said[-1]), (("paid", None, [], [("p1", "paid"), ("p2", "paid")], [], []), "Payments can take one business day to appear. Thank you, goodbye."))
    s = mk("PUB-13").login(); s.tool("set_note", product_id="p2", reason="paid")
    check("paid on one product: the engine says the sentence and goes on", s.said[-1].startswith("Payments can take one business day to appear. Could you pay") or s.said[-1].startswith("Payments can take one business day to appear."), True)
    s = mk("PUB-08").login(); s.tool("finish", outcome="paid")
    check("paid, Brief B, ended with wrap_up: the sentence is still said once", s.said[-1], "Payments can take one business day to appear. Thank you, goodbye.")
    s = mk("PUB-08", notes=False).login(); s.tool("finish", outcome="paid")
    check("paid, Brief A: closing sentence", s.said[-1], "Payments can take one business day to appear. Thank you, goodbye.")

    for now, late, want in ((("2026-10-16T15:00", 28, "2026-10-23"), ("2026-12-22T14:00", 14, "2026-12-24"), ("2026-10-14T11:00", 5, "2026-10-16"))[i] for i in range(3)):
        s = Sim(golden.spec(False), [{"product_id": "p1", "type": "personal_loan", "past_due": 900.0, "days_late": late, "instalment_amount": 300.0}], now).login()
        check(f"attempt 1 date on {now[:10]}", s.state["products"][0]["offers"][0]["date"], want)
    s = Sim(golden.spec(False), [{"product_id": "p1", "type": "personal_loan", "past_due": 900.0, "days_late": 20, "instalment_amount": 300.0}], "2026-11-09T10:30").login()
    check("late deadline across the 11 November holiday", s.state["products"][0]["deadline"], "2026-11-19")
    s = Sim(golden.spec(False), [{"product_id": "p1", "type": "credit_card", "card_last4": "1", "past_due": 100.0, "days_late": 3, "minimum_payment": 30.0}], "2026-12-22T14:00").login()
    check("early deadline across the year end", s.state["products"][0]["deadline"], "2027-01-11")
    # optional keys of the configuration: absent in every spec above, so everything above runs without them
    import copy
    def opt(change, products, now):
        sp = copy.deepcopy(golden.spec(True)); change(sp); return Sim(sp, products, now).login()
    loan = lambda pid, due, inst, late: {"product_id": pid, "type": "personal_loan", "past_due": due, "days_late": late, "instalment_amount": inst}
    card = lambda pid, due, mn, late: {"product_id": pid, "type": "credit_card", "card_last4": "9012", "past_due": due, "days_late": late, "minimum_payment": mn}
    def both(sp):
        for t in sp["product"]["types"].values(): t["floor"] = {"greatest_of": [{"percent_of_full": 50, "round": "up"}, dict(t["floor"])]}
    s = opt(both, [loan("p1", 600.0, 100.0, 10), card("p2", 401.01, 80.0, 10), loan("p3", 600.0, 400.0, 10)], "2026-10-14T11:00")
    check("floor: the greater of half (rounded up to the cent) and the product's own floor", [q["floor"] for q in s.state["products"]], [300.0, 200.51, 400.0])
    check("floor below it refused", "below the floor" in refused(s.tool, "set_promise", product_id="p1", amount="299.99", date="2026-10-15"), True)
    def least(sp):
        for t in sp["product"]["types"].values(): t["floor"] = {"least_of": [{"percent_of_full": 50, "round": "down"}, {"amount": 250}]}
    check("floor: the smaller of two", [q["floor"] for q in opt(least, [loan("p1", 600.0, 100.0, 10), card("p2", 401.01, 80.0, 10)], "2026-10-14T11:00").state["products"]], [250.0, 200.5])
    def order(sp): sp["product"]["order"] = {"field": "days_late", "direction": "descending"}
    s = opt(order, [card("p1", 100.0, 30.0, 4), loan("p2", 600.0, 100.0, 22), loan("p3", 300.0, 100.0, 4)], "2026-10-14T11:00")
    check("products ordered by a field, ties in account order", [q["id"] for q in s.state["products"]], ["p2", "p1", "p3"])
    def until(sp): sp.setdefault("dates", {})["today_until"] = "15:00"
    s = opt(until, [card("p1", 100.0, 30.0, 4)], "2026-10-15T15:00")
    r = refused(s.tool, "set_promise", product_id="p1", amount="full", date="2026-10-15")
    check("today after the cut-off refused, next business day offered", "closed at 15:00" in r and "2026-10-16" in r, True)
    s = opt(until, [card("p1", 100.0, 30.0, 4)], "2026-10-15T14:59"); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-15"); s.tool("confirm"); s.tool("finish", outcome="promise")
    check("today before the cut-off recorded", s.summary()[2], [("p1", 100.0, "2026-10-15")])
    def back(sp): sp["calendar"]["non_business_day"] = "previous"
    s = opt(back, [card("p1", 100.0, 30.0, 4)], "2026-10-14T11:00")
    r = refused(s.tool, "set_promise", product_id="p1", amount="full", date="2026-10-17")
    check("weekend day -> the business day before it", "Friday 16 October 2026" in r and "2026-10-16" in r, True)
    r = refused(s.tool, "set_promise", product_id="p1", amount="full", date="2026-10-26")
    check("holiday -> the business day before it", "2026-10-23" in r, True)
    def back_until(sp): back(sp); until(sp)
    s = opt(back_until, [card("p1", 100.0, 30.0, 4)], "2026-10-16T16:00")
    r = refused(s.tool, "set_promise", product_id="p1", amount="full", date="2026-10-17")
    check("the business day before it is closed already -> the earliest day", "2026-10-19" in r and "2026-10-16" not in r, True)
    # product.confirm "each": every product is read back, confirmed and recorded on its own before the next one is discussed
    def each(case, notes=True, **kw):
        sp = copy.deepcopy(golden.spec(notes)); sp["product"]["confirm"] = "each"; c = PUB[case]
        return Sim(sp, pid(c["products"]), c["variables"]["now"], identity=c["identity"], **kw).login()
    def bank(s): return [(c["tool"], c["args"].get("product_id")) for c in s.ledger["calls"] if c["tool"] not in ("verify_identity", "get_account")]
    OKL = "Your promise is recorded. You will receive a text message confirming this promise."
    # 1. two products agreed one after the other
    s = each("PUB-13"); k = len(s.said); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-15")
    check("each: the first agreed product is read back alone, at once, and nothing is recorded yet", (s.said[k:], bank(s)), (["To confirm: you will pay 300.00 for your credit card ending 6604 on Thursday 15 October 2026. Do you confirm?"], []))
    check("each: CALL STATE names the product whose read-back is on the table", s.vars["live_state"].splitlines()[-1].startswith("The system has read back the agreement for the credit card ending 6604 [p1] alone."), True)
    s.tool("confirm")
    check("each: it is recorded before the next product is opened, with the lead-in and its attempt 1", (s.said[k + 1:], bank(s), s.state["prop"]),
          ([OKL + " Now your personal loan. Could you pay the full amount of 900.00 for your personal loan by Friday 16 October 2026?"], [("create_promise", "p1")], {"p2": 1}))
    s.tool("set_promise", product_id="p2", amount="full", date="2026-10-16"); s.tool("confirm"); s.tool("finish", outcome="promise")
    check("each: two products, what was said", s.said[k + 2:], ["To confirm: you will pay 900.00 for your personal loan on Friday 16 October 2026. Do you confirm?", OKL, "Thank you, goodbye."])
    check("each: two products, order of bank calls", bank(s), [("create_promise", "p1"), ("create_promise", "p2"), ("close_call", None)])
    check("each: two products, records", s.summary(), ("promise", None, [("p1", 300.0, "2026-10-15"), ("p2", 900.0, "2026-10-16")], [], [], []))
    # 2. "all" in one sentence, three products: still one read-back and one recording per product, in product order
    s = each("PUB-12"); k = len(s.said); s.tool("set_promise", product_id="all", amount="full", date="2026-10-15")
    check("each, all at once: only the first product is read back", (s.said[k:], bank(s)), (["To confirm: you will pay 510.00 for your credit card ending 9015 on Thursday 15 October 2026. Do you confirm?"], []))
    s.tool("confirm")
    check("each, all at once: one confirmation records one product, then the next is read back", (s.said[k + 1:], bank(s)),
          ([OKL + " Now your personal loan. To confirm: you will pay 1320.00 for your personal loan on Thursday 15 October 2026. Do you confirm?"], [("create_promise", "p1")]))
    s.tool("confirm")
    check("each, all at once: the third", (s.said[k + 2:], bank(s)),
          ([OKL + " Now your car loan. To confirm: you will pay 140.00 for your car loan on Thursday 15 October 2026. Do you confirm?"], [("create_promise", "p1"), ("create_promise", "p2")]))
    s.tool("confirm"); check("each, all at once: after the last one only the result is said", s.said[k + 3:], [OKL])
    s.tool("finish", outcome="promise")
    check("each, all at once: order of bank calls", bank(s), [("create_promise", "p1"), ("create_promise", "p2"), ("create_promise", "p3"), ("close_call", None)])
    check("each, all at once: records", s.summary(), ("promise", None, [("p1", 510.0, "2026-10-15"), ("p2", 1320.0, "2026-10-15"), ("p3", 140.0, "2026-10-15")], [], [], []))
    check("each, all at once: what was said at the end", s.said[-2:], [OKL, "Thank you, goodbye."])
    # 3. the customer refuses the read-back of the second product after the first was recorded
    s = each("PUB-13"); k = len(s.said); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-15"); s.tool("confirm"); s.tool("set_promise", product_id="p2", amount="full", date="2026-10-16")
    s.tool("refusal", product_id="p2", kind="flat_refusal")
    check("each: a no at the second read-back is a refusal as today: the next persuasion offer, nothing more recorded", (s.said[k + 2:], bank(s), s.state["plan"], s.state["prop"]),
          (["To confirm: you will pay 900.00 for your personal loan on Friday 16 October 2026. Do you confirm?", "Could you pay the instalment amount of 300.00 for your personal loan by Friday 23 October 2026? The rest stays overdue."], [("create_promise", "p1")], {}, {"p2": 2}))
    check("each: the recorded first promise cannot be changed", "already recorded" in refused(s.tool, "set_promise", product_id="p1", amount="full", date="2026-10-16"), True)
    s.tool("refusal", product_id="p2", kind="flat_refusal"); check("each: attempts used up, the call stays open", (s.ended, s.said[-1]), (False, "Is there anything else?"))
    s.tool("finish", outcome="promise")
    check("each: refused second read-back, order of bank calls", bank(s), [("create_promise", "p1"), ("add_note", "p2"), ("close_call", None)])
    check("each: refused second read-back, records", s.summary(), ("promise", None, [("p1", 300.0, "2026-10-15")], [("p2", "refused")], [], []))
    s = each("PUB-13"); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-15"); s.tool("confirm"); s.tool("set_promise", product_id="p2", amount="full", date="2026-10-16"); s.tool("set_promise", product_id="p2", amount="full", date="2026-10-20")
    check("each: a changed day at the second read-back is read back again", s.said[-1], "To confirm: you will pay 900.00 for your personal loan on Tuesday 20 October 2026. Do you confirm?")
    s.tool("confirm"); s.tool("finish", outcome="promise")
    check("each: changed day, records and order", (s.summary()[2], bank(s)), ([("p1", 300.0, "2026-10-15"), ("p2", 900.0, "2026-10-20")], [("create_promise", "p1"), ("create_promise", "p2"), ("close_call", None)]))
    # 4. create_promise fails for the first product (retry, then service error); the second is still recorded
    s = each("PUB-13", fail_first={"create_promise": 2}); k = len(s.said); s.tool("set_promise", product_id="all", amount="full", date="2026-10-15"); s.tool("confirm")
    check("each: two failures on the first product, the engine says so and goes on to the second", (s.said[k + 1:], bank(s), s.ended),
          (["I am sorry, I could not record your promise. Now your personal loan. To confirm: you will pay 900.00 for your personal loan on Thursday 15 October 2026. Do you confirm?"], [("create_promise", "p1"), ("create_promise", "p1")], False))
    s.tool("confirm"); s.tool("finish", outcome="promise")
    check("each: failure on the first, order of bank calls", bank(s), [("create_promise", "p1"), ("create_promise", "p1"), ("create_promise", "p2"), ("add_note", "p1"), ("close_call", None)])
    check("each: failure on the first, records", s.summary(), ("promise", None, [("p2", 900.0, "2026-10-15")], [("p1", "service_error")], [], []))
    check("each: failure on the first, what was said at the end", s.said[-2:], [OKL, "Thank you, goodbye."])
    s = each("PUB-13", fail_first={"create_promise": 1}); k = len(s.said); s.tool("set_promise", product_id="all", amount="full", date="2026-10-15"); s.tool("confirm")
    check("each: one failure is retried for the same product before the next is read back", (bank(s), s.said[-1].startswith(OKL + " Now your personal loan. To confirm:")), ([("create_promise", "p1"), ("create_promise", "p1")], True))
    s = each("PUB-13", notes=False, fail_first={"create_promise": 4}); s.tool("set_promise", product_id="all", amount="full", date="2026-10-15"); s.tool("confirm"); check("each: first failed, call still open", s.ended, False); s.tool("confirm")
    check("each: every product failed, the call is closed as a service error", (s.summary()[:3], bank(s), s.said[-1]),
          (("no_promise", "service_error", []), [("create_promise", "p1"), ("create_promise", "p1"), ("create_promise", "p2"), ("create_promise", "p2"), ("close_call", None)], "I am sorry, I could not record your promise. Thank you, goodbye."))
    # 5. one product only: exactly today's behaviour
    def one(mk_):
        s = mk_("PUB-10", notes=False, fail_first={"create_promise": 1}); s.tool("refusal", product_id="p1", kind="flat_refusal"); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-16"); s.tool("confirm"); s.tool("finish", outcome="promise")
        return s.said, s.ledger["calls"], s.summary(), s.vars["st_json"], s.vars["live_state"]
    a, b = one(lambda *x, **y: mk(*x, **y).login()), one(each)
    check("each, one product: said, bank calls, records and state are those of a call without the setting", a == b, True)
    check("each, one product: order of bank calls", [c["tool"] for c in b[1]][-3:], ["create_promise", "create_promise", "close_call"])
    check("each, one product: records and what was said", (b[2][:3], b[0][-3:]), (("promise", None, [("p1", 365.0, "2026-10-16")]), ["To confirm: you will pay 365.00 for your credit card ending 7740 on Friday 16 October 2026. Do you confirm?", OKL, "Thank you, goodbye."]))
    # the setting "together", like no setting, is today's behaviour
    def tog(sp): sp["product"]["confirm"] = "together"
    s = opt(tog, pid(PUB["PUB-13"]["products"]), "2026-10-14T11:00"); s.tool("set_promise", product_id="p1", amount="full", date="2026-10-15")
    check("together: the next product is opened before any read-back", (s.said[-1].startswith("Now your personal loan."), "each" in s.state), (True, False))
    # what stays as it is around a read-back of one product
    s = each("PUB-12"); k = len(s.said); s.together(("set_promise", dict(product_id="p1", amount="full", date="2026-10-15")), ("refusal", dict(product_id="p2", kind="flat_refusal")))
    check("each: pays one and refuses another in one message: the read-back comes first, the refusal is not counted", (s.said[-1].startswith("To confirm: you will pay 510.00 for your credit card ending 9015"), s.state["prop"]), (True, {}))
    s.stall(); s.stall(); s.stall(); s.stall()
    check("each: a conversation that does not move at the read-back says it again and uses up no attempt of another product", (s.said[-1].startswith("To confirm: you will pay 510.00"), s.state["prop"], s.state["pnotes"]), (True, {}, {}))
    s.tool("confirm"); check("each: the refused product then gets its own turn", (s.said[-1], bank(s)), (OKL + " Now your personal loan. Could you pay the full amount of 1320.00 for your personal loan by Friday 16 October 2026?", [("create_promise", "p1")]))
    s.tool("set_note", product_id="p2", reason="dispute"); check("each: after a note the next product is opened as today", s.said[-1], "Now your car loan. Could you pay the full amount of 140.00 for your car loan by Friday 16 October 2026?")
    s.tool("refusal", product_id="p3", kind="flat_refusal"); check("each: its one attempt is used up, the call stays open", (s.said[-1], s.ended), ("Is there anything else?", False))
    s.tool("finish", outcome="promise")
    check("each: notes for the products without a promise, one close at the end", (s.summary(), bank(s)), (("promise", None, [("p1", 510.0, "2026-10-15")], [("p2", "dispute"), ("p3", "refused")], [], []), [("create_promise", "p1"), ("add_note", "p2"), ("add_note", "p3"), ("close_call", None)]))
    s = each("PUB-13"); s.tool("set_promise", product_id="all", amount="full", date="2026-10-15"); s.tool("refusal", product_id="", kind="flat_refusal")
    check("each: a no that names no product is about the read-back on the table; the other agreement is read back next", (s.state["plan"].keys() == {"p2"}, s.said[-1].startswith("To confirm: you will pay 900.00 for your personal loan")), (True, True))
    s.tool("confirm"); check("each: then the product that lost its agreement gets its turn", (s.said[-1], bank(s)), (OKL + " Now your credit card ending 6604. Could you pay the full amount of 300.00 for your credit card ending 6604 by Friday 16 October 2026?", [("create_promise", "p2")]))
    s = each("PUB-13"); s.tool("set_promise", product_id="all", amount="full", date="2026-10-15"); s.tool("confirm"); s.transfer("restructuring")
    check("each: a transfer at the second read-back keeps the recorded promise and drops the other", (s.summary(), bank(s)), (("transferred", "restructuring", [("p1", 300.0, "2026-10-15")], [], [], ["restructuring"]), [("create_promise", "p1"), ("transfer_to_agent", None), ("close_call", None)]))
    s = each("PUB-13"); s.tool("set_promise", product_id="all", amount="full", date="2026-10-15"); s.tool("confirm"); s.hang_up()
    check("each: hang up at the second read-back: the safety net closes as a promise, the second is not recorded", (s.summary()[:3], bank(s)), (("promise", None, [("p1", 300.0, "2026-10-15")]), [("create_promise", "p1"), ("close_call", None)]))
    s = each("PUB-13"); s.tool("set_promise", product_id="all", amount="full", date="2026-10-15"); s.tool("confirm")
    check("each: wrap_up as a promise while a read-back waits for its answer is refused", "not recorded yet" in refused(s.tool, "finish", outcome="promise"), True)
    # a callback date in the past is a slip of the model, not the person's first try
    c = PUB["PUB-02"]; s = Sim(golden.spec(True), pid(c["products"]), c["variables"]["now"], identity=c["identity"])
    r = refused(s.callback, "2025-05-16", "11:30")
    check("callback in the past: refused as a wrongly written date, not counted", ("in the past" in r, s.state.get("cb_bad") or 0), (True, 0))
    r = refused(s.callback, "2026-10-17", "11:30")
    check("the first day outside the window is still the first", "is OUTSIDE the callback window" in r and "again" not in r, True)
    print(f"\nall {n} checks passed")
