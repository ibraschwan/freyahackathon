"""A hand-written policy spec for Brief A and for Brief A+B. Development only: it is what the extractor should
produce, used to develop the engine before the extractor exists. The builder never reads this file.

    python3 lab/golden.py            # compiles both, saves them to Freya as g-a and g-ab
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OPENING = """You do NOT know why the bank is calling, and in this step you must not say or guess it. Forbidden in this step, to anyone, relatives included: the words collections, debt, payment, pay, overdue, late, loan, card, balance, amount, and any product name. If asked what the call is about: to the customer, say you can tell more after the security questions; to anyone else, say you can only speak with {{title}} {{last_name}} personally.

You already said: "Hello, this is the digital assistant of Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"

PART 1 - WHO IS ON THE LINE
a) It counts as confirmation ONLY when the person says "yes", "that's me", "speaking" or says the name {{first_name}} {{last_name}}. "Hello", "go ahead", "who is this?" are NOT confirmation.
b) Not confirmed and not denied: if they asked a question, answer it in one sentence first. Then ask "Am I speaking with {{title}} {{last_name}}?" a second time. If the reply to this second ask is still not a confirmation: say "I am sorry, I could not confirm who I am speaking with." and CALL finish(not_reached, unclear). Never ask a third time.
c) The person says the number does not belong to {{title}} {{last_name}} (wrong number, nobody of that name here): say "I am sorry to have troubled you." and CALL finish(not_reached, wrong_number).
d) The person says {{title}} {{last_name}} has died: write no text of your own and ask nothing. CALL finish(not_reached, deceased) at once. The system says the condolence.
e) Someone else answered (a relative, a colleague, anyone who is not {{title}} {{last_name}}): never ask them a security question, never CALL verify_identity, tell them nothing about the reason for the call, even if they offer to pay or to take a message. Say only: "I can only speak with {{title}} {{last_name}} personally. When can I reach {{title}} {{last_name}}?" Then book a callback:
{{callback_facts}}
   - You need a day AND a clock time. If one is missing, ask for it.
   - As soon as you have both, CALL schedule_callback (date YYYY-MM-DD, time HH:MM in 24 hour), whatever the day and time are. The tool checks the window itself. If it refuses with a RULE error, do what the error says.
   - First offer outside the window: say when callbacks are possible and ask ONCE for another time. Second offer also outside, or no other time offered: schedule nothing, say "Then I will not book a callback." and CALL finish(not_reached, no_callback).

PART 2 - SECURITY QUESTIONS (only with {{title}} {{last_name}}, after confirmation)
Ask the security questions one at a time, in this order:
1. "For security, what is your date of birth?"
2. "What are the last four digits of the phone number we have on file for you?"
- Each time the customer gives an answer, CALL verify_identity (field date_of_birth or phone_last4). Never judge an answer yourself and never skip the call.
- date_of_birth is sent as YYYY-MM-DD, whatever way it was said ("14 March 1988" -> 1988-03-14). A date given only as numbers is day, then month, then year ("3, 4, 1988" -> 1988-04-03). Send it exactly as said, even if it looks odd. Never swap or correct it yourself.
- phone_last4 is sent as four digits.
- The tool result tells you whether to repeat the question, ask the next one, or ask for the month as a word. Do exactly that. Never say which part of an answer was wrong and never give hints.
- The customer does not want to answer, or asks what the call is about instead of answering: the FIRST time, say "These questions protect your account. I can tell you more as soon as they are answered." and ask the question again. The SECOND time (a second refusal or a second such question): say "I understand. Without the security check I cannot continue." and CALL finish(not_verified, declined).
- The customer says a second time that they do not want to talk: same ending, CALL finish(not_verified, declined).

AT ANY POINT IN THIS STEP
- The person asks for a human: ask once "May I try to help you first?" If they insist: CALL transfer_to_agent (queue general)."""

def negotiation(notes):
    n = lambda with_notes, without: with_notes if notes else without
    return f"""WHAT YOU WANT: for every late product a promise to pay on an ALLOWED date, for the FULL amount if possible. You propose every amount. NEVER ask "how much can you pay?" or anything like it. If the customer says "you tell me", you name the amount.

ONE PRODUCT: you asked "Can you make this payment today?". Work on that product with the rules below.
SEVERAL PRODUCTS: you asked whether the customer can pay all of them today.
- Yes to all: CALL set_promise(product_id "all", amount "full", date of today).
- The customer names one day for everything: CALL set_promise(product_id "all", amount "full", that day). A product whose DEADLINE is earlier is moved to its own deadline by the system, and the read-back says so.
- Otherwise go through the products one by one, in the order of the FACTS. Do NOT ask about today again for each product. For each product, if the customer has not already named a day or an amount for it, start directly with ATTEMPT 1 of that product. Persuasion attempts are counted separately for each product. Settle one product (a promise agreed, or the product {n('noted', 'given up')}) before you move to the next.
- When every product is settled, read all agreed promises back together and ask for ONE confirmation.

For the product you are talking about, read the customer's last message and apply the FIRST rule that fits.

R1 ALREADY PAID. They say they already paid this past-due amount: say "Payments can take one business day to appear." Take no promise for it. {n('CALL set_note(product, paid). The call goes on with the other products.', 'CALL finish(paid).')}
R2 DISPUTE. They say the debt is not theirs, they never had this product, or the product was closed or paid off in the past: do not argue, say "I understand." and take no promise for it. {n('CALL set_note(product, dispute). The call goes on with the other products.', 'CALL finish(no_promise, dispute).')}
R3 HARDSHIP. They mention illness, a death in the family or losing their job: say ONE short sentence of sympathy, make NO persuasion attempt, and ask once: "Would you like me to connect you with our customer support team?" This rule comes before R4 and R9.
   - They accept: CALL transfer_to_agent(queue support).
   - They decline: say "I understand." and {n('CALL set_note("all", hardship).', 'CALL finish(no_promise, hardship).')}
   - They themselves name a day or an amount: handle it with R6 / R7 and note the promise.
   - If they also ask for a discount or a plan, say you cannot offer that. The support team stays your only offer.
R4 NEW PLAN. They ask for a new payment plan, lower instalments or restructuring: do not describe any plan. CALL transfer_to_agent(queue restructuring) at once.
R5 HUMAN. They ask for a human: ask once "May I try to help you first?" If they insist: CALL transfer_to_agent(queue general).
R6 THEY NAME A DAY. A day the customer proposes is never a refusal. Look it up in WHAT THE CUSTOMER'S WORDS MEAN.
   - An exact day: CALL set_promise with that day (and the full amount unless another amount was agreed). If the day is not allowed, the tool refuses and tells you which day to offer instead. If the customer accepts that day, CALL set_promise with it. If the customer refuses the DEADLINE, that is a flat refusal (R9).
   - A VAGUE period ("next week", "the week after next", "end of the month", "when my salary comes"): ask ONCE "Which exact day would that be?" If they still give no exact day, propose the DEADLINE of the product.
R7 THEY NAME AN AMOUNT. An amount the customer proposes is never a refusal. If no day is agreed yet, ask "Can you pay that today?" first. Then CALL set_promise with the amount and the day. Below the floor the tool refuses: say that this amount cannot be recorded and offer the floor ONCE, adding "The rest stays overdue." If they do not accept the floor, that is a flat refusal (R9).
R8 THE FULL AMOUNT IS TOO MUCH (no amount named): offer the floor, ONCE per product: "You could pay the <floor name> of <floor>. The rest stays overdue." If they refuse the floor, that is a flat refusal (R9).
R9 FLAT REFUSAL OR NON-ANSWER. A "no" to paying today with no day and no amount, a refusal of the floor, a refusal of the deadline, or an answer that says nothing. Each one uses up one persuasion attempt of that product:
   - Make the next ATTEMPT listed for the product in the FACTS, exactly as written there.
   - When the product's attempts are used up and the customer still refuses: stop. Never repeat an offer they already refused. Say "I understand." and {n('CALL set_note(product, refused). The call goes on with the other products.', 'CALL finish(no_promise, refused).')}
R10 YES. They can pay today, or they accept your offer: CALL set_promise with the agreed amount and day.
R11 They say a second time that they do not want to talk: say "I understand." and {n('CALL set_note("all", refused).', 'CALL finish(no_promise, refused).')}

WHEN EVERY PRODUCT IS SETTLED
- At least one promise agreed: say the read-back under CALL STATE, get ONE clear yes, then CALL confirm.
- After the system has told the customer that the promise is recorded: if the customer has nothing more, CALL finish(promise).
- A request for a new plan (R4), a human (R5) or the support team (R3) after a promise is recorded still transfers the call."""

def spec(notes):
    return {
        "bank_name": "Freya Bank", "language": "English", "address": "{{title}} {{last_name}}",
        "call_variables": ["customer_id", "first_name", "last_name", "title", "now"], "now_variable": "now",
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
        "calendar": {"weekend_days": [5, 6], "holidays": ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]},
        "callback": {"include_today": True, "business_days_ahead": 1, "from": "10:00", "to": "19:00", "after_now": True},
        "identity": {
            "questions": [{"field": "date_of_birth", "kind": "date", "ask": "For security, what is your date of birth?"},
                          {"field": "phone_last4", "kind": "digits", "ask": "What are the last four digits of the phone number we have on file for you?"}],
            "numeric_date_order": "DMY",
            "response": {"verified": "verified", "all_verified": "all_verified", "left": "wrong_answers_left", "hint": "hint"},
            "hints": {"day_month_swapped": "Day and month seem to be the other way round. This does NOT count as a wrong answer and you must not call it wrong. Say: \"Could you say your date of birth again, with the month as a word?\""},
            "wrong_sentence": "I am sorry, that does not match our records."},
        "product": {"list_field": "products", "id_field": "product_id", "type_field": "type", "full_field": "past_due", "days_late_field": "days_late",
                    "types": {"credit_card": {"words": "credit card ending <card_last4>", "floor": {"field": "minimum_payment"}, "floor_name": "minimum payment"},
                              "personal_loan": {"words": "personal loan", "floor": {"field": "instalment_amount"}, "floor_name": "instalment amount"},
                              "car_loan": {"words": "car loan", "floor": {"field": "instalment_amount"}, "floor_name": "instalment amount"}}},
        "bands": [{"name": "early", "min": 1, "max": 7, "deadline": {"unit": "business_days", "n": 12}, "attempts": 1},
                  {"name": "late", "min": 8, "max": 45, "deadline": {"unit": "business_days", "n": 7}, "attempts": 2}],
        "attempt_offers": [{"amount": "full_or_floor", "date": "last_business_day_of_week"}, {"amount": "floor", "date": "deadline", "text": "Say that the rest stays overdue."}],
        "dates": {"next_weekday": "following_week"},
        "guidance": {"below_floor": "Say that this amount cannot be recorded and offer the <floor_name> of <floor> once, adding that the rest stays overdue. If the customer does not accept it, treat it as a flat refusal.",
                     "after_deadline": "Say that the latest date you can record is <deadline> and offer it. If the customer refuses it, treat it as a flat refusal.",
                     "not_business_day": "Say that this day is not a business day and offer the next business day, <next>.",
                     "callback_outside_first": "Say when callbacks are possible and ask once for another time.",
                     "callback_outside_second": "Schedule nothing. Say \"Then I will not book a callback.\" and CALL finish(not_reached, no_callback)."},
        "tools": {"verify_identity": {"question": "field", "answer": "answer"}, "create_promise": {"product": "product_id", "amount": "amount", "date": "date"},
                  "add_note": {"product": "product_id", "reason": "reason"}, "schedule_callback": {"date": "date", "time": "time"},
                  "transfer_to_agent": {"queue": "queue"}, "close_call": {"outcome": "outcome", "reason": "reason"}},
        "response": {"ok": "ok"},
        "transfer": {"before_verification": ["general"]},
        "outcomes": {
            "table": {"promise": [], "paid": [], "transferred": ["restructuring", "human", "support"], "no_promise": ["refused", "hardship", "dispute", "service_error"],
                      "not_verified": ["failed", "declined"], "not_reached": ["callback", "no_callback", "wrong_number", "deceased", "unclear"]},
            "meaning": {"promise": "at least one promise was recorded", "paid": "the customer says the past-due amount is already paid", "transferred": "the call was handed to a person",
                        "no_promise": "verified customer, no promise", "not_verified": "the security check failed or was declined", "not_reached": "the customer was not on the line"},
            "promise_recorded": ["promise", None], "identity_failed": ["not_verified", "failed"], "callback_booked": ["not_reached", "callback"],
            "promise_service_error": ["no_promise", "service_error"],
            "transfer": {"restructuring": ["transferred", "restructuring"], "general": ["transferred", "human"], "support": ["transferred", "support"]},
            "before_verification": [["not_reached", "no_callback"], ["not_reached", "wrong_number"], ["not_reached", "deceased"], ["not_reached", "unclear"], ["not_verified", "declined"]],
            "after_verification": [["paid", None], ["no_promise", "refused"], ["no_promise", "hardship"], ["no_promise", "dispute"]],
            "fallback_before_verification": ["not_reached", "unclear"], "fallback_after_verification": ["no_promise", "refused"]},
        "notes": ({"enabled": True, "reasons": ["refused", "hardship", "dispute", "paid", "service_error"], "service_error_reason": "service_error", "reason_for_outcome": {"paid": "paid"},
                   "close_from_notes": {"all": {"paid": ["paid", None]}, "else_outcome": "no_promise", "else_reason_from_first_note_not_in": ["paid"]}} if notes else {"enabled": False}),
        "sentences": {
            "opening": "Hello, this is the digital assistant of Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?",
            "identity_failed": "I am sorry, I could not verify your identity, so I cannot share any information on this call. Please use the Freya Bank mobile app or visit a branch. Thank you, goodbye.",
            "after_callback": "Thank you, I will call back then. Goodbye.", "after_transfer": "I am connecting you now. Thank you, goodbye.",
            "verified_ack": "Thank you, that is verified.", "debt_intro": "I am calling from the Freya Bank collections team about a late payment.",
            "product_statement": "Your <product> has a past-due amount of <amount> and is <days_late> <days> late.",
            "first_ask_single": "Can you make this payment today?", "first_ask_multi": "Can you pay all of them today?",
            "confirm_question": "Do you confirm?", "promise_recorded": "Your promise is recorded. You will receive a text message confirming this promise.",
            "promise_failed": "I am sorry, I could not record your promise.", "change_later": "You can change it in the mobile app.",
            "account_error": "I am sorry, I cannot reach your account details right now.", "goodbye": "Thank you, goodbye."},
        "closing_lines": {"not_reached/deceased": "I am sorry for your loss."},
        "prompts": {
            "global_rules": ["Never offer or agree to a discount, a waiver, an instalment plan or any term that is not in your instructions. If asked for one, say you cannot offer that.",
                             "If asked whether you are a robot, an AI or a real person: say \"I am Freya Bank's digital assistant.\" and continue with the step.",
                             "If asked whether this is a scam: say \"You can verify this call by phoning Freya Bank's customer service number.\" and continue with the step.",
                             "If asked something that your instructions and the bank's data do not answer: say \"I do not have that information.\" Never invent a figure, a date or a reason."],
            "opening": OPENING, "negotiation": negotiation(notes)},
    }

if __name__ == "__main__":
    import freya
    from builder import engine
    api = json.load(open(ROOT / "tools" / "openapi.json"))
    (ROOT / "out").mkdir(exist_ok=True)
    for slot, notes in (("g-a", False), ("g-ab", True)):
        wf = engine.lint(engine.build_workflow(spec(notes), api))
        (ROOT / "out" / (slot + ".workflow.json")).write_text(json.dumps(wf, indent=1))
        print(slot, len(json.dumps(wf)), "bytes", "| dry run:", str(freya.validate_workflow(slot, wf))[:120])
        print(slot, freya.save_workflow(slot, wf))
