"""Writes tests/heldout.json: scenarios on call days the 100 scenarios do not use.

Kept out of the improvement loop (see auto/program.md). They are run for a candidate only when it is proposed as final.
Every expected date is computed by the helpers of make_scenarios.py and asserted against a value worked out by hand.

    python3 tests/make_heldout.py
"""
import json, pathlib
import make_scenarios as m

ROOT = pathlib.Path(__file__).resolve().parent.parent
start = len(m.S)
MON19, THU5, TUE24, FRI13, THU31, WED23 = "2026-10-19T09:30", "2026-11-05T16:45", "2026-11-24T12:00", "2026-11-13T19:00", "2026-12-31T10:15", "2026-12-23T11:00"
def same(a, b):
    assert a == b, (a, b)
    return a

m.sc("H01", "PUB-01", "Flat no on a Monday, accepts the first proposal", "Verified. When asked whether you can pay today say only 'No.' Give no date and no amount. Accept the first new proposal the assistant makes. Confirm at the read-back.",
     "promise", promises=[("p1", 420.0, same(m.last_bd_week(MON19), "2026-10-23"))], checks=["the agent proposes Friday 23 October"], now=MON19, family="Other days")
m.sc("H02", "PUB-04", "A date after a deadline that crosses a holiday", "Verified. You cannot pay today. Say you can pay the full amount on the 20th of November. Accept the latest possible date when it is offered. Confirm at the read-back.",
     "promise", promises=[("p1", 1250.0, same(m.deadline(THU5, 14), "2026-11-17"))], checks=["20 November is not accepted", "the agent says the latest date it can record is 17 November"], now=THU5, family="Other days")
m.sc("H03", "PUB-07", "The day after tomorrow is a holiday", "Verified. You cannot pay today. Say you will pay the full amount 'the day after tomorrow'. Accept the next business day when it is offered. Confirm at the read-back.",
     "promise", promises=[("p1", 540.0, "2026-11-27")], checks=["Thursday 26 November is not accepted", "promise recorded for Friday 27 November"], now=TUE24, family="Other days")
assert m.isbd(m.d("2026-11-27")) and not m.isbd(m.d("2026-11-26")) and m.deadline(TUE24, 5) >= "2026-11-27"
m.sc("H04", "PUB-02", "Callback asked for after the window has closed for today", "You are her husband. Say Maria is home today at half past seven in the evening. If asked for another time, say Monday at ten in the morning.",
     "not_reached", "callback", callbacks=[(same(m.bd(FRI13, 1), "2026-11-16"), "10:00")], checks=[m.NO_DEBT, "no callback is scheduled for today", "callback scheduled for Monday 16 November at 10:00"], now=FRI13, third_party=True, family="Other days")
m.sc("H05", "PUB-09", "Flat no on New Year's Eve", "Verified. When asked whether you can pay today say only 'No, I can't.' Give no date and no amount. Accept the first new proposal the assistant makes. Confirm at the read-back.",
     "promise", promises=[("p1", 2100.0, same(m.last_bd_week(THU31), "2027-01-08"))], checks=["the agent proposes Friday 8 January, the last business day of next week"], now=THU31, family="Other days")
assert m.deadline(THU31, 28) == "2027-01-12"
m.sc("H06", "PUB-06", "Too much, then the lower amount next Monday", "Verified. Say the full amount is too much for you right now. Accept the lower amount when it is offered, and say you will pay it 'next Monday'. If asked which date that is, say 'Monday of next week'. Confirm at the read-back.",
     "promise", promises=[("p1", 637.5, "2026-12-28")], checks=["the agent never asks how much she can pay", "promise recorded for 637.50 on Monday 28 December"], now=WED23, family="Other days")
assert m.isbd(m.d("2026-12-28")) and m.deadline(WED23, 12) == "2027-01-05"
m.sc("H07", "PUB-13", "One date for both, deadlines differ, on another day", "Verified. You cannot pay today. Say you want to pay both in full on the 30th of October. Accept when told the loan has an earlier latest date. Confirm once at the read-back.",
     "promise", promises=[("p1", 300.0, "2026-10-30"), ("p2", 900.0, same(m.deadline(MON19, 20), "2026-10-29"))], checks=["credit card recorded on 30 October", "loan recorded on its own deadline, 29 October", "the read-back names both dates"], now=MON19, brief="B", family="Other days")
assert m.deadline(MON19, 4) == "2026-11-05"
m.sc("H08", "PUB-12", "All three tomorrow, on another day", "Verified. You cannot pay today. Say you will pay all three in full tomorrow. Confirm once at the read-back.",
     "promise", promises=[("p1", 510.0, "2026-11-06"), ("p2", 1320.0, "2026-11-06"), ("p3", 140.0, "2026-11-06")], checks=["all three recorded for Friday 6 November", "one read-back and one confirmation for all three"], now=THU5, brief="B", family="Other days")
m.sc("H09", "PUB-08", "Callback an hour too early, then on the hour", "You are her mother. Say Hannah can be reached tomorrow at nine in the morning. If asked for another time, say tomorrow at ten in the morning.",
     "not_reached", "callback", callbacks=[(same(m.bd(TUE24, 1), "2026-11-25"), "10:00")], checks=[m.NO_DEBT, "no callback is scheduled for 09:00", "callback scheduled for 25 November at 10:00"], now=TUE24, third_party=True, family="Other days")
m.sc("H10", "PUB-05", "This Friday, said on a Monday", "Verified. You cannot pay today. Say you will pay the full amount this Friday. Confirm at the read-back.",
     "promise", promises=[("p1", 780.0, "2026-10-23")], checks=["promise recorded for Friday 23 October"], now=MON19, family="Other days")
assert m.deadline(MON19, 21) == "2026-10-29"
m.sc("H11", "PUB-03", "A day in January, said on New Year's Eve", "Verified. You cannot pay today. Say you will pay the full amount on the 5th of January. Confirm at the read-back.",
     "promise", promises=[("p1", 95.0, "2027-01-05")], checks=["promise recorded for Tuesday 5 January 2027"], now=THU31, family="Other days")
assert m.isbd(m.d("2027-01-05")) and m.deadline(THU31, 4) == "2027-01-19"
m.sc("H12", "PUB-10", "Tomorrow is Christmas Eve, and the service fails once", "Verified. You cannot pay today. Say you will pay the full amount tomorrow. Confirm at the read-back.",
     "promise", promises=[("p1", 365.0, "2026-12-24")], checks=["exactly one promise in the ledger after the retry", "promise recorded for Thursday 24 December"], now=WED23, family="Other days")
assert m.isbd(m.d("2026-12-24"))

if __name__ == "__main__":
    H = m.S[start:]
    (ROOT / "tests" / "heldout.json").write_text(json.dumps(H, indent=1))
    print(len(H), "held-out scenarios on", len({h["variables"]["now"] for h in H}), "new call days")
    for h in H:
        e = h["expected"]; print(h["id"], h["session"], h["variables"]["now"], "|", e["outcome"], e["reason"] or "-", "|", [(p["product_id"], p["amount"], p["date"]) for p in e["promises"]] or "", e["callbacks"] or "")
