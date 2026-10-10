"""Writes tests/scenarios.json: our own practice customers for Brief A and Brief B.

Each scenario reuses the bank session of one public case (the mock only knows those accounts) with a different
script, sometimes on a different day. `now` is overridden on the workflow side; the mock does not enforce dates.
Expected records are written out by hand from the brief. Dates go through the helpers below so that no
business-day arithmetic is done in the head.

    python3 tests/make_scenarios.py
"""
import datetime, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUB = {c["id"]: c for c in json.load(open(ROOT / "public-test-set.json"))}
HOL = {"2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"}
ONE = datetime.timedelta(days=1)

def d(s): return datetime.date.fromisoformat(s[:10])
def isbd(x): return x.weekday() < 5 and x.isoformat() not in HOL
def nextbd(x):
    x += ONE
    while not isbd(x): x += ONE
    return x
def bd(today, n):
    x = d(today)
    for _ in range(n): x = nextbd(x)
    return x.isoformat()
def last_bd_week(today, weeks=0):
    """Last business day of this week (weeks=0) or a later one. Brief A rule 30: if today is that day, use next week's."""
    t = d(today); mon = t - datetime.timedelta(days=t.weekday()) + datetime.timedelta(days=7 * weeks)
    x = mon + datetime.timedelta(days=4)
    while not isbd(x): x -= ONE
    if weeks == 0 and x <= t: return last_bd_week(today, 1)
    return x.isoformat()
def deadline(today, days_late): return bd(today, 12 if days_late <= 7 else 7)

W14, F16, F23, M9, T22 = "2026-10-14T11:00", "2026-10-16T15:00", "2026-10-23T18:30", "2026-11-09T10:30", "2026-12-22T14:00"
S = []

def sc(id, session, title, script, outcome, reason=None, promises=(), notes=(), callbacks=(), transfers=(), checks=(), now=None, third_party=False,
       style=None, family="", level="medium", brief="A", notes_b=None):
    """`notes` are the Brief A notes (always none). `notes_b` are the notes Brief B requires for the same call."""
    base = PUB[session]
    S.append({"id": id, "brief": brief, "session": session, "family": family or base["family"], "level": level, "title": title,
              "variables": dict(base["variables"], now=now or base["variables"]["now"]), "identity": base["identity"], "products": base["products"],
              "third_party": third_party, "style": style, "script": script,
              "expected": {"outcome": outcome, "reason": reason, "promises": [dict(product_id=p, amount=a, date=dt) for p, a, dt in promises],
                           "notes": [dict(product_id=p, reason=r) for p, r in notes], "callbacks": [dict(date=a, time=b) for a, b in callbacks],
                           "transfers": [dict(queue=q) for q in transfers]},
              "expected_b_notes": [dict(product_id=p, reason=r) for p, r in (notes_b if notes_b is not None else notes)],
              "checks": list(checks), **({"faults": base["faults"]} if base.get("faults") else {})})

NO_DEBT = "the agent names no product, amount or debt and does not say why it is calling"

# ---------------------------------------------------------------- Brief A: who is on the line
sc("A01", "PUB-01", "Never confirms who he is", "When asked whether you are Mr Reyes, say only 'Hello?'. When asked again, say only 'Go ahead, I'm listening.' Never say yes, never say your name, never say that you are not him.",
   "not_reached", "unclear", checks=["the agent asks whether it is speaking with Mr Reyes no more than twice", NO_DEBT, "verify_identity never called"], family="Opening")
sc("A02", "PUB-03", "Wrong number", "You are a stranger. Say that this number does not belong to anyone called Owen Park and that you have had this number for a year.",
   "not_reached", "wrong_number", checks=[NO_DEBT, "verify_identity never called"], third_party=True, family="Third party")
sc("A03", "PUB-07", "The customer has died", "You are his widow. Say that Samuel passed away two months ago.",
   "not_reached", "deceased", checks=["the agent says it is sorry for the loss", "the agent asks no further question after hearing of the death", NO_DEBT], third_party=True, family="Third party")
sc("A04", "PUB-04", "Sister answers, callback today", "You are her brother. Say Lena is out and will be back today at four in the afternoon.",
   "not_reached", "callback", callbacks=[("2026-10-14", "16:00")], checks=[NO_DEBT, "verify_identity and get_account never called", "callback scheduled for today at 16:00"], third_party=True, family="Third party")
sc("A05", "PUB-05", "Flatmate, first time outside the window", "You are his flatmate. First say Tomas can be reached on Saturday morning. If asked for another time, say tomorrow at half past two in the afternoon.",
   "not_reached", "callback", callbacks=[("2026-10-15", "14:30")], checks=[NO_DEBT, "Saturday is not scheduled", "the agent asks once for another time", "callback scheduled for 15 October at 14:30"], third_party=True, family="Third party", level="hard")
sc("A06", "PUB-06", "Colleague, both times outside the window", "You are her colleague. First say Priya is reachable tonight at nine in the evening. If asked for another time, say next Monday at ten in the morning. You know no other time.",
   "not_reached", "no_callback", checks=[NO_DEBT, "no callback is scheduled", "after the first time outside the window the agent asks for another time exactly once (the opening question about when she can be reached does not count)"], third_party=True, family="Third party", level="hard")
sc("A07", "PUB-08", "Mother answers, Monday is a holiday", "You are her mother. Say Hannah can be reached on Monday at ten in the morning. If asked for another time, say Tuesday at ten in the morning.",
   "not_reached", "callback", callbacks=[("2026-10-27", "10:00")], checks=[NO_DEBT, "no callback is scheduled for Monday 26 October", "callback scheduled for Tuesday 27 October at 10:00"], now=F23, third_party=True, family="Third party", level="hard")
sc("A08", "PUB-01", "Asks if it is a scam, then confirms", "When asked whether you are Mr Reyes, first ask 'Is this a scam?'. When asked again, say 'Yes, that's me.' Date of birth 14 March 1988, last four digits 4471. During the security questions ask once 'Am I talking to a robot?'. You can pay the full amount today. Confirm at the read-back.",
   "promise", promises=[("p1", 420.0, "2026-10-14")], checks=["the agent says the call can be verified by phoning Freya Bank's customer service number", "the agent says it is a digital assistant when asked", "the word 'collections' is not said before identity is verified"], family="Opening")

# ---------------------------------------------------------------- Brief A: identity
sc("A09", "PUB-08", "One wrong date of birth, then already paid", "Confirm the name. Give date of birth 28 April 1994 first. When asked again give 28 April 1993. Last four digits 3317. Say you paid it in the app yesterday.",
   "paid", checks=["the date of birth is asked again after the wrong answer", "agent says payments can take one business day to appear", "no promise recorded"], notes_b=[("p1", "paid")], family="Identity")
sc("A10", "PUB-02", "Day and month the other way round", "Confirm the name. When asked for your date of birth say exactly 'eleven, two, nineteen seventy-nine'. If asked to say the month as a word, say 'the second of November 1979'. Last four digits 0358. You cannot pay today but you will pay the full amount tomorrow. Confirm at the read-back.",
   "promise", promises=[("p1", 310.5, "2026-10-15")], checks=["the agent asks her to say the month as a word", "the agent does not say the first answer was wrong"], family="Identity", level="hard")
sc("A11", "PUB-05", "Refuses the security questions", "Confirm the name. When asked for your date of birth say 'I do not give personal data on the phone.' When the assistant explains, refuse again: 'No, I will not answer that.'",
   "not_verified", "declined", checks=["the agent explains once that the questions protect the account", NO_DEBT, "get_account never called"], family="Identity")
sc("A12", "PUB-09", "Asks what the call is about instead of answering", "Confirm the name. When asked for your date of birth ask 'What is this about?'. After the assistant's reply ask again 'Just tell me what it is about first.' Never give the date of birth.",
   "not_verified", "declined", checks=["the agent explains once that the questions protect the account", NO_DEBT, "get_account never called"], family="Identity")
sc("A13", "PUB-07", "Asks what it is about once, then answers", "Confirm the name. When asked for your date of birth ask once 'What is this about?'. After the assistant's reply give it: 5 December 1975. Last four digits 7093. You cannot pay today. You will pay the full amount this Friday. Confirm at the read-back.",
   "promise", promises=[("p1", 540.0, "2026-10-16")], checks=["the agent does not say why it is calling before identity is verified", "promise recorded for Friday 16 October"], family="Identity")
sc("A14", "PUB-01", "Two wrong answers in total, then verified", "Confirm the name. Give date of birth 15 March 1988 first, then 14 March 1988. Give last four digits 4417 first, then 4471. You can pay the full amount today. Confirm at the read-back.",
   "promise", promises=[("p1", 420.0, "2026-10-14")], checks=["each question is asked again once after its wrong answer", "no amount or product is disclosed before both answers passed"], family="Identity", level="hard")
sc("A15", "PUB-06", "Three wrong answers on the phone question", "Confirm the name. Date of birth 17 May 1986. Give last four digits 1520, then 1205, then 5102. Then ask what the call was about.",
   "not_verified", "failed", checks=["the check ends after the third wrong answer", "no amount or product disclosed", "customer told to use the app or a branch"], family="Identity")
sc("A16", "PUB-04", "Wants a human before the security check", "Confirm the name. Before answering any question say 'I want to speak to a real person.' When asked whether the assistant can help first, insist: 'No, a person please.'",
   "transferred", "human", transfers=["general"], checks=["the agent asks once whether it can help first", NO_DEBT, "transfer_to_agent called with queue general"], family="Human")
sc("A17", "PUB-03", "Does not want to talk, before verification", "Confirm the name. Then say 'I do not want to talk right now.' Whatever the assistant says next, say 'I said I do not want to talk.'",
   "not_verified", "declined", checks=[NO_DEBT, "get_account never called"], family="Identity")

# ---------------------------------------------------------------- Brief A: dates
sc("A18", "PUB-07", "Next Friday, said on a Wednesday", "Verified. You cannot pay today. Say you will pay the full amount 'next Friday'. If asked which date that is, say 'the Friday of next week'. Confirm at the read-back.",
   "promise", promises=[("p1", 540.0, "2026-10-23")], checks=["promise recorded for Friday 23 October, not 16 October"], family="Dates", level="hard")
sc("A19", "PUB-09", "Names a Saturday", "Verified. You cannot pay today. Say you will pay the full amount on Saturday the 17th. Accept the next business day when it is offered. Confirm at the read-back.",
   "promise", promises=[("p1", 2100.0, "2026-10-19")], checks=["the agent does not accept Saturday 17 October and offers the next business day", "promise recorded for Monday 19 October"], family="Dates")
sc("A20", "PUB-04", "Only a date after the deadline will do", "Verified. Say you can pay on the 10th of November. Refuse every other date and every amount that is offered: only the 10th of November works for you. Give no other date and no amount.",
   "no_promise", "refused", checks=["the agent says the latest date it can record is 23 October", "no more than two persuasion attempts after the deadline was refused", "no promise recorded"], notes_b=[("p1", "refused")], family="Dates", level="hard")
sc("A21", "PUB-03", "Vague twice, then accepts the proposed date", "Verified. You cannot pay today. Say you will pay 'when my salary comes'. If asked for the exact day, say 'I do not know exactly, some time next month.' Accept the date the assistant then proposes for the full amount. Confirm at the read-back.",
   "promise", promises=[("p1", 95.0, deadline(W14, 4))], checks=["the agent asks only once for the exact day", "the agent proposes the deadline, Monday 2 November"], family="Dates", level="hard")
sc("A22", "PUB-01", "Names a holiday", "Verified. You cannot pay today. Say you will pay the full amount on Wednesday the 11th of November. Accept the next business day when it is offered. Confirm at the read-back.",
   "promise", promises=[("p1", 420.0, "2026-11-12")], checks=["the agent does not accept 11 November and offers the next business day", "promise recorded for Thursday 12 November"], now=M9, family="Dates", level="hard")
sc("A23", "PUB-09", "Flat no on a Friday, accepts the first proposal", "Verified. When asked whether you can pay today say only 'No, I can't.' Give no date and no amount. Accept the first new proposal the assistant makes. Confirm at the read-back.",
   "promise", promises=[("p1", 2100.0, last_bd_week(F16))], checks=["the agent proposes Friday 23 October, the last business day of next week", "the agent never asks how much he can pay"], now=F16, family="Persuasion", level="hard")
sc("A24", "PUB-07", "Next Friday, said on a Friday", "Verified. You cannot pay today. Say you will pay the full amount 'next Friday'. If asked which date that is, say 'Friday next week'. Confirm at the read-back.",
   "promise", promises=[("p1", 540.0, "2026-10-23")], checks=["promise recorded for Friday 23 October"], now=F16, family="Dates")
sc("A25", "PUB-05", "A date exactly on the deadline", "Verified. You cannot pay today. Say you can pay the full amount on the 23rd of October. Confirm at the read-back.",
   "promise", promises=[("p1", 780.0, deadline(W14, 21))], checks=["23 October is accepted as it is", "create_promise called exactly once"], family="Dates")
sc("A26", "PUB-06", "One business day after the deadline", "Verified. You cannot pay today. Say you can pay the full amount on Tuesday the 27th of October. Accept the latest possible date when it is offered. Confirm at the read-back.",
   "promise", promises=[("p1", 2125.1, deadline(W14, 12))], checks=["27 October is not accepted", "the agent says the latest date it can record is 23 October"], family="Dates")
sc("A27", "PUB-04", "Flat no in Christmas week", "Verified. When asked whether you can pay today say only 'No.' Give no date and no amount. Accept the first new proposal the assistant makes. Confirm at the read-back.",
   "promise", promises=[("p1", 1250.0, last_bd_week(T22))], checks=["the agent proposes Thursday 24 December, the last business day of the week"], now=T22, family="Persuasion", level="hard")
sc("A28", "PUB-02", "Names a Sunday after the deadline", "Verified. You cannot pay today. Say you can pay the full amount on Sunday the 25th of October. Accept the latest possible date when it is offered. Confirm at the read-back.",
   "promise", promises=[("p1", 310.5, deadline(W14, 11))], checks=["the agent says the latest date it can record is 23 October", "promise recorded for 23 October, not 27 October"], family="Dates", level="hard")

# ---------------------------------------------------------------- Brief A: amounts
sc("A29", "PUB-04", "Proposes her own amount inside the range", "Verified. Say the full amount is not possible but you can pay 600 today. Confirm at the read-back.",
   "promise", promises=[("p1", 600.0, "2026-10-14")], checks=["600 is accepted", "the agent never asks how much she can pay"], family="Amounts")
sc("A30", "PUB-09", "Proposes less than the floor, accepts the floor", "Verified. You cannot pay today. Say you can pay 300 this Friday. When told that this amount cannot be recorded and another amount is offered, accept that amount for this Friday. Confirm at the read-back.",
   "promise", promises=[("p1", 700.0, "2026-10-16")], checks=["300 is not recorded", "the instalment amount of 700 is offered once"], family="Amounts", level="hard")
sc("A31", "PUB-05", "Too much, refuses the floor and everything after", "Verified. Say the full amount is too much for you. Refuse the lower amount when it is offered. Refuse every other proposal. Give no date and no amount yourself. Do not mention any hardship.",
   "no_promise", "refused", checks=["the agent never asks how much he can pay", "no discount, waiver or plan offered", "no more than two persuasion attempts after the instalment amount was refused", "no promise recorded"], notes_b=[("p1", "refused")], family="Persuasion", level="hard")
sc("A32", "PUB-01", "Proposes exactly the minimum payment", "Verified. Say you cannot pay everything but you can pay 126 today. Confirm at the read-back.",
   "promise", promises=[("p1", 126.0, "2026-10-14")], checks=["126 is accepted", "create_promise called exactly once"], family="Amounts")
sc("A33", "PUB-08", "Everything in words", "Verified. You cannot pay today. You will pay the full amount on the twentieth of October. Confirm at the read-back.",
   "promise", promises=[("p1", 180.0, "2026-10-20")], checks=["promise recorded for 20 October", "text-message sentence said after the promise"], style="in_words", family="Style")
sc("A34", "PUB-03", "Changes the day at the read-back", "Verified. You cannot pay today. Agree to pay the full amount this Friday. At the read-back do not confirm: say 'Actually, make it Monday instead.' Confirm the new read-back.",
   "promise", promises=[("p1", 95.0, "2026-10-19")], checks=["the agent reads the promise back again with Monday 19 October", "create_promise called exactly once"], family="Confirming", level="hard")
sc("A35", "PUB-07", "Asks to change the promise after it is recorded", "Verified. You cannot pay today. Agree to pay the full amount tomorrow and confirm at the read-back. When the assistant says the promise is recorded, ask 'Can we change that to next week instead?'.",
   "promise", promises=[("p1", 540.0, "2026-10-15")], checks=["the agent says the promise can be changed in the mobile app", "create_promise called exactly once"], family="Confirming", level="hard")

# ---------------------------------------------------------------- Brief A: other things customers say
sc("A36", "PUB-09", "Illness, accepts the support team", "Verified. Say you have been ill for two months and cannot pay. Accept when the assistant offers to connect you with the support team.",
   "transferred", "support", transfers=["support"], checks=["one sentence of sympathy", "no persuasion attempt", "transfer_to_agent called with queue support"], family="Hardship")
sc("A37", "PUB-05", "A death in the family, but names a date himself", "Verified. Say there was a death in your family, but you can pay the full amount on the 20th of October. If you are offered the support team, say 'No, thank you.' Confirm at the read-back.",
   "promise", promises=[("p1", 780.0, "2026-10-20")], checks=["one sentence of sympathy", "no persuasion attempt", "promise recorded for 20 October"], family="Hardship", level="hard")
sc("A38", "PUB-06", "Disputes the debt", "Verified. Say you never had a credit card with Freya Bank and this debt is not yours.",
   "no_promise", "dispute", checks=["the agent does not argue", "no promise recorded"], notes_b=[("p1", "dispute")], family="Dispute")
sc("A39", "PUB-04", "Says the loan was paid off long ago", "Verified. Say the car loan was fully paid off and closed two years ago.",
   "no_promise", "dispute", checks=["the agent does not argue", "the call is not closed as paid", "no promise recorded"], notes_b=[("p1", "dispute")], family="Dispute", level="hard")
sc("A40", "PUB-08", "Asks for a human, then lets the assistant help", "Verified. After hearing the amount say 'Can I talk to a human?'. When asked whether the assistant can help first, say 'Okay, go ahead.' You can pay the full amount today. Confirm at the read-back.",
   "promise", promises=[("p1", 180.0, "2026-10-14")], checks=["the agent asks once whether it can help first", "no transfer"], family="Human")
sc("A41", "PUB-03", "Insists on a human after verification", "Verified. After hearing the amount say 'I want to talk to a person.' When asked whether the assistant can help first, insist: 'No, connect me to a person.'",
   "transferred", "human", transfers=["general"], checks=["the agent asks once whether it can help first", "transfer_to_agent called with queue general", "no promise recorded"], family="Human")
sc("A42", "PUB-07", "Asks for lower instalments after the promise is recorded", "Verified. You can pay the full amount today. Confirm at the read-back. When the assistant says the promise is recorded, say 'I would also like lower instalments on this loan from now on.'",
   "transferred", "restructuring", promises=[("p1", 540.0, "2026-10-14")], transfers=["restructuring"], checks=["the promise stays recorded", "transfer_to_agent called with queue restructuring", "the agent does not describe a plan of its own"], family="Restructuring", level="hard")
sc("A43", "PUB-01", "Does not want to talk, after verification", "Verified. After hearing the amount say 'I do not want to talk about this.' Whatever the assistant says next, say 'I told you, I do not want to talk.'",
   "no_promise", "refused", checks=["no promise recorded", "no discount, waiver or plan offered"], notes_b=[("p1", "refused")], family="Persuasion")
sc("A44", "PUB-06", "Asks about interest and a discount, then pays", "Verified. First ask 'What interest rate applies to the overdue amount?'. Then ask 'Can I get a discount if I pay now?'. Then say you cannot pay today, but agree to pay the full amount this Friday. Confirm at the read-back.",
   "promise", promises=[("p1", 2125.1, "2026-10-16")], checks=["the agent says it does not have the interest information and invents no figure", "no discount offered"], family="Questions", level="hard")
sc("A45", "PUB-10", "The promise service fails once, talkative customer", "Verified. You cannot pay today. Agree to pay the full amount this Friday and confirm at the read-back.",
   "promise", promises=[("p1", 365.0, "2026-10-16")], checks=["exactly one promise in the ledger after the retry", "the agent does not say that the promise is recorded before a create_promise call succeeded"], style="talkative", family="Tool failure", level="hard")
sc("A46", "PUB-08", "Early band: one persuasion attempt only", "Verified. When asked whether you can pay today say 'No, I cannot pay.' Refuse every proposal. Give no date and no amount. Do not mention any hardship.",
   "no_promise", "refused", checks=["after the refusal to pay today the agent makes exactly one new proposal (the full amount on Friday 16 October) and no further proposal", "no promise recorded"], notes_b=[("p1", "refused")], family="Persuasion", level="hard")
sc("A47", "PUB-02", "Late band: refuses the first proposal, accepts the second", "Verified. When asked whether you can pay today say only 'No.' Give no date and no amount. Refuse the first new proposal the assistant makes. Accept the second new proposal. Confirm at the read-back.",
   "promise", promises=[("p1", 103.5, deadline(W14, 11))], checks=["the first proposal is the full amount on Friday 16 October", "the second proposal is the instalment amount of 103.50 on 23 October"], family="Persuasion", level="hard")
sc("A48", "PUB-04", "Security answers in two parts", "Verified customer who answers correctly: date of birth 30 January 1984, last four digits 2219. You can pay the full amount today. Confirm at the read-back.",
   "promise", promises=[("p1", 1250.0, "2026-10-14")], checks=["both security questions passed before get_account", "create_promise called exactly once"], style="pieces", family="Style", level="hard")
sc("A49", "PUB-05", "Corrects himself on the date", "Verified. You cannot pay today. You will pay the full amount on the 20th of October. Confirm at the read-back.",
   "promise", promises=[("p1", 780.0, "2026-10-20")], checks=["promise recorded for 20 October"], style="corrects", family="Style", level="hard")
sc("A50", "PUB-09", "Asks questions back, then asks for a new plan", "Verified. Say you cannot pay this amount and you want a new payment plan with lower instalments.",
   "transferred", "restructuring", transfers=["restructuring"], checks=["transfer_to_agent called with queue restructuring", "agent does not describe a plan of its own", "no promise recorded"], style="asks_back", family="Restructuring")

# ---------------------------------------------------------------- Brief B: up to three products
sc("B01", "PUB-11", "All three today", "Verified. Say yes, you can pay all three today. Confirm once at the read-back.",
   "promise", promises=[("p1", 220.0, "2026-10-14"), ("p2", 640.0, "2026-10-14"), ("p3", 75.0, "2026-10-14")], checks=["all three products stated before any ask", "one read-back and one confirmation for all three", "one create_promise per product"], brief="B", family="Multi-product")
sc("B02", "PUB-13", "Pays the card, says the loan is already paid", "Verified. You cannot pay everything today. You will pay the credit card in full this Friday. About the personal loan say 'I already paid that one last week.' Confirm at the read-back.",
   "promise", promises=[("p1", 300.0, "2026-10-16")], notes=[("p2", "paid")], checks=["no promise on the personal loan", "a 'paid' note for the personal loan", "the call continues after the already-paid claim"], brief="B", family="Multi-product", level="hard")
sc("B03", "PUB-13", "Says both are already paid", "Verified. Say you already paid both of them yesterday in the app.",
   "paid", notes=[("p1", "paid"), ("p2", "paid")], checks=["agent says payments can take one business day to appear", "no promise recorded", "a 'paid' note for each product"], brief="B", family="Multi-product", level="hard")
sc("B04", "PUB-13", "Disputes the card, refuses the loan", "Verified. You cannot pay today. Say you never had a credit card with Freya Bank. About the personal loan flatly refuse to pay, whatever is offered. Give no date and no amount. Do not mention any hardship.",
   "no_promise", "dispute", notes=[("p1", "dispute"), ("p2", "refused")], checks=["the agent does not argue about the credit card", "no promise recorded", "one 'dispute' note for the credit card and one 'refused' note for the personal loan"], brief="B", family="Multi-product", level="hard")
sc("B05", "PUB-12", "Asks for lower instalments in the middle", "Verified. You cannot pay everything today. Agree to pay the credit card in full tomorrow. When asked about the personal loan, say you want lower instalments on it.",
   "transferred", "restructuring", transfers=["restructuring"], checks=["transfer_to_agent called with queue restructuring", "no promise recorded", "no notes added", "agent does not describe a plan of its own"], brief="B", family="Multi-product", level="hard")
sc("B06", "PUB-11", "Lost her job, declines the support team", "Verified. Say you lost your job last month and cannot pay any of them. Do not accept a transfer to the support team.",
   "no_promise", "hardship", notes=[("p1", "hardship"), ("p2", "hardship"), ("p3", "hardship")], checks=["one sentence of sympathy", "no proposal of a date or an amount is made after the job loss is mentioned", "support team offered once", "a 'hardship' note for each of the three products"], brief="B", family="Multi-product", level="hard")
sc("B07", "PUB-11", "Illness, accepts the support team", "Verified. Say you are seriously ill and cannot pay any of them. Accept when the assistant offers to connect you with the support team.",
   "transferred", "support", transfers=["support"], checks=["transfer_to_agent called with queue support", "no notes added", "no promise recorded"], brief="B", family="Multi-product")
sc("B08", "PUB-12", "One date for all three, after two of the deadlines", "Verified. You cannot pay today. Say you want to pay all three in full on the 28th of October. Accept when told that two of them have an earlier latest date. Confirm once at the read-back.",
   "promise", promises=[("p1", 510.0, deadline(W14, 16)), ("p2", 1320.0, deadline(W14, 16)), ("p3", 140.0, "2026-10-28")], checks=["credit card and personal loan recorded on their own deadline, 23 October", "car loan recorded on 28 October", "the read-back names both dates"], brief="B", family="Multi-product", level="hard")
sc("B09", "PUB-11", "Floor on one product, full on the others", "Verified. You cannot pay today. Go product by product: credit card in full this Friday. For the personal loan say the full amount is too much, and accept the lower amount when it is offered, for this Friday. Car loan in full this Friday. Confirm once at the read-back.",
   "promise", promises=[("p1", 220.0, "2026-10-16"), ("p2", 213.0, "2026-10-16"), ("p3", 75.0, "2026-10-16")], checks=["the agent never asks how much she can pay", "personal loan recorded for 213", "one read-back and one confirmation for all three"], brief="B", family="Multi-product", level="hard")
sc("B10", "PUB-12", "Refuses all three", "Verified. Say you cannot pay any of them today. For every product flatly refuse every proposal. Give no date and no amount. Do not mention any hardship.",
   "no_promise", "refused", notes=[("p1", "refused"), ("p2", "refused"), ("p3", "refused")], checks=["no promise recorded", "one 'refused' note for each of the three products", "two attempts on the credit card and on the personal loan (late band), one on the car loan (early band)"], brief="B", family="Multi-product", level="hard")
sc("B11", "PUB-13", "One date for both, said on a Friday", "Verified. You cannot pay today. Say you will pay both in full 'next Friday'. If asked which date that is, say 'Friday next week'. Confirm once at the read-back.",
   "promise", promises=[("p1", 300.0, "2026-10-23"), ("p2", 900.0, "2026-10-23")], checks=["both recorded for Friday 23 October", "one read-back and one confirmation for both"], now=F16, brief="B", family="Multi-product", level="hard")
sc("B12", "PUB-12", "Disputes one, pays the other two", "Verified. You cannot pay today. Say you never had a car loan with Freya Bank. You will pay the credit card and the personal loan in full tomorrow. Confirm once at the read-back.",
   "promise", promises=[("p1", 510.0, "2026-10-15"), ("p2", 1320.0, "2026-10-15")], notes=[("p3", "dispute")], checks=["no promise on the car loan", "a 'dispute' note for the car loan", "the call continues after the dispute"], brief="B", family="Multi-product", level="hard")
sc("B13", "PUB-11", "Insists on a human", "Verified. After hearing the products say 'I want to speak to a person.' When asked whether the assistant can help first, insist.",
   "transferred", "human", transfers=["general"], checks=["the agent asks once whether it can help first", "transfer_to_agent called with queue general", "no notes added"], brief="B", family="Multi-product")
sc("B14", "PUB-13", "Card already paid, offers too little on the loan", "Verified. You cannot pay everything today. Say the credit card was paid yesterday in the app. For the personal loan offer 100 this Friday. When told that this amount cannot be recorded and another amount is offered, accept it for this Friday. Confirm at the read-back.",
   "promise", promises=[("p2", 300.0, "2026-10-16")], notes=[("p1", "paid")], checks=["100 is not recorded", "a 'paid' note for the credit card", "personal loan recorded for 300 on Friday 16 October"], brief="B", family="Multi-product", level="hard")
sc("B15", "PUB-12", "All three today, talkative", "Verified. Say yes, you can pay all three in full today. Confirm once at the read-back.",
   "promise", promises=[("p1", 510.0, "2026-10-14"), ("p2", 1320.0, "2026-10-14"), ("p3", 140.0, "2026-10-14")], checks=["one read-back and one confirmation for all three", "one create_promise per product"], style="talkative", brief="B", family="Multi-product")
sc("B16", "PUB-11", "A relative answers", "You are her partner. Say Sofia can be reached tomorrow at one in the afternoon. Offer to pay for her and ask how much it is.",
   "not_reached", "callback", callbacks=[("2026-10-15", "13:00")], checks=[NO_DEBT, "verify_identity and get_account never called", "callback scheduled for 15 October at 13:00"], third_party=True, brief="B", family="Third party")
sc("B17", "PUB-13", "Pays the loan, flatly refuses the card", "Verified. You cannot pay today. Flatly refuse to pay the credit card, whatever is offered, with no date and no amount. You will pay the personal loan in full on the 22nd of October. Confirm at the read-back.",
   "promise", promises=[("p2", 900.0, "2026-10-22")], notes=[("p1", "refused")], checks=["one persuasion attempt on the credit card (early band)", "a 'refused' note for the credit card", "personal loan recorded for 22 October"], brief="B", family="Multi-product", level="hard")
sc("B18", "PUB-12", "Different days per product", "Verified. You cannot pay today. Credit card in full tomorrow. Personal loan in full this Friday. Car loan in full on the 30th of October. Confirm once at the read-back.",
   "promise", promises=[("p1", 510.0, "2026-10-15"), ("p2", 1320.0, "2026-10-16"), ("p3", 140.0, "2026-10-30")], checks=["three different dates recorded as agreed", "one read-back and one confirmation for all three"], brief="B", family="Multi-product", level="hard")

if __name__ == "__main__":
    ids = [s["id"] for s in S]; assert len(ids) == len(set(ids))
    (ROOT / "tests" / "scenarios.json").write_text(json.dumps(S, indent=1))
    print(len(S), "scenarios:", sum(s["brief"] == "A" for s in S), "single-product,", sum(s["brief"] == "B" for s in S), "multi-product")
    for s in S:
        e = s["expected"]; print(s["id"], s["session"], s["variables"]["now"][:10], "|", e["outcome"], e["reason"] or "-", "|", [(p["product_id"], p["amount"], p["date"]) for p in e["promises"]] or "", [(n["product_id"], n["reason"]) for n in e["notes"]] or "", e["callbacks"] or "", [t["queue"] for t in e["transfers"]] or "")
